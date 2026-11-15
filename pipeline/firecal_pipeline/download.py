"""FIRMS area API -> data/firms_api/: the hotspots after the yearly archive.

The yearly "all countries" zips end with [data] last_year. This step fills January 1 of the next
year to today from the FIRMS area API, one CSV per product and UTC acquisition date:

    data/firms_api/{product}/{YYYY-MM-DD}.{sp|nrt}.csv   (header only on a day with no detections)
    data/firms_api/availability.json                     FIRMS date ranges at download time

Standard-processing (SP) data is used where FIRMS has it and near-real-time (NRT) after that. An
NRT day is replaced once its SP version is published, and the last few NRT days are fetched again
on every run because NRT files keep filling in for a day or two.

The MAP_KEY comes from FIRMS_MAP_KEY in the environment or in the git-ignored .env at the repo
root. It is placed only in request URLs: never printed, logged, or written to disk.
"""
import csv
import datetime as dt
import io
import json
import os
import time
import urllib.error
import urllib.request

from .config import ROOT, Config

BASE = "https://firms.modaps.eosdis.nasa.gov"
SOURCES = {"modis": "MODIS", "viirs-snpp": "VIIRS_SNPP", "viirs-jpss1": "VIIRS_NOAA20"}  # product -> FIRMS id
CHUNK_DAYS = 5      # the area API's largest DAY_RANGE
REFRESH_DAYS = 3    # NRT days this close to the newest are fetched again


class MissingKey(RuntimeError):
    pass


def map_key() -> str:
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text().splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() == "FIRMS_MAP_KEY":
                key = value.strip().strip('"').strip("'")
    if not key:
        raise MissingKey("FIRMS_MAP_KEY is not set: put it in .env at the repo root (see .env.example).")
    return key


def get(url: str, key: str) -> str:
    """GET a FIRMS URL; any error message has the key removed."""
    try:
        with urllib.request.urlopen(url, timeout=180) as r:
            return r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"FIRMS HTTP {e.code}: {body}".replace(key, "<MAP_KEY>")) from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"FIRMS unreachable: {e.reason}".replace(key, "<MAP_KEY>")) from None


def availability(key: str) -> dict[str, tuple[dt.date, dt.date]]:
    text = get(f"{BASE}/api/data_availability/csv/{key}/ALL", key)
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        out[row["data_id"]] = (dt.date.fromisoformat(row["min_date"]), dt.date.fromisoformat(row["max_date"]))
    if not out:
        raise RuntimeError("FIRMS data_availability returned nothing: " + text[:200].replace(key, "<MAP_KEY>"))
    return out


def wait_for_quota(key: str) -> None:
    """Sleep while this key has used most of its transactions for the current 10-minute window."""
    while True:
        s = json.loads(get(f"{BASE}/mapserver/mapkey_status/?MAP_KEY={key}", key))
        used, limit = int(s.get("current_transactions", 0)), int(s.get("transaction_limit", 5000))
        if used < 0.8 * limit:
            return
        print(f"  FIRMS quota {used}/{limit} used; waiting 60 s", flush=True)
        time.sleep(60)


def fetch(key: str, source: str, bbox: str, first: dt.date, n: int) -> dict[dt.date, tuple[str, list[str]]]:
    """One area request: `n` days from `first`. Returns {acq_date: (header, rows)} for every day asked."""
    text = get(f"{BASE}/api/area/csv/{key}/{source}/{bbox}/{n}/{first.isoformat()}", key)
    lines = text.splitlines()
    if not lines or not lines[0].startswith("latitude,"):
        raise RuntimeError(f"FIRMS {source} {first}: unexpected reply: " + text[:200].replace(key, "<MAP_KEY>"))
    header = lines[0]
    col = header.split(",").index("acq_date")
    days = {first + dt.timedelta(i): (header, []) for i in range(n)}
    for line in lines[1:]:
        if not line:
            continue
        d = dt.date.fromisoformat(line.split(",")[col])
        if d not in days:
            raise RuntimeError(f"FIRMS {source}: asked for {first} + {n} days, got a row dated {d}")
        days[d][1].append(line)
    return days


def runs(days: list[tuple[dt.date, str]]):
    """Consecutive days with the same variant, cut into chunks of at most CHUNK_DAYS."""
    chunk: list[tuple[dt.date, str]] = []
    for d, v in days:
        if chunk and (v != chunk[-1][1] or d != chunk[-1][0] + dt.timedelta(1) or len(chunk) == CHUNK_DAYS):
            yield chunk
            chunk = []
        chunk.append((d, v))
    if chunk:
        yield chunk


def run(cfg: Config) -> None:
    key = map_key()
    avail = availability(key)
    out = cfg.dir("firms_api")
    start = dt.date(int(cfg["data"]["last_year"]) + 1, 1, 1)
    today = dt.datetime.now(dt.timezone.utc).date()
    bbox = ",".join(f"{float(v):g}" for v in cfg.bbox)
    used = {}
    n_requests = 0
    for product, sid in SOURCES.items():
        sp, nrt = avail.get(f"{sid}_SP"), avail.get(f"{sid}_NRT")
        used.update({f"{sid}_SP": sp, f"{sid}_NRT": nrt})
        last = min(today, max(r[1] for r in (sp, nrt) if r))
        pdir = cfg.dir(f"firms_api/{product}")
        need = []
        d = start
        while d <= last:
            want = "sp" if sp and sp[0] <= d <= sp[1] else "nrt" if nrt and nrt[0] <= d <= nrt[1] else None
            if want:
                have = (pdir / f"{d}.{want}.csv").exists()
                stale = want == "nrt" and d > nrt[1] - dt.timedelta(REFRESH_DAYS)
                if not have or stale:
                    need.append((d, want))
            d += dt.timedelta(1)
        print(f"{product}: {len(need)} days to fetch ({start} to {last})", flush=True)
        for chunk in runs(need):
            if n_requests % 20 == 0:
                wait_for_quota(key)
            first, variant = chunk[0]
            got = fetch(key, f"{sid}_{variant.upper()}", bbox, first, len(chunk))
            n_requests += 1
            for day, (header, rows) in got.items():
                path = pdir / f"{day}.{variant}.csv"
                tmp = path.with_suffix(".tmp")
                tmp.write_text("\n".join([header, *rows]) + "\n")
                tmp.replace(path)
                other = pdir / f"{day}.{'nrt' if variant == 'sp' else 'sp'}.csv"
                if variant == "sp" and other.exists():
                    other.unlink()
            print(f"  {sid}_{variant.upper()} {first} +{len(chunk)}d: {sum(len(r) for _, r in got.values()):,} rows", flush=True)
    (out / "availability.json").write_text(json.dumps(
        {"fetched": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
         "sources": {k: [v[0].isoformat(), v[1].isoformat()] for k, v in used.items() if v}}, indent=1))
    print(f"download done: {n_requests} requests", flush=True)
