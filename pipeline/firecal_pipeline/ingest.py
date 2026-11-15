"""FIRMS yearly zips -> bronze Parquet, one file per product and year.

Bronze keeps every hotspot inside the clip box (filtered or not, so outage detection can see
raw detections) with one schema for all products:

    sat, lat, lon, acq_utc, local_date, dn, frp, confidence, type, keep, cell8

Recent days (after [data] last_year) come from the FIRMS area API files written by download.py and
go to bronze/{product}/recent.parquet. Near-real-time files have no FIRMS `type` column, so for
those rows `type` stays null and the vegetation filter uses a stand-in: a res-8 cell is treated as
a static or non-vegetation source when at least half of its archive detections had a non-zero
`type` (bronze/static_cells.parquet). Tested by building the mask from 2012-2022 and applying it to
2023-2025 VIIRS: it removes 83 % of the detections `type` removes and wrongly drops 0.2 % of
vegetation-fire detections.

bronze/recent.json records, per satellite, the last local solar date with complete data: the
newest UTC day FIRMS has for that source is still filling in, and a local date needs the UTC
morning after it, so the last complete local date is two days before the newest UTC date.
"""
import datetime as dt
import json
import pathlib
import shutil
import tempfile
import zipfile

from .config import Config, connect

PRODUCTS = {  # product -> (first year, satellite expression)
    "modis": (2000, "CASE satellite WHEN 'Aqua' THEN 'aqua' WHEN 'Terra' THEN 'terra' END"),
    "viirs-snpp": (2012, "'snpp'"),
    "viirs-jpss1": (2018, "'noaa20'"),
}


def extract_csv(z: zipfile.ZipFile, name: str, tmp: str) -> pathlib.Path:
    """Copy one zip member to a fixed file name inside tmp.

    The member's name is never used as a path or placed in SQL, so names like '../x' or
    names containing quotes are harmless.
    """
    dest = pathlib.Path(tmp) / "member.csv"
    with z.open(name) as src, open(dest, "wb") as out:
        shutil.copyfileobj(src, out)
    return dest


STATIC_SHARE = 0.5  # a cell is "static" when at least this share of its archive detections had type != 0


def keep_expr(cfg: Config, product: str, type_col: str = "type") -> str:
    f = cfg["filters"]
    parts = [f"{type_col} = 0"] if f["vegetation_only"] else []
    if product == "modis":
        parts.append(f"TRY_CAST(confidence AS INT) >= {int(f['modis_min_confidence'])}")
    else:
        levels = ", ".join(f"'{c}'" for c in f["viirs_confidence"] if c.isalpha())
        parts.append(f"lower(confidence) IN ({levels})")
    return " AND ".join(parts) or "TRUE"


def ingest_year(cfg: Config, product: str, year: int, force: bool = False) -> pathlib.Path | None:
    zpath = cfg.raw_dir / f"{product}_{year}_all_countries.zip"
    out = cfg.dir(f"bronze/{product}") / f"{year}.parquet"
    if out.exists() and not force:
        return out
    if not zpath.exists():
        return None
    x0, y0, x1, y1 = (float(v) for v in cfg.bbox)
    res = int(cfg["grid"]["celldays_resolution"])
    sat = PRODUCTS[product][1]
    keep = keep_expr(cfg, product)
    countries = cfg["data"]["countries"]
    con = connect()
    con.execute("""CREATE TABLE b(sat VARCHAR, lat DOUBLE, lon DOUBLE, acq_utc TIMESTAMP, local_date DATE,
                   dn VARCHAR, frp DOUBLE, confidence VARCHAR, type INTEGER, keep BOOLEAN, cell8 UBIGINT)""")
    with zipfile.ZipFile(zpath) as z, tempfile.TemporaryDirectory() as tmp:
        for name in z.namelist():
            if not any(name.endswith(f"_{c}.csv") for c in countries):
                continue
            p = extract_csv(z, name, tmp)
            con.execute(f"""
                INSERT INTO b
                SELECT {sat}, latitude, longitude, t,
                       CAST(t + to_seconds(CAST(round(longitude / 15.0 * 3600) AS BIGINT)) AS DATE),
                       daynight, frp, confidence, type, {keep},
                       h3_latlng_to_cell(latitude, longitude, {res})
                FROM (SELECT *, strptime(acq_date || ' ' || lpad(acq_time, 4, '0'), '%Y-%m-%d %H%M') AS t
                      FROM read_csv('{p}', header = true,
                           types = {{'acq_time': 'VARCHAR', 'acq_date': 'VARCHAR', 'confidence': 'VARCHAR',
                                     'satellite': 'VARCHAR', 'daynight': 'VARCHAR', 'type': 'INTEGER'}}))
                WHERE longitude BETWEEN {x0} AND {x1} AND latitude BETWEEN {y0} AND {y1}""")
    con.execute(f"""COPY (SELECT DISTINCT * FROM b WHERE sat IS NOT NULL ORDER BY acq_utc)
                    TO '{out}' (FORMAT parquet, COMPRESSION zstd)""")
    n = con.execute("SELECT count(*) FROM b").fetchone()[0]
    print(f"bronze {product} {year}: {n:,} rows", flush=True)
    return out


