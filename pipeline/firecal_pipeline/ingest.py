"""FIRMS yearly zips -> bronze Parquet, one file per product and year.

Bronze keeps every hotspot inside the clip box (filtered or not, so outage detection can see
raw detections) with one schema for all products:

    sat, lat, lon, acq_utc, local_date, dn, frp, confidence, type, keep, cell8, continent

`continent` comes from the FIRMS country file through [data] continents (the global run,
global/continents.toml; PREREGISTRATION.md §7). Without that setting every row is "study_area".
Recent days from the FIRMS API carry no country. With continents set, each recent row takes the
continent its res-6 cell had most often in the archive (bronze/continent_cells.parquet), falling back
to the res-5, 4, 3 and 2 parents for places that never burned before; rows matching none are dropped,
as the country files hold only land (PREREGISTRATION.md §7, 2026-11-15). Tested on 2025-07-01..05:
vegetation detections per continent were within 0.2 % of the country files. Otherwise they get
"study_area".

Recent days (after [data] last_year) come from the FIRMS area API files written by download.py and
go to bronze/{product}/recent.parquet. Near-real-time files have no FIRMS `type` column, so for
those rows `type` stays null and the vegetation filter uses a stand-in: a res-8 cell is treated as
a static or non-vegetation source when at least half of its archive detections had a non-zero
`type` (bronze/static_cells.parquet). Tested by building the mask from 2012-2022 and applying it to
2023-2025 VIIRS: it removes 83 % of the detections `type` removes and wrongly drops 0.2 % of
vegetation-fire detections.

MODIS rows from first_year to [data] modis_labels_through (2017) take their `type` from the
producer's MCD14ML Collection 6 version 3 monthly files in [data] modis_labels_dir, matched on UTC
time, satellite, latitude and longitude (PREREGISTRATION.md section 7, 2026-11-15). The FIRMS
archive rows for those years carry version-2 labels; from 2018 they are already version 3. A year
stops with an error when under 99.9 % of its rows find a match.

bronze/recent.json records, per satellite, the last local solar date with complete data: the
newest UTC day FIRMS has for that source is still filling in, and a local date needs the UTC
morning after it, so the last complete local date is two days before the newest UTC date.
"""
import datetime as dt
import json
import pathlib
import shutil
import tempfile
import tomllib
import zipfile

import pandas as pd

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


MIN_LABEL_MATCH = 0.999  # share of a year's FIRMS MODIS rows that must find a version-3 label
LABEL_SAT = {"T": "terra", "A": "aqua"}


def label_dir(cfg: Config) -> pathlib.Path | None:
    d = cfg["data"].get("modis_labels_dir")
    return cfg.base / d if d else None


def month_labels(src: pathlib.Path, cache: pathlib.Path) -> pathlib.Path:
    """One MCD14ML monthly file (space-separated text) -> Parquet with the match key and `type`."""
    out = cache / (src.name.split(".txt")[0] + ".parquet")
    if out.exists():
        return out
    df = pd.read_csv(src, sep=r"\s+", usecols=["YYYYMMDD", "HHMM", "sat", "lat", "lon", "type"],
                     dtype={"YYYYMMDD": str, "HHMM": str, "sat": str, "lat": float, "lon": float, "type": "int8"})
    df = pd.DataFrame({
        "sat": df.sat.map(LABEL_SAT),
        "acq_utc": pd.to_datetime(df.YYYYMMDD + df.HHMM.str.zfill(4), format="%Y%m%d%H%M"),
        "lat": df.lat.round(4), "lon": df.lon.round(4), "type": df.type})
    tmp = out.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.rename(out)
    return out


