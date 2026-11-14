"""silver + model -> gold/vN/: the files the API serves.

monthly_res{4,5,6}.parquet  cell, year, month, source, value, raw, detections, frp   (sorted by cell)
    value       S-NPP-equivalent burning cell-days (the model is applied here, and only here)
    raw         burning cell-days counted by the satellite used that day, unconverted
    detections  hotspots counted by that satellite (filtered), unconverted
    frp         summed fire radiative power of those hotspots, MW, unconverted
month_status.parquet        year, month, source, days, days_with_data, days_filled
misses.parquet, model.json, validation.json   copied from model/
manifest.json               version, coverage, eras, gaps, row counts, input fingerprint

One satellite per day, never summed: each day uses the first satellite in its era's chain with any
detection in the study box. gold/CURRENT names the version the API should serve.
"""
import datetime as dt
import hashlib
import json
import shutil

from .config import Config, connect


def next_version(gold) -> str:
    n = [int(p.name[1:]) for p in gold.glob("v*") if p.name[1:].isdigit()]
    return f"v{max(n, default=0) + 1}"


def fingerprint(cfg: Config) -> str:
    h = hashlib.sha256()
    for p in sorted((cfg.out / "bronze").rglob("*.parquet")):
        st = p.stat()
        h.update(f"{p.relative_to(cfg.out)}:{st.st_size}:{int(st.st_mtime)}\n".encode())
    return h.hexdigest()


def run(cfg: Config) -> None:
    silver, model_dir = cfg.out / "silver", cfg.out / "model"
    gold = cfg.dir("gold")
    version = next_version(gold)
    out = gold / version
    out.mkdir()
    model = json.loads((model_dir / "model.json").read_text())
    eras = cfg["harmonization"]["eras"]
    con = connect()

    # Which satellite each day uses.
    con.execute(f"CREATE TABLE cov AS SELECT sat, d FROM read_parquet('{silver}/coverage.parquet') WHERE n_raw > 0")
    con.execute("CREATE TABLE era(start DATE, stop DATE, source VARCHAR, rank INT, sat VARCHAR)")
    for e in eras:
        for rank, sat in enumerate(e["chain"]):
            con.execute("INSERT INTO era VALUES (?, ?, ?, ?, ?)", [e["start"], e["end"], e["source"], rank, sat])
    con.execute("""
        CREATE TABLE days AS
        WITH cal AS (SELECT CAST(d AS DATE) AS d, source FROM era,
                       generate_series(start, stop, INTERVAL 1 DAY) AS t(d) WHERE rank = 0),
             options AS (SELECT c.d, e.source, e.rank, e.sat FROM cal c
                         JOIN era e ON c.d BETWEEN e.start AND e.stop JOIN cov USING (sat, d))
        SELECT cal.d, cal.source, arg_min(o.sat, o.rank) AS sat, min(o.rank) AS rank
        FROM cal LEFT JOIN options o USING (d) GROUP BY ALL""")

    # Multipliers: per (model satellite, day/night, res-3 area), with the study-area value as fallback.
    con.execute("CREATE TABLE ratio(sat VARCHAR, dn VARCHAR, r3 UBIGINT, r DOUBLE)")
    con.execute("CREATE TABLE region_ratio(sat VARCHAR, dn VARCHAR, r DOUBLE)")
    for sat, m in model["models"].items():
        con.executemany("INSERT INTO region_ratio VALUES (?, ?, ?)", [[sat, dn, r] for dn, r in m["region"].items()])
        con.executemany("INSERT INTO ratio VALUES (?, ?, h3_string_to_h3(?), ?)",
                        [[sat, dn, s, r] for dn, d in m["strata"].items() for s, r in d.items()])
    sr = int(model["stratum_resolution"])
    con.execute(f"""
        CREATE TABLE harmonized AS
        SELECT c.cell8, c.d, d.source, c.n_hot, c.frp,
               CASE WHEN c.sat IN ('snpp', 'noaa20') THEN 1.0 ELSE coalesce(r.r, rr.r) END AS value
        FROM read_parquet('{silver}/cell_day.parquet') c
        JOIN days d ON d.d = c.d AND d.sat = c.sat
        LEFT JOIN ratio r ON r.sat = c.sat AND r.dn = c.dn AND r.r3 = h3_cell_to_parent(c.cell8, {sr})
        LEFT JOIN region_ratio rr ON rr.sat = c.sat AND rr.dn = c.dn""")
    assert con.execute("SELECT count(*) FROM harmonized WHERE value IS NULL").fetchone()[0] == 0

    rows = {}
    for res in cfg["grid"]["app_resolutions"]:
        path = out / f"monthly_res{res}.parquet"
        con.execute(f"""
            COPY (SELECT h3_cell_to_parent(cell8, {res}) AS cell, year(d)::SMALLINT AS year, month(d)::TINYINT AS month,
                         any_value(source) AS source, sum(value)::FLOAT AS value, count(*)::INTEGER AS raw,
                         sum(n_hot)::INTEGER AS detections, sum(frp)::FLOAT AS frp
                  FROM harmonized GROUP BY ALL ORDER BY cell, year, month)
            TO '{path}' (FORMAT parquet, COMPRESSION zstd)""")
        rows[f"res{res}"] = con.execute(f"SELECT count(*), count(DISTINCT cell) FROM '{path}'").fetchone()

    con.execute(f"""
        COPY (SELECT year(d)::SMALLINT AS year, month(d)::TINYINT AS month, any_value(source) AS source,
                     count(*)::TINYINT AS days, count(sat)::TINYINT AS days_with_data,
                     count(*) FILTER (WHERE rank > 0)::TINYINT AS days_filled
              FROM days GROUP BY ALL ORDER BY ALL) TO '{out}/month_status.parquet' (FORMAT parquet)""")
    filled = con.execute("SELECT sat, count(*) FROM days WHERE rank > 0 GROUP BY sat ORDER BY sat").fetchall()
    gaps = con.execute("""SELECT strftime(min(d), '%Y-%m-%d'), strftime(max(d), '%Y-%m-%d'), count(*) FROM (
                            SELECT d, d - CAST(row_number() OVER (ORDER BY d) AS INT) AS grp FROM days WHERE sat IS NULL)
                          GROUP BY grp ORDER BY 1""").fetchall()

    for f in ("model.json", "validation.json", "misses.parquet"):
        shutil.copy(model_dir / f, out / f)
    manifest = {
        "version": version,
        "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "region": {"bbox": cfg.bbox, "countries": cfg["data"]["countries"]},
        "unit": "S-NPP-equivalent burning cell-days (H3 res-8 cell, local solar date, day/night)",
        "series_start": eras[0]["start"][:7], "series_end": eras[-1]["end"][:7],
        "eras": eras,
        "resolutions": cfg["grid"]["app_resolutions"],
        "rows": {k: {"rows": v[0], "cells": v[1]} for k, v in rows.items()},
        "days_filled_by": dict(filled),
        "gaps": [{"start": a, "end": b, "days": n} for a, b, n in gaps],
        "model": {"calibration_years": model["calibration_years"], "shrinkage_k": model["shrinkage_k"],
                  "stratum_resolution": sr},
        "inputs_sha256": fingerprint(cfg),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    (gold / "CURRENT").write_text(version + "\n")
    print("published", version, json.dumps(manifest["rows"]), "filled", dict(filled), "gaps", len(gaps), flush=True)
