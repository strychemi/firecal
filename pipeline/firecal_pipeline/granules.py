"""Satellite granule records -> which outage-check units each satellite observed (PREREGISTRATION.md §7, 2026-11-15).

A granule is one 5-minute (MODIS) or 6-minute (VIIRS) slice of a satellite's swath. NASA's Common Metadata
Repository (CMR) keeps a public record of every granule of the fire products FIRMS is built from: when it was
observed, its footprint, and whether it is a day pass, night pass or both. No login is needed.

    granules step:  {granules_dir}/{sat}/{YYYY-MM}.parquet   gid, t0, t1, flag, polys
                    (granules touching the study box, or all of them for the global run; one file per
                    satellite and month of the fit years)
    cells step:     silver/observed.parquet                  sat, r3, d, dn
                    silver/passes.parquet                    sat, continent, d, dn, fallback

A satellite observed an outage-check unit (continent, H3 resolution-3 cell r3, local solar date d, pass dn) if
  1. one of its granules for that pass covers the cell's centre during that local solar date (a granule flagged
     BOTH counts for both passes), and
  2. FIRMS has at least one of its detections, unfiltered, in that continent (Argentina: the study box) on that
     date and pass (§7, 2026-11-15: NASA can record a pass that FIRMS does not hold, as for NOAA-20 before
     2018-04-01).
observed.parquet holds condition 1 for units with fire (a burning cell-day of any satellite), the only ones
the fit can use; passes.parquet holds condition 2. Only units both satellites observed are used to fit or
test the conversion (fit.py, fair_ctes).

Fallback (rule 7, part 7, as settled in §7 on 2026-11-15): a pass on which a satellite has a detection in a
continent at a time with no granule record of that satellite uses the whole continent as its unit, observed by
that satellite (passes.fallback). So does a pass on which the satellite has detections but no granule units.
Without a [data] granules_dir (the local check sample) every pass uses the fallback.

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
         "temporal": f"{month}-01T00:00:00Z,{end.isoformat()}T23:59:59Z"}
    if [float(v) for v in bbox] != [-180.0, -90.0, 180.0, 90.0]:  # the whole globe needs no spatial filter
        q["bounding_box"] = ",".join(str(v) for v in bbox)
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


def load_year(cfg: Config, sat: str, year: int) -> pd.DataFrame:
    """A satellite's granule records for one year (plus the last day of the year before, for local dates)."""
    root = granule_dir(cfg) / sat
    want = [m for m in months(cfg, sat) if m.startswith(f"{year}-") and m <= dt.date.today().strftime("%Y-%m")]
    missing = [m for m in want if not (root / f"{m}.parquet").exists()]
    if missing:
        raise SystemExit(f"granules: {len(missing)} {sat} months not downloaded (first {missing[0]}); "
                         "run `python -m firecal_pipeline granules`")
    files = [root / f"{m}.parquet" for m in want + [f"{year - 1}-12", f"{year + 1}-01"] if (root / f"{m}.parquet").exists()]
    if not files:
        return pd.DataFrame(columns=["gid", "t0", "t1", "flag", "polys"])
    g = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True).drop_duplicates("gid")
    lo, hi = pd.Timestamp(year - 1, 12, 31), pd.Timestamp(year + 1, 1, 2)
    return g[(g.t1 >= lo) & (g.t0 < hi)].sort_values("t0", ignore_index=True)


