"""FIRMS area API -> data/firms_api/: the hotspots after the yearly archive.

The yearly "all countries" zips end with [data] last_year. This step fills January 1 of the next
year to today from the FIRMS area API, one CSV per product and UTC acquisition date:

    data/firms_api/{product}/{YYYY-MM-DD}.{sp|nrt}.csv   (header only on a day with no detections)
    data/firms_api/availability.json                     FIRMS date ranges at download time

Standard-processing (SP) data is used where FIRMS has it and near-real-time (NRT) after that. An
NRT day is replaced once its SP version is published, and the last few NRT days are fetched again
on every run because NRT files keep filling in for a day or two.

Requests run in parallel ([data] api_workers, default 4) and are paced by the key's own transaction
count (mapkey_status): a request starts only while the count, plus what the requests in flight are
expected to cost, stays under QUOTA_SHARE of the limit (5,000 per 10 minutes). The expected cost is
measured on the first request, which runs alone. [data] api_products limits the products fetched
(the global run fetches only VIIRS: its series uses no MODIS after 2012).

`download --sample YYYY-MM-DD` fetches 5 standard-processing days from that date into
firms_api_sample/{product}/ and prints the time and transactions each request took: a probe before a
large download, and archive days to compare the API with the yearly files.

The MAP_KEY comes from FIRMS_MAP_KEY in the environment or in the git-ignored .env at the repo
root (for a git worktree, the main checkout's). It is placed only in request URLs: never printed,
logged, or written to disk.
"""
import csv
import datetime as dt
import io
import json
import os
import pathlib
import subprocess
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from .config import ROOT, Config

BASE = "https://firms.modaps.eosdis.nasa.gov"
SOURCES = {"modis": "MODIS", "viirs-snpp": "VIIRS_SNPP", "viirs-jpss1": "VIIRS_NOAA20"}  # product -> FIRMS id
CHUNK_DAYS = 5      # the area API's largest DAY_RANGE
REFRESH_DAYS = 3    # NRT days this close to the newest are fetched again
QUOTA_SHARE = 0.95  # share of the key's transaction limit the download may fill
RETRIES = 4         # attempts per request on a timeout, connection error or server error


class MissingKey(RuntimeError):
    pass


def map_key() -> str:
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    env = env_file()
    if not key and env:
        for line in env.read_text().splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() == "FIRMS_MAP_KEY":
                key = value.strip().strip('"').strip("'")
    if not key:
        raise MissingKey("FIRMS_MAP_KEY is not set: put it in .env at the repo root (see .env.example).")
    return key


def env_file():
    """.env at the repo root; in a git worktree without one, the main checkout's."""
    if (ROOT / ".env").exists():
        return ROOT / ".env"
    try:
        common = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    env = pathlib.Path(common).parent / ".env"
    return env if env.exists() else None


class Transient(RuntimeError):
    """A failure worth retrying: timeout, connection error, server error."""


