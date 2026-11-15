"""Satellite granule records -> which outage-check units each satellite observed (PREREGISTRATION.md §7, 2026-11-15).

A granule is one 5-minute (MODIS) or 6-minute (VIIRS) slice of a satellite's swath. NASA's Common Metadata
Repository (CMR) keeps a public record of every granule of the fire products FIRMS is built from: when it was
observed, its footprint, and whether it is a day pass, night pass or both. No login is needed.

    granules step:  data/granules/{sat}/{YYYY-MM}.parquet    gid, t0, t1, flag, polys
                    (granules touching the study box, one file per satellite and month of the fit years)
    cells step:     silver/observed.parquet                  sat, r3, d, dn, src

A satellite observed an outage-check unit (H3 resolution-3 cell r3, local solar date d, pass dn) if
  1. one of its granules for that pass covers the cell's centre during that local solar date (a granule flagged
     BOTH counts for both passes), and
  2. FIRMS has at least one of its detections, unfiltered, in the study box on that date and pass
     (§7, second row of 2026-11-15: NASA can record a pass that FIRMS does not hold, as for NOAA-20 before
     2018-04-01).
Only units both satellites observed are used to fit or test the conversion (fit.py).

Fallback (rule 7, part 7, as settled in §7 on 2026-11-15): a pass (local solar date and day/night) on which a
satellite has a detection at a time with no granule record of that satellite uses the whole study box as its
unit, observed by that satellite (src = 'fallback', r3 = NULL), in place of its granule units. So does a pass
with detections but no granule units at all. Without a [data] granules_dir (the local check sample) every
pass uses the fallback.

Consistency check (rule 7, part 5, as settled in §7 on 2026-11-15): the cells step stops if more than 0.1 % of
a satellite's detections in the fit years have a granule record at their time but lie outside its footprint.
Detections with no record at their time are missing records, handled by the fallback, and are reported.

Footprints are the 4-corner polygons CMR records in its GEODETIC system: corners joined by great circles.
Containment is tested on the sphere (inside every edge's great circle), so footprints over a pole or across
the antimeridian need no special case. The step stops on a footprint that is not convex.
"""
import datetime as dt
import json
import time
import urllib.parse
import urllib.request

import h3
import numpy as np
import pandas as pd

from .config import Config

CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
# Version 061 MODIS swath fire products and version 002 VIIRS 375 m ones (rule 7, part 1).
COLLECTIONS = {"terra": "C2271754179-LPCLOUD", "aqua": "C2278858993-LPCLOUD",
               "snpp": "C2734202914-LPCLOUD", "noaa20": "C2734197957-LPCLOUD"}
FIRST_MONTH = {"aqua": "2002-07", "snpp": "2012-01", "noaa20": "2018-01"}
FLAG = {"DAY": ["D"], "NIGHT": ["N"], "BOTH": ["D", "N"]}
MAX_OUTSIDE = 0.001          # rule 7, part 5
TIME_SLACK = pd.Timedelta(minutes=1)  # FIRMS acquisition times are whole minutes
RECHECK_DAYS = 45            # months ending this recently are downloaded again (records still arriving)


def granule_dir(cfg: Config):
    d = cfg["data"].get("granules_dir")
    return None if d is None else cfg.base / d


def fit_years(cfg: Config) -> range:
    return range(cfg.calibration_years[0], int(cfg["data"]["last_year"]) + 1)


def months(cfg: Config, sat: str) -> list[str]:
    ys = fit_years(cfg)
    out = [f"{y}-{m:02d}" for y in ys for m in range(1, 13)]
    return [m for m in out if m >= FIRST_MONTH.get(sat, "0000")]


# ---- download -------------------------------------------------------------------------------------------