def hits(pts: np.ndarray, polys: list, use: np.ndarray, chunk: int = 128) -> tuple[np.ndarray, np.ndarray]:
    """(point index, granule index) pairs with the point inside the granule's footprint.

    Footprints are all 4-corner quadrilaterals, so a chunk of granules is tested against every point in one
    matrix product: a point is inside when it is on the inner side of all four edge great circles."""
    rs = [rings(p) for p in polys]
    quad = all(len(r) == 1 and len(r[0]) == 4 for r in rs)
    out_c, out_g = [], []
    if quad:
        n = np.stack([r[0] for r in rs]).astype(np.float32)          # (G, 4, 3)
        p32 = pts.astype(np.float32)
        for a in range(0, len(n), chunk):
            m = (p32 @ n[a:a + chunk].reshape(-1, 3).T).reshape(len(pts), -1, 4)
            c, g = np.nonzero((m >= 0).all(-1))
            out_c.append(c), out_g.append(g + a)
    else:
        for g, r in enumerate(rs):
            hit = np.zeros(len(pts), bool)
            for normals in r:
                hit |= inside(pts, normals)
            c = np.flatnonzero(hit)
            out_c.append(c), out_g.append(np.full(len(c), g))
    c, g = np.concatenate(out_c), np.concatenate(out_g)
    keep = use[g]
    return c[keep], g[keep]