def static_cells(cfg: Config) -> pathlib.Path:
    """Res-8 cells whose archive detections were mostly non-vegetation (FIRMS type 1, 2 or 3)."""
    bronze, last = cfg.out / "bronze", int(cfg["data"]["last_year"])
    out = bronze / "static_cells.parquet"
    years = [p for p in bronze.glob("*/[0-9]*.parquet") if int(p.stem) <= last]
    con = connect()
    files = ", ".join(f"'{p}'" for p in sorted(years))
    con.execute(f"""COPY (SELECT cell8 FROM read_parquet([{files}]) GROUP BY cell8
                          HAVING avg((type <> 0)::INT) >= {STATIC_SHARE} ORDER BY cell8)
                    TO '{out}' (FORMAT parquet)""")
    return out


def ingest_recent(cfg: Config, product: str, availability: dict, static: pathlib.Path) -> tuple[list[str], str] | None:
    """FIRMS area API CSVs -> bronze/{product}/recent.parquet. Returns (satellites, last complete local date)."""
    files = sorted((cfg.out / "firms_api" / product).glob("*.csv"))
    if not files:
        return None
    sid = {"modis": "MODIS", "viirs-snpp": "VIIRS_SNPP", "viirs-jpss1": "VIIRS_NOAA20"}[product]
    newest = max(dt.date.fromisoformat(r[1]) for k, r in availability.items() if k.startswith(sid + "_"))
    through = newest - dt.timedelta(days=2)
    x0, y0, x1, y1 = (float(v) for v in cfg.bbox)
    res = int(cfg["grid"]["celldays_resolution"])
    keep = keep_expr(cfg, product, "coalesce(type, CASE WHEN s.cell8 IS NULL THEN 0 ELSE 2 END)")
    out = cfg.dir(f"bronze/{product}") / "recent.parquet"
    con = connect()
    con.execute(f"CREATE TABLE static AS SELECT cell8 FROM '{static}'")
    names = ", ".join(f"'{p}'" for p in files)
    con.execute(f"""
        CREATE TABLE b AS
        WITH raw AS (
            SELECT {PRODUCTS[product][1]} AS sat, latitude AS lat, longitude AS lon, t AS acq_utc,
                   CAST(t + to_seconds(CAST(round(longitude / 15.0 * 3600) AS BIGINT)) AS DATE) AS local_date,
                   daynight AS dn, frp, confidence, TRY_CAST(type AS INTEGER) AS type,
                   h3_latlng_to_cell(latitude, longitude, {res}) AS cell8
            FROM (SELECT *, strptime(acq_date || ' ' || lpad(acq_time, 4, '0'), '%Y-%m-%d %H%M') AS t
                  FROM read_csv([{names}], header = true, union_by_name = true,
                       types = {{'acq_time': 'VARCHAR', 'acq_date': 'VARCHAR', 'confidence': 'VARCHAR',
                                 'satellite': 'VARCHAR', 'daynight': 'VARCHAR'}}))
            WHERE longitude BETWEEN {x0} AND {x1} AND latitude BETWEEN {y0} AND {y1})
        SELECT raw.sat, raw.lat, raw.lon, raw.acq_utc, raw.local_date, raw.dn, raw.frp, raw.confidence, raw.type,
               {keep} AS keep, raw.cell8
        FROM raw LEFT JOIN static s ON s.cell8 = raw.cell8
        WHERE raw.sat IS NOT NULL AND raw.local_date <= DATE '{through}'""")
    con.execute(f"COPY (SELECT DISTINCT * FROM b ORDER BY acq_utc) TO '{out}' (FORMAT parquet, COMPRESSION zstd)")
    n, nrt, sats = con.execute("SELECT count(*), count(*) FILTER (WHERE type IS NULL), list(DISTINCT sat ORDER BY sat) FROM b").fetchone()
    print(f"bronze {product} recent: {n:,} rows ({nrt:,} near-real-time) through {through}", flush=True)
    return sats, through.isoformat()


def run(cfg: Config, force: bool = False) -> None:
    first, last = cfg["data"]["first_year"], cfg["data"]["last_year"]
    for product, (start, _) in PRODUCTS.items():
        for year in range(max(first, start), last + 1):
            ingest_year(cfg, product, year, force)

    bronze = cfg.out / "bronze"
    avail_path = cfg.out / "firms_api" / "availability.json"
    if not avail_path.exists():
        for p in bronze.glob("*/recent.parquet"):
            p.unlink()
        (bronze / "recent.json").unlink(missing_ok=True)
        return
    availability = json.loads(avail_path.read_text())["sources"]
    static = static_cells(cfg)
    through = {}
    for product in PRODUCTS:
        got = ingest_recent(cfg, product, availability, static)
        if got:
            for sat in got[0]:
                through[sat] = got[1]
    (bronze / "recent.json").write_text(json.dumps({"through": through}, indent=1))