def relabel_modis(cfg: Config, con, year: int) -> None:
    """Replace `type` (and `keep`) in table b with the version-3 labels for that year."""
    d = label_dir(cfg)
    files = sorted(d.glob(f"MCD14ML.{year}[0-9][0-9].006.03.txt.gz")) if d else []
    if not files:
        raise SystemExit(f"No MCD14ML version-3 files for {year} in {d}: download them first (README, MODIS labels).")
    cache = d / "labels"  # beside the downloads: bronze/*/ must hold only bronze tables
    cache.mkdir(exist_ok=True)
    parquet = ", ".join(f"'{month_labels(f, cache)}'" for f in files)
    x0, y0, x1, y1 = (float(v) for v in cfg.bbox)
    con.execute(f"""CREATE TEMP TABLE lab AS
        SELECT sat, acq_utc, lat, lon, min(type) AS type, count(DISTINCT type) AS ntypes FROM read_parquet([{parquet}])
        WHERE lon BETWEEN {x0 - 0.01} AND {x1 + 0.01} AND lat BETWEEN {y0 - 0.01} AND {y1 + 0.01}
        GROUP BY ALL""")
    total, matched, changed, ambiguous = con.execute("""
        SELECT count(*), count(l.type), count(*) FILTER (WHERE l.type IS DISTINCT FROM b.type AND l.type IS NOT NULL),
               count(*) FILTER (WHERE l.ntypes > 1)
        FROM b LEFT JOIN lab l ON l.sat = b.sat AND l.acq_utc = b.acq_utc AND l.lat = round(b.lat, 4) AND l.lon = round(b.lon, 4)
        WHERE b.sat IS NOT NULL""").fetchone()
    share = matched / total if total else 1.0
    print(f"modis labels {year}: {matched:,} of {total:,} rows matched ({100 * share:.3f} %), "
          f"{changed:,} type changed, {ambiguous:,} ambiguous", flush=True)
    if ambiguous:  # two label rows with the same key but different types: never pick one silently
        raise SystemExit(f"modis labels {year}: {ambiguous:,} rows match label rows that disagree on type; stopping.")
    if share < MIN_LABEL_MATCH:
        raise SystemExit(f"modis labels {year}: only {100 * share:.3f} % of rows matched (need {100 * MIN_LABEL_MATCH} %); stopping.")
    con.execute(f"""UPDATE b SET type = l.type FROM lab l
        WHERE l.sat = b.sat AND l.acq_utc = b.acq_utc AND l.lat = round(b.lat, 4) AND l.lon = round(b.lon, 4)""")
    con.execute(f"UPDATE b SET keep = {keep_expr(cfg, 'modis')}")
    con.execute("DROP TABLE lab")


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


STUDY_AREA = "study_area"


def continents(cfg: Config) -> dict | None:
    """The continent table, or None when the run has a single study area."""
    name = cfg["data"].get("continents")
    return None if name is None else tomllib.loads((cfg.base / name).read_text())


def file_country(name: str, product: str, year: int) -> str:
    return pathlib.PurePosixPath(name).name.removeprefix(f"{product}_{year}_").removesuffix(".csv")


def continent_sql(table: dict | None, country: str) -> str:
    """SQL for one country file's continent (the split countries by longitude)."""
    if table is None:
        return f"'{STUDY_AREA}'"
    split = table.get("split_at_lon", {}).get(country)
    if split:
        return f"CASE WHEN longitude < {float(split['lon'])} THEN '{split['west']}' ELSE '{split['east']}' END"
    for cont, names in table["continent"].items():
        if country in names:
            return f"'{cont}'"
    raise SystemExit(f"ingest: country file {country!r} has no continent in {table and 'continents.toml'}")


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
    table = continents(cfg)
    con = connect()
    con.execute("""CREATE TABLE b(sat VARCHAR, lat DOUBLE, lon DOUBLE, acq_utc TIMESTAMP, local_date DATE,
                   dn VARCHAR, frp DOUBLE, confidence VARCHAR, type INTEGER, keep BOOLEAN, cell8 UBIGINT,
                   continent VARCHAR)""")
    with zipfile.ZipFile(zpath) as z, tempfile.TemporaryDirectory() as tmp:
        for name in z.namelist():
            if not name.endswith(".csv"):
                continue
            country = file_country(name, product, year)
            if countries != "all" and country not in countries:
                continue
            p = extract_csv(z, name, tmp)
            con.execute(f"""
                INSERT INTO b
                SELECT {sat}, latitude, longitude, t,
                       CAST(t + to_seconds(CAST(round(longitude / 15.0 * 3600) AS BIGINT)) AS DATE),
                       daynight, frp, confidence, type, {keep},
                       h3_latlng_to_cell(latitude, longitude, {res}), {continent_sql(table, country)}
                FROM (SELECT *, strptime(acq_date || ' ' || lpad(acq_time, 4, '0'), '%Y-%m-%d %H%M') AS t
                      FROM read_csv('{p}', header = true,
                           types = {{'acq_time': 'VARCHAR', 'acq_date': 'VARCHAR', 'confidence': 'VARCHAR',
                                     'satellite': 'VARCHAR', 'daynight': 'VARCHAR', 'type': 'INTEGER'}}))
                WHERE longitude BETWEEN {x0} AND {x1} AND latitude BETWEEN {y0} AND {y1}""")
    if product == "modis" and year <= int(cfg["data"].get("modis_labels_through", 0)):
        relabel_modis(cfg, con, year)
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