def granule_units(g: pd.DataFrame, fire: pd.DataFrame) -> pd.DataFrame:
    """Units (r3, d, dn) with fire whose cell centre lies in a granule footprint.

    `fire` holds the resolution-3 cells (r3, lat, lon of the centre) and local dates d that have a burning
    cell-day of any satellite; only those units can enter the fit. Granules are handled one UTC day at a time
    against the fire cells of the local dates that day can reach; the local date of a hit is the granule
    mid-time shifted by the cell's longitude."""
    if g.empty or fire.empty:
        return pd.DataFrame({"r3": pd.Series(dtype="uint64"), "d": pd.Series(dtype="object"), "dn": pd.Series(dtype="object")})
    mid = g.t0 + (g.t1 - g.t0) / 2
    out = []
    fire_d = fire.assign(day=pd.to_datetime(fire.d))
    for day, gd in g.groupby(mid.dt.normalize()):
        cand = fire_d[(fire_d.day >= day - pd.Timedelta(days=1)) & (fire_d.day <= day + pd.Timedelta(days=1))]
        if cand.empty:
            continue
        cells = cand.drop_duplicates("r3")
        pts = xyz(cells.lat.values, cells.lon.values)
        c, gi = hits(pts, list(gd.polys), gd.flag.isin(list(FLAG)).to_numpy())
        if not len(c):
            continue
        t = mid.loc[gd.index].to_numpy()[gi] + pd.to_timedelta(np.round(cells.lon.values[c] / 15 * 3600), unit="s").to_numpy()
        h = pd.DataFrame({"r3": cells.r3.values[c], "d": pd.DatetimeIndex(t).normalize(), "flag": gd.flag.to_numpy()[gi]})
        h = h.merge(cand[["r3", "day"]], left_on=["r3", "d"], right_on=["r3", "day"])[["r3", "d", "flag"]]
        for flag, dns in FLAG.items():
            for dn in dns:
                out.append(h[h.flag == flag][["r3", "d"]].assign(dn=dn))
    if not out:
        return granule_units(g.iloc[:0], fire.iloc[:0])
    u = pd.concat(out, ignore_index=True).drop_duplicates()
    return u.assign(d=u.d.dt.date)


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
    """Write silver/observed.parquet and silver/passes.parquet; stop if the footprint consistency check fails.

    observed.parquet  sat, r3, d, dn              granule units with fire (condition 1)
    passes.parquet    sat, continent, d, dn, fallback
                      passes on which FIRMS holds the satellite's data in that continent (condition 2);
                      fallback: the whole continent counts as observed on that pass (rule 7, part 7)
    A satellite observed a unit of a continent if the pass is in passes and either it is a fallback pass or
    the unit is in observed (fit.py)."""
    ys = fit_years(cfg)
    con.execute(f"""CREATE OR REPLACE TABLE passes AS
                    SELECT sat, continent, local_date AS d, dn FROM b
                    WHERE year(local_date) BETWEEN {ys[0]} AND {ys[-1]} GROUP BY ALL""")
    con.execute("CREATE OR REPLACE TABLE obs(sat VARCHAR, r3 UBIGINT, d DATE, dn VARCHAR)")
    con.execute("CREATE OR REPLACE TABLE norecord(sat VARCHAR, continent VARCHAR, d DATE, dn VARCHAR)")
    if granule_dir(cfg) is None:
        print("observed: no granules_dir; every pass uses the whole-area fallback", flush=True)
    else:
        con.execute(f"""CREATE OR REPLACE TABLE fire AS
                        SELECT h3_cell_to_parent(cell8, 3) AS r3, d FROM read_parquet('{silver}/cell_day.parquet')
                        WHERE year(d) BETWEEN {ys[0]} AND {ys[-1]} GROUP BY ALL""")
        for sat in COLLECTIONS:
            n = bad = missing = units = grans = 0
            t = time.time()
            for year in ys:
                g = load_year(cfg, sat, year)
                fire = con.execute(f"""SELECT r3, d, h3_cell_to_lat(r3) AS lat, h3_cell_to_lng(r3) AS lon FROM fire
                                       WHERE d BETWEEN DATE '{year - 1}-12-31' AND DATE '{year + 1}-01-01'""").df()
                u = granule_units(g, fire)
                u = u[pd.to_datetime(u.d).dt.year == year]
                con.register("units_df", u.assign(sat=sat))
                con.execute("INSERT INTO obs SELECT sat, r3, CAST(d AS DATE), dn FROM units_df")
                det = con.execute(f"""SELECT acq_utc, lat, lon, continent, local_date AS d, dn FROM b
                                      WHERE sat = '{sat}' AND year(local_date) = {year} ORDER BY acq_utc""").df()
                rec, ok = footprint_check(g, det)
                m = det[~rec]
                con.register("missing_df", m[["continent", "d", "dn"]].drop_duplicates().assign(sat=sat))
                con.execute("INSERT INTO norecord SELECT sat, continent, CAST(d AS DATE), dn FROM missing_df")
                n, bad, missing = n + len(det), bad + int((rec & ~ok).sum()), missing + len(m)
                units, grans = units + len(u), grans + len(g)
            print(f"observed {sat}: {grans} granules, {units} units with fire; of {n} detections, {bad} "
                  f"({100 * bad / max(n, 1):.4f} %) outside the footprint of their granule, {missing} with no "
                  f"granule record at their time ({time.time() - t:.0f} s)", flush=True)
            if n and bad / n > MAX_OUTSIDE:
                raise SystemExit(f"observed: {sat} has more than {100 * MAX_OUTSIDE} % of detections outside its "
                                 "granule footprints (PREREGISTRATION.md §7, rule 7 part 5); investigate before fitting")
    # Fallback: a pass with a detection lacking a granule record, or a satellite pass with no granule units at all.
    con.execute("""CREATE OR REPLACE TABLE pass AS
                   SELECT p.*, (p.sat, p.continent, p.d, p.dn) IN (SELECT (sat, continent, d, dn) FROM norecord)
                               OR (p.sat, p.d, p.dn) NOT IN (SELECT DISTINCT (sat, d, dn) FROM obs) AS fallback
                   FROM passes p""")
    for row in con.execute("""SELECT sat, count(*), count(*) FILTER (WHERE fallback) FROM pass
                              GROUP BY ALL ORDER BY sat""").fetchall():
        print("passes {}: {} with FIRMS data, {} using the fallback".format(*row), flush=True)
    con.execute(f"COPY (SELECT * FROM obs ORDER BY sat, d, dn, r3) TO '{silver}/observed.parquet' "
                "(FORMAT parquet, COMPRESSION zstd)")
    con.execute(f"COPY (SELECT * FROM pass ORDER BY sat, continent, d, dn) TO '{silver}/passes.parquet' "
                "(FORMAT parquet, COMPRESSION zstd)")
