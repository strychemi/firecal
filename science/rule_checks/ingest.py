"""Build H3 cell-day tables for the rule checks (Aqua MODIS and S-NPP VIIRS, 2012-2025).

Region: the exploratory box around Argentina, so the global data stay unexamined.
Unit: burning cell-day = (H3 res-8 cell, local solar date, day/night) with >= 1 hotspot.
Run: uv run --python 3.13 --with duckdb ingest.py
"""
import pathlib, tempfile, zipfile
import duckdb

from zips import extract_csv


ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "data"
OUT = ROOT / "data" / "derived" / "rule_checks"
OUT.mkdir(parents=True, exist_ok=True)
BBOX = (-76.0, -56.0, -50.0, -20.0)  # min_lon, min_lat, max_lon, max_lat
COUNTRIES = ["Argentina", "Bolivia", "Brazil", "Chile", "Paraguay", "Uruguay", "Falkland"]
YEARS = range(2012, 2026)
H3_RES = 8

con = duckdb.connect(str(OUT / "cells.duckdb"))
con.execute("INSTALL h3 FROM community; LOAD h3;")
con.execute("""CREATE OR REPLACE TABLE cellday(
  sat VARCHAR, d DATE, dn VARCHAR, cell UBIGINT, keep BOOLEAN)""")

def load(zip_path, family):
    with zipfile.ZipFile(zip_path) as z, tempfile.TemporaryDirectory() as tmp:
        for name in z.namelist():
            if not name.endswith(".csv") or not any(c in name for c in COUNTRIES):
                continue
            p = extract_csv(z, name, tmp)
            if family == "modis":
                sat = "CASE satellite WHEN 'Aqua' THEN 'aqua' ELSE 'terra' END"
                keep = "type = 0 AND TRY_CAST(confidence AS INT) >= 30"
            else:
                sat = "'snpp'"
                keep = "type = 0 AND lower(confidence) IN ('n', 'h')"
            con.execute(f"""
              INSERT INTO cellday
              SELECT sat, d, dn, cell, bool_or(keep) FROM (
                SELECT {sat} AS sat,
                  CAST(strptime(acq_date || ' ' || lpad(acq_time, 4, '0'), '%Y-%m-%d %H%M')
                       + to_seconds(CAST(round(longitude / 15.0 * 3600) AS BIGINT)) AS DATE) AS d,
                  daynight AS dn,
                  h3_latlng_to_cell(latitude, longitude, {H3_RES}) AS cell,
                  ({keep}) AS keep
                FROM read_csv('{p}', header=true, types={{'acq_time':'VARCHAR','confidence':'VARCHAR',
                     'acq_date':'VARCHAR','satellite':'VARCHAR','daynight':'VARCHAR'}})
                WHERE longitude BETWEEN {BBOX[0]} AND {BBOX[2]} AND latitude BETWEEN {BBOX[1]} AND {BBOX[3]}
              ) WHERE sat <> 'terra' GROUP BY ALL""")

for y in YEARS:
    for family in ("modis", "viirs-snpp"):
        load(RAW / f"{family}_{y}_all_countries.zip", "modis" if family == "modis" else "viirs")
    print(y, con.execute("SELECT count(*) FROM cellday").fetchone()[0], flush=True)

# Daily presence (any raw detection in the box): used to find outage days and matched days.
con.execute("""CREATE OR REPLACE TABLE presence AS
  SELECT sat, d, count(*) AS n_cells FROM cellday GROUP BY ALL""")
# Monthly counts on matched days only, per res-3 stratum and 2-degree block.
con.execute("""CREATE OR REPLACE TABLE monthly AS
  WITH matched AS (SELECT d FROM presence GROUP BY d HAVING count(DISTINCT sat) = 2)
  SELECT sat, year(d) AS y, month(d) AS m, dn,
    h3_cell_to_parent(cell, 3) AS r3, h3_cell_to_parent(cell, 2) AS r2,
    CAST(floor(h3_cell_to_lat(cell) / 2) AS INT) AS blat, CAST(floor(h3_cell_to_lng(cell) / 2) AS INT) AS blon,
    count(*) AS n
  FROM (SELECT DISTINCT sat, d, dn, cell FROM cellday WHERE keep) JOIN matched USING (d)
  GROUP BY ALL""")
con.execute(f"COPY monthly TO '{OUT / 'monthly.parquet'}' (FORMAT parquet)")
con.execute(f"COPY presence TO '{OUT / 'presence.parquet'}' (FORMAT parquet)")
print(con.execute("SELECT sat, dn, sum(n) FROM monthly WHERE y BETWEEN 2013 AND 2022 GROUP BY ALL ORDER BY ALL").fetchall())