def get(url: str, key: str, timeout: int = 180) -> str:
    """GET a FIRMS URL; any error message has the key removed."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        kind = Transient if e.code >= 500 or e.code == 429 else RuntimeError
        raise kind(f"FIRMS HTTP {e.code}: {body}".replace(key, "<MAP_KEY>")) from None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        reason = getattr(e, "reason", e)
        raise Transient(f"FIRMS unreachable: {reason}".replace(key, "<MAP_KEY>")) from None


def availability(key: str) -> dict[str, tuple[dt.date, dt.date]]:
    text = get(f"{BASE}/api/data_availability/csv/{key}/ALL", key)
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        out[row["data_id"]] = (dt.date.fromisoformat(row["min_date"]), dt.date.fromisoformat(row["max_date"]))
    if not out:
        raise RuntimeError("FIRMS data_availability returned nothing: " + text[:200].replace(key, "<MAP_KEY>"))
    return out


def key_status(key: str) -> tuple[int, int]:
    """(transactions used in the current 10-minute window, limit)."""
    s = json.loads(get(f"{BASE}/mapserver/mapkey_status/?MAP_KEY={key}", key))
    return int(s.get("current_transactions") or 0), int(s.get("transaction_limit") or 5000)


class Quota:
    """Starts requests only while the key's count plus the expected cost of those in flight stays
    under QUOTA_SHARE of its limit."""

    def __init__(self, key: str, cost: float = 1.0):
        self.key, self.cost, self.inflight = key, cost, 0
        self.lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            used, limit = key_status(self.key)
            with self.lock:
                if used + (self.inflight + 1) * self.cost <= QUOTA_SHARE * limit:
                    self.inflight += 1
                    return
            print(f"  FIRMS quota {used}/{limit} used, {self.inflight} requests in flight; waiting 30 s", flush=True)
            time.sleep(30)

    def release(self) -> None:
        with self.lock:
            self.inflight -= 1


def measured(key: str, call):
    """Run call() alone; returns (result, seconds, transactions it cost as the key's count saw it)."""
    before = key_status(key)[0]
    t = time.monotonic()
    out = call()
    secs = time.monotonic() - t
    time.sleep(5)  # let the count catch up
    after = key_status(key)[0]
    return out, secs, max(after - before, 0)


def fetch(key: str, source: str, bbox: str, first: dt.date, n: int) -> dict[dt.date, tuple[str, list[str]]]:
    """One area request: `n` days from `first`. Returns {acq_date: (header, rows)} for every day asked."""
    url = f"{BASE}/api/area/csv/{key}/{source}/{bbox}/{n}/{first.isoformat()}"
    for attempt in range(RETRIES):
        try:
            text = get(url, key, timeout=900)
            break
        except Transient as e:
            if attempt == RETRIES - 1:
                raise
            wait_s = 30 * 2 ** attempt
            print(f"  {source} {first}: {e}; retrying in {wait_s} s", flush=True)
            time.sleep(wait_s)
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


def products(cfg: Config) -> dict[str, str]:
    """Products to fetch: [data] api_products, default all three."""
    names = cfg["data"].get("api_products", list(SOURCES))
    unknown = set(names) - set(SOURCES)
    if unknown:
        raise SystemExit(f"download: unknown api_products {sorted(unknown)}; choose from {list(SOURCES)}")
    return {p: SOURCES[p] for p in names}


def bbox_arg(cfg: Config) -> str:
    return ",".join(f"{float(v):g}" for v in cfg.bbox)


def save(pdir: pathlib.Path, variant: str, got: dict) -> int:
    """Write one CSV per day; an SP day replaces its NRT file. Returns the row count."""
    for day, (header, rows) in got.items():
        path = pdir / f"{day}.{variant}.csv"
        tmp = path.with_suffix(".tmp")
        tmp.write_text("\n".join([header, *rows]) + "\n")
        tmp.replace(path)
        other = pdir / f"{day}.{'nrt' if variant == 'sp' else 'sp'}.csv"
        if variant == "sp" and other.exists():
            other.unlink()
    return sum(len(r) for _, r in got.values())


def sample(cfg: Config, first: dt.date) -> None:
    """Probe: CHUNK_DAYS standard-processing days from `first`, one request per product, run alone."""
    key = map_key()
    used, limit = key_status(key)
    print(f"key: {used}/{limit} transactions used in this window", flush=True)
    for product, sid in products(cfg).items():
        pdir = cfg.dir(f"firms_api_sample/{product}")
        got, secs, cost = measured(key, lambda: fetch(key, f"{sid}_SP", bbox_arg(cfg), first, CHUNK_DAYS))
        n = save(pdir, "sp", got)
        print(f"{sid}_SP {first} +{CHUNK_DAYS}d: {n:,} rows in {secs:.0f} s, {cost} transactions", flush=True)


def run(cfg: Config) -> None:
    key = map_key()
    avail = availability(key)
    out = cfg.dir("firms_api")
    start = dt.date(int(cfg["data"]["last_year"]) + 1, 1, 1)
    today = dt.datetime.now(dt.timezone.utc).date()
    bbox = bbox_arg(cfg)
    workers = int(cfg["data"].get("api_workers", 4))
    used = {}
    jobs = []
    for product, sid in products(cfg).items():
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
        jobs += [(pdir, sid, chunk) for chunk in runs(need)]
    print(f"{len(jobs)} requests, up to {workers} at a time", flush=True)

    def one(job) -> str:
        pdir, sid, chunk = job
        first, variant = chunk[0]
        t = time.monotonic()
        try:
            n = save(pdir, variant, fetch(key, f"{sid}_{variant.upper()}", bbox, first, len(chunk)))
        finally:
            quota.release()
        return f"  {sid}_{variant.upper()} {first} +{len(chunk)}d: {n:,} rows in {time.monotonic() - t:.0f} s"

    quota = Quota(key)
    done = 0
    if jobs:  # the first request runs alone, to measure what one costs
        quota.acquire()
        msg, _, cost = measured(key, lambda: one(jobs[0]))
        quota.cost = max(1.0, float(cost))
        done = 1
        print(f"{msg}, {cost} transactions; pacing at {quota.cost:g} per request", flush=True)
    with ThreadPoolExecutor(workers) as pool:
        pending = set()
        for job in jobs[1:]:
            while len(pending) >= workers:
                finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                for f in finished:
                    print(f.result(), flush=True)
                    done += 1
            quota.acquire()
            pending.add(pool.submit(one, job))
        for f in pending:
            print(f.result(), flush=True)
            done += 1
    (out / "availability.json").write_text(json.dumps(
        {"fetched": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
         "sources": {k: [v[0].isoformat(), v[1].isoformat()] for k, v in used.items() if v}}, indent=1))
    used_now, limit = key_status(key)
    print(f"download done: {done} requests; key at {used_now}/{limit} transactions", flush=True)
