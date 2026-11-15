"""Build the local check sample: real FIRMS rows for a small box near the Paraná Delta.

Built from a full local build (needs data/bronze and data/firms_api). The output is git-ignored, so
no FIRMS data goes into the repo:

    raw/{product}_{year}_all_countries.zip   archive years, in the FIRMS zip layout (one Argentina file)
    raw/firms_api/                            recent days from RECENT_FROM, as the download step writes them
                                              (enough for the near-real-time path and the in-progress month)

scripts/check.sh builds it when missing, copies raw/firms_api to out/, runs ingest -> cells -> fit ->
publish with FIRECAL_ROOT set to this folder, and compares the Rust API with the Python reference
(tests/test_api_parity.py).
"""
import json
import pathlib
import shutil
import tomllib
import zipfile

import duckdb

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
RECENT_FROM = "2026-10-01"
SATELLITE = {"terra": "Terra", "aqua": "Aqua", "snpp": "N", "noaa20": "N20"}


def main() -> None:
    x0, y0, x1, y1 = tomllib.loads((HERE / "firecal.toml").read_text())["data"]["clip_bbox"]
    src, raw = REPO / "data", HERE / "raw"
    shutil.rmtree(raw, ignore_errors=True)
    (raw / "firms_api").mkdir(parents=True)
    con = duckdb.connect()
    sat = "CASE sat " + " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in SATELLITE.items()) + " END"
    for path in sorted((src / "bronze").glob("*/[0-9]*.parquet")):
        product, year = path.parent.name, path.stem
        rows = con.execute(f"""
            SELECT round(lat, 5) AS latitude, round(lon, 5) AS longitude, strftime(acq_utc, '%Y-%m-%d') AS acq_date,
                   strftime(acq_utc, '%H%M') AS acq_time, {sat} AS satellite, confidence, dn AS daynight, frp, type
            FROM '{path}' WHERE lon BETWEEN {x0} AND {x1} AND lat BETWEEN {y0} AND {y1} ORDER BY acq_utc, lat, lon""").df()
        name = f"{product}/{year}/{product}_{year}_Argentina.csv"
        with zipfile.ZipFile(raw / f"{product}_{year}_all_countries.zip", "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            z.writestr(name, rows.to_csv(index=False))
    for product_dir in sorted(p for p in (src / "firms_api").iterdir() if p.is_dir()):
        out = raw / "firms_api" / product_dir.name
        out.mkdir()
        for f in sorted(f for f in product_dir.glob("*.csv") if f.name >= RECENT_FROM):
            lines = f.read_text().splitlines()
            head = lines[0].split(",")
            lat, lon = head.index("latitude"), head.index("longitude")
            keep = [l for l in lines[1:] if l and x0 <= float(l.split(",")[lon]) <= x1 and y0 <= float(l.split(",")[lat]) <= y1]
            (out / f.name).write_text("\n".join([lines[0], *keep]) + "\n")
    avail = json.loads((src / "firms_api" / "availability.json").read_text())
    (raw / "firms_api" / "availability.json").write_text(json.dumps(avail, indent=1))
    size = sum(p.stat().st_size for p in raw.rglob("*") if p.is_file())
    print(f"sample written to {raw}: {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
