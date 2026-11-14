"""FIRMS yearly zips -> bronze Parquet, one file per product and year.

Bronze keeps every hotspot inside the clip box (filtered or not, so outage detection can see
raw detections) with one schema for all products:

    sat, lat, lon, acq_utc, local_date, dn, frp, confidence, type, keep, cell8
"""
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


def keep_expr(cfg: Config, product: str) -> str:
    f = cfg["filters"]
    parts = ["type = 0"] if f["vegetation_only"] else []
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


def run(cfg: Config, force: bool = False) -> None:
    first, last = cfg["data"]["first_year"], cfg["data"]["last_year"]
    for product, (start, _) in PRODUCTS.items():
        for year in range(max(first, start), last + 1):
            ingest_year(cfg, product, year, force)