def fetch_month(sat: str, month: str, bbox) -> pd.DataFrame:
    y, m = map(int, month.split("-"))
    end = (dt.date(y, m, 28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    q = {"collection_concept_id": COLLECTIONS[sat], "page_size": 2000,
         "temporal": f"{month}-01T00:00:00Z,{end.isoformat()}T23:59:59Z",
         "bounding_box": ",".join(str(v) for v in bbox)}
    url = f"{CMR}?{urllib.parse.urlencode(q)}"
    rows, after, hits = [], None, None
    while True:
        req = urllib.request.Request(url, headers={"User-Agent": "firecal",
                                                   **({"CMR-Search-After": after} if after else {})})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    body, after, hits = r.read(), r.headers.get("CMR-Search-After"), int(r.headers["CMR-Hits"])
                break
            except OSError:
                if attempt == 3:
                    raise
                time.sleep(5 * (attempt + 1))
        entries = json.loads(body)["feed"]["entry"]
        rows += [{"gid": e["title"], "t0": e["time_start"], "t1": e["time_end"], "flag": e.get("day_night_flag"),
                  "polys": [p[0] for p in e.get("polygons", [])]} for e in entries]
        if not entries or not after or len(rows) >= hits:
            break
    if len(rows) != hits:
        raise SystemExit(f"granules: {sat} {month}: CMR reported {hits} granules but returned {len(rows)}")
    df = pd.DataFrame(rows, columns=["gid", "t0", "t1", "flag", "polys"])
    for c in ("t0", "t1"):
        df[c] = pd.to_datetime(df[c], utc=True).dt.tz_localize(None)
    return df.drop_duplicates("gid").sort_values("t0", ignore_index=True)


def download(cfg: Config) -> None:
    """Fetch each satellite's granule records for the fit years, one month per request; skip months already saved."""
    root = granule_dir(cfg)
    if root is None:
        raise SystemExit("granules: no [data] granules_dir in firecal.toml")
    recent = (dt.date.today() - dt.timedelta(days=RECHECK_DAYS)).strftime("%Y-%m")
    for sat in COLLECTIONS:
        (root / sat).mkdir(parents=True, exist_ok=True)
        for month in months(cfg, sat):
            if month > dt.date.today().strftime("%Y-%m"):
                break
            out = root / sat / f"{month}.parquet"
            if out.exists() and month < recent:
                continue
            t = time.time()
            df = fetch_month(sat, month, cfg.bbox)
            tmp = out.with_suffix(".tmp")
            df.to_parquet(tmp, index=False)
            tmp.replace(out)
            print(f"granules {sat} {month}: {len(df)} ({time.time() - t:.1f} s)", flush=True)
            time.sleep(0.2)


# ---- footprints -----------------------------------------------------------------------------------------

def xyz(lat, lon) -> np.ndarray:
    la, lo = np.radians(np.asarray(lat, float)), np.radians(np.asarray(lon, float))
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], -1)


def rings(polys) -> list[np.ndarray]:
    """CMR polygon strings ("lat lon lat lon ...", closed) -> inward edge normals, one (k, 3) array per ring."""
    out = []
    for p in polys:
        v = np.array(p.split(), dtype=float)
        c = xyz(v[0::2], v[1::2])
        normals = np.cross(c[:-1], c[1:])
        centre = c[:-1].sum(0)
        s = normals @ centre
        if not ((s > 0).all() or (s < 0).all()):
            raise SystemExit(f"granules: footprint is not convex, not handled: {p[:80]}")
        out.append(normals * np.sign(s[0]))
    return out


def inside(points: np.ndarray, normals: np.ndarray) -> np.ndarray:
    """Points (n, 3) inside a convex spherical polygon given by its inward edge normals."""
    return (points @ normals.T >= 0).all(-1)


def universe(cfg: Config) -> pd.DataFrame:
    """Resolution-3 cells that can hold a study-box detection: those covering the box plus a 1-degree margin."""
    w, s, e, n = cfg.bbox
    poly = h3.LatLngPoly([(s - 1, w - 1), (s - 1, e + 1), (n + 1, e + 1), (n + 1, w - 1)])
    cells = sorted(h3.polygon_to_cells(poly, 3))
    ll = np.array([h3.cell_to_latlng(c) for c in cells])
    return pd.DataFrame({"r3": cells, "lat": ll[:, 0], "lon": ll[:, 1]})


def load_month_files(cfg: Config, sat: str) -> pd.DataFrame:
    root = granule_dir(cfg) / sat
    missing = [m for m in months(cfg, sat) if not (root / f"{m}.parquet").exists()
               and m <= dt.date.today().strftime("%Y-%m")]
    if missing:
        raise SystemExit(f"granules: {len(missing)} {sat} months not downloaded (first {missing[0]}); "
                         "run `python -m firecal_pipeline granules`")
    files = [root / f"{m}.parquet" for m in months(cfg, sat) if (root / f"{m}.parquet").exists()]
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True).drop_duplicates("gid")


def granule_units(g: pd.DataFrame, u: pd.DataFrame) -> pd.DataFrame:
    """(r3, d, dn) units whose cell centre lies in a granule footprint, local date from the granule mid-time."""
    out_r, out_t, out_lon, out_dn = [], [], [], []
    mid = (g.t0 + (g.t1 - g.t0) / 2).to_numpy()
    pts = xyz(u.lat.values, u.lon.values)
    for i, (polys, flag) in enumerate(zip(g.polys, g.flag)):
        hit = np.zeros(len(u), bool)
        for normals in rings(polys):
            hit |= inside(pts, normals)
        idx = np.flatnonzero(hit)
        for dn in FLAG.get(flag, []):
            out_r.append(idx), out_t.append(np.full(len(idx), mid[i])), out_lon.append(u.lon.values[idx])
            out_dn.append(np.full(len(idx), dn))
    if not out_r:
        return pd.DataFrame(columns=["r3", "d", "dn"])
    r = np.concatenate(out_r)
    t = pd.to_datetime(np.concatenate(out_t)) + pd.to_timedelta(np.round(np.concatenate(out_lon) / 15 * 3600), unit="s")
    return pd.DataFrame({"r3": u.r3.values[r], "d": t.normalize().date, "dn": np.concatenate(out_dn)}).drop_duplicates()


