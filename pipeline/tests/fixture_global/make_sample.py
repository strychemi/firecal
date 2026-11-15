"""Build the global check sample: pipeline/tests/fixture_global/out/gold/v1, cut from data/global/gold/CURRENT.

Keeps every published file, with the per-hexagon files (monthly_res*, continents_res*) limited to hexagons whose
centre is within 1 degree of a preset box in this folder's firecal.toml. Month status, error ranges, model and
validation are kept whole, so the API and the reference answer exactly as they would on the full data for these
places. Run from pipeline/: uv run python -I tests/fixture_global/make_sample.py
"""
import json
import pathlib
import shutil
import sys
import tomllib

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from firecal_pipeline.config import Config, connect  # noqa: E402

MARGIN = 1.0


def main() -> None:
    src_cfg = Config.load(HERE.parents[2] / "global" / "firecal.toml")
    gold = src_cfg.out / "gold"
    src = gold / (gold / "CURRENT").read_text().strip()
    boxes = [p["bbox"] for p in tomllib.loads((HERE / "firecal.toml").read_text())["presets"]]
    out = HERE / "out" / "gold"
    shutil.rmtree(HERE / "out", ignore_errors=True)
    dst = out / "v1"
    dst.mkdir(parents=True)
    keep = " OR ".join(f"(lng BETWEEN {x0 - MARGIN} AND {x1 + MARGIN} AND lat BETWEEN {y0 - MARGIN} AND {y1 + MARGIN})"
                       for x0, y0, x1, y1 in boxes)
    con = connect()
    for f in sorted(src.iterdir()):
        if f.name.startswith(("monthly_res", "continents_res", "mtd_res")):
            con.execute(f"""COPY (SELECT * EXCLUDE (lat, lng) FROM (
                                SELECT *, h3_cell_to_lat(cell) AS lat, h3_cell_to_lng(cell) AS lng FROM '{f}')
                              WHERE {keep} ORDER BY ALL)
                            TO '{dst / f.name}' (FORMAT parquet, COMPRESSION zstd)""")
        elif f.is_file():
            shutil.copy(f, dst / f.name)
    m = json.loads((dst / "manifest.json").read_text())
    m["version"], m["sample_of"] = "v1", f"{src}"
    (dst / "manifest.json").write_text(json.dumps(m, indent=1))
    (out / "CURRENT").write_text("v1\n")
    sizes = {f.name: con.execute(f"SELECT count(*) FROM '{f}'").fetchone()[0] for f in sorted(dst.glob("*_res*.parquet"))}
    print("global sample from", src.name, json.dumps(sizes))


if __name__ == "__main__":
    main()