LOOKUP_RES = (6, 5, 4, 3, 2)  # recent rows' continent: the finest of these levels the archive has seen


def continent_cells(cfg: Config) -> pathlib.Path:
    """res, cell, continent: each cell's most frequent continent in the archive at LOOKUP_RES levels."""
    bronze, last = cfg.out / "bronze", int(cfg["data"]["last_year"])
    out = bronze / "continent_cells.parquet"
    years = [p for p in bronze.glob("*/[0-9]*.parquet") if int(p.stem) <= last]
    files = ", ".join(f"'{p}'" for p in sorted(years))
    levels = ", ".join(f"({r})" for r in LOOKUP_RES)
    con = connect()
    con.execute(f"""COPY (
        WITH c6 AS (SELECT h3_cell_to_parent(cell8, 6) AS c6, continent, count(*) AS n
                    FROM read_parquet([{files}]) GROUP BY ALL),
             u AS (SELECT v.r AS res, h3_cell_to_parent(c6, v.r) AS cell, continent, sum(n) AS n
                   FROM c6, (VALUES {levels}) v(r) GROUP BY ALL)
        SELECT res, cell, continent FROM u
        QUALIFY row_number() OVER (PARTITION BY res, cell ORDER BY n DESC, continent) = 1
        ORDER BY res, cell) TO '{out}' (FORMAT parquet)""")
    return out


def ingest_recent(cfg: Config, product: str, availability: dict, static: pathlib.Path,
                  lookup: pathlib.Path | None = None) -> tuple[list[str], str] | None:
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
    if lookup:
        con.execute(f"CREATE TABLE lk AS SELECT * FROM '{lookup}'")
        joins = " ".join(f"LEFT JOIN lk k{r} ON k{r}.res = {r} AND k{r}.cell = h3_cell_to_parent(raw.cell8, {r})"
                         for r in LOOKUP_RES)
        continent = "coalesce(" + ", ".join(f"k{r}.continent" for r in LOOKUP_RES) + ")"
    else:
        joins, continent = "", f"'{STUDY_AREA}'"
    names = ", ".join(f"'{p}'" for p in files)
    csv = f"""read_csv([{names}], header = true, union_by_name = true,
                       types = {{'acq_time': 'VARCHAR', 'acq_date': 'VARCHAR', 'confidence': 'VARCHAR',
                                 'satellite': 'VARCHAR', 'daynight': 'VARCHAR'}})"""
    # Only standard-processing files have `type`; when every file is near-real-time the column is absent.
    has_type = "type" in {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {csv}").fetchall()}
    type_col = "TRY_CAST(type AS INTEGER)" if has_type else "CAST(NULL AS INTEGER)"
    con.execute(f"""
        CREATE TABLE b AS
        WITH raw AS (
            SELECT {PRODUCTS[product][1]} AS sat, latitude AS lat, longitude AS lon, t AS acq_utc,
                   CAST(t + to_seconds(CAST(round(longitude / 15.0 * 3600) AS BIGINT)) AS DATE) AS local_date,
                   daynight AS dn, frp, confidence, {type_col} AS type,
                   h3_latlng_to_cell(latitude, longitude, {res}) AS cell8
            FROM (SELECT *, strptime(acq_date || ' ' || lpad(acq_time, 4, '0'), '%Y-%m-%d %H%M') AS t
                  FROM {csv})
            WHERE longitude BETWEEN {x0} AND {x1} AND latitude BETWEEN {y0} AND {y1})
        SELECT raw.sat, raw.lat, raw.lon, raw.acq_utc, raw.local_date, raw.dn, raw.frp, raw.confidence, raw.type,
               {keep} AS keep, raw.cell8, {continent} AS continent
        FROM raw LEFT JOIN static s ON s.cell8 = raw.cell8 {joins}
        WHERE raw.sat IS NOT NULL AND raw.local_date <= DATE '{through}'""")
    if lookup:
        n_all = con.execute(f"SELECT count(*) FROM b").fetchone()[0]
        con.execute("DELETE FROM b WHERE continent IS NULL")
        n_off = n_all - con.execute("SELECT count(*) FROM b").fetchone()[0]
        print(f"bronze {product} recent: {n_off:,} rows in no archive continent dropped", flush=True)
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
    lookup = continent_cells(cfg) if continents(cfg) else None
    through = {}
    for product in PRODUCTS:
        got = ingest_recent(cfg, product, availability, static, lookup)
        if got:
            for sat in got[0]:
                through[sat] = got[1]
    (bronze / "recent.json").write_text(json.dumps({"through": through}, indent=1))