def footprint_check(g: pd.DataFrame, det: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """For detections (acq_utc, lat, lon, sorted by time): whether a granule record exists at their time, and
    whether they lie inside the footprint of one.

    FIRMS gives whole-minute times, so a detection is checked against every granule whose time window
    (widened by a minute) contains it."""
    g = g.assign(t0s=g.t0 - TIME_SLACK, t1s=g.t1 + TIME_SLACK).sort_values("t0s", ignore_index=True)
    rec, ok = np.zeros(len(det), bool), np.zeros(len(det), bool)
    t = det.acq_utc.to_numpy()
    pts = xyz(det.lat.values, det.lon.values)
    for gi in range(len(g)):
        lo, hi = np.searchsorted(t, [g.t0s[gi].to_datetime64(), g.t1s[gi].to_datetime64()], side="left")
        if lo == hi:
            continue
        sl = slice(lo, hi)
        rec[sl] = True
        for normals in rings(g.polys[gi]):
            ok[sl] |= inside(pts[sl], normals)
    return rec, ok


def build(cfg: Config, con, silver) -> None:
    """Write silver/observed.parquet; stop if the footprint consistency check fails."""
    ys = fit_years(cfg)
    con.execute(f"""CREATE OR REPLACE TABLE passes AS
                    SELECT sat, local_date AS d, dn FROM b
                    WHERE year(local_date) BETWEEN {ys[0]} AND {ys[-1]} GROUP BY ALL""")
    con.execute("CREATE OR REPLACE TABLE obs(sat VARCHAR, r3 VARCHAR, d DATE, dn VARCHAR, src VARCHAR)")
    con.execute("CREATE OR REPLACE TABLE norecord(sat VARCHAR, d DATE, dn VARCHAR)")
    if granule_dir(cfg) is None:
        print("observed: no granules_dir; every pass uses the whole-box fallback", flush=True)
    else:
        u = universe(cfg)
        for sat in COLLECTIONS:
            g = load_month_files(cfg, sat)
            t = time.time()
            units = granule_units(g, u)
            det = con.execute(f"""SELECT acq_utc, lat, lon, local_date AS d, dn FROM b WHERE sat = '{sat}'
                                  AND year(local_date) BETWEEN {ys[0]} AND {ys[-1]} ORDER BY acq_utc""").df()
            rec, ok = footprint_check(g, det)
            n, bad, missing = len(det), int((rec & ~ok).sum()), det[~rec]
            print(f"observed {sat}: {len(g)} granules, {len(units)} units; of {n} detections, {bad} "
                  f"({100 * bad / max(n, 1):.4f} %) outside the footprint of their granule, {len(missing)} with no "
                  f"granule record at their time ({time.time() - t:.0f} s)", flush=True)
            if n and bad / n > MAX_OUTSIDE:
                raise SystemExit(f"observed: {sat} has more than {100 * MAX_OUTSIDE} % of detections outside its "
                                 "granule footprints (PREREGISTRATION.md §7, rule 7 part 5); investigate before fitting")
            con.register("units_df", units.assign(sat=sat))
            con.execute("INSERT INTO obs SELECT sat, r3, CAST(d AS DATE), dn, 'granule' FROM units_df")
            con.register("missing_df", missing[["d", "dn"]].drop_duplicates().assign(sat=sat))
            con.execute("INSERT INTO norecord SELECT sat, CAST(d AS DATE), dn FROM missing_df")
    # Fallback: passes with a detection lacking a granule record, or with detections but no granule units.
    con.execute("DELETE FROM obs WHERE (sat, d, dn) IN (SELECT (sat, d, dn) FROM norecord)")
    # Condition 2: FIRMS holds the pass.
    con.execute("DELETE FROM obs WHERE (sat, d, dn) NOT IN (SELECT (sat, d, dn) FROM passes)")
    con.execute("""INSERT INTO obs SELECT p.sat, NULL, p.d, p.dn, 'fallback' FROM passes p
                   WHERE NOT EXISTS (SELECT 1 FROM obs o WHERE o.sat = p.sat AND o.d = p.d AND o.dn = p.dn)""")
    for row in con.execute("""SELECT sat, src, count(*), count(DISTINCT (d, dn)) FROM obs
                              GROUP BY ALL ORDER BY sat, src""").fetchall():
        print("observed", *row, flush=True)
    con.execute(f"COPY (SELECT * FROM obs ORDER BY sat, d, dn, r3) TO '{silver}/observed.parquet' "
                "(FORMAT parquet, COMPRESSION zstd)")
