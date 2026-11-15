"""silver + model -> gold/vN/: the files the API serves.

monthly_res{4,5,6}.parquet  cell, year, month, source, value, raw, detections, frp   (sorted by cell)
    value       VIIRS-equivalent burning cell-days (the model is applied here, and only here)
    raw         burning cell-days counted by the satellite used that day, unconverted
    detections  hotspots counted by that satellite (filtered), unconverted
    frp         summed fire radiative power of those hotspots, MW, unconverted
continents_res{4,5,6}.parquet  cell, continent, value: each hexagon's fire-days per continent, whole series
month_status.parquet        continent, year, month, source, days, days_with_data, days_filled
misses.parquet              continent, model, size, area_km2, lo, hi, q10, q90, n   (from model/)
model.json, validation.json copied from model/
hotspots.parquet            cell4/5/6, lat, lon, acq_utc, local_date, sat, dn, confidence, frp, in_calendar
                            (not with [api] hotspot_export = false)
mtd_res{4,5,6}.parquet      cell, year, value: days 1..D of the in-progress month, in every year
                            (only when the series ends partway through a month)
manifest.json               version, coverage, eras, through, in_progress, gaps, continents, row counts, input fingerprint

Continents: the global run fits each continent separately (model.json `continents`), and every cell-day takes
its own continent's multiplier. Argentina is one continent, "study_area". A continent without a fitted model
(Antarctica) has no MODIS days: its months before February 2012 have no data, rather than unconverted counts.

One satellite per day, never summed: each day uses the first satellite in its era's chain with any
detection in that day's continent (Argentina: the study box). gold/CURRENT names the version the API should serve.
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


def prune(cfg: Config) -> None:
    """Delete all but the newest [data] keep_versions published versions (default 3). The version named
    in gold/CURRENT is always kept, and nothing is deleted without one. 0 keeps only that version. Older
    versions are rebuilt by re-running the pipeline if needed."""
    gold = cfg.out / "gold"
    keep = int(cfg["data"].get("keep_versions", 3))
    if keep < 0:
        raise ValueError(f"[data] keep_versions must be 0 or more, not {keep}")
    if not (gold / "CURRENT").exists():
        print("no gold/CURRENT, so nothing is known to be in use; not pruning", flush=True)
        return
    current = (gold / "CURRENT").read_text().strip()
    versions = sorted((p for p in gold.glob("v*") if p.is_dir() and p.name[1:].isdigit()), key=lambda p: int(p.name[1:]))
    old = [p for p in versions[:len(versions) - keep] if p.name != current]  # keep = 0: only CURRENT is left
    for p in old:
        shutil.rmtree(p)
    print(f"pruned {len(old)} old version(s): {', '.join(p.name for p in old) or 'none'}; kept "
          f"{', '.join(p.name for p in versions if p not in old)}", flush=True)


def resolve_eras(cfg: Config) -> list[dict]:
    """Replace end = "latest" with the last complete local date: the newest of the era's satellites in
    bronze/recent.json (a day falls back down the chain), or December 31 of last_year without recent data."""
    recent = cfg.out / "bronze" / "recent.json"
    through = json.loads(recent.read_text())["through"] if recent.exists() else {}
    eras = []
    for e in cfg["harmonization"]["eras"]:
        e = dict(e)
        if e["end"] == "latest":
            ends = [through[s] for s in e["chain"] if s in through]
            e["end"] = max(ends) if ends else f"{cfg['data']['last_year']}-12-31"
        eras.append(e)
    return eras


def continent_models(model: dict) -> dict[str, dict]:
    """continent -> {satellite: fitted model}. The global run fits each continent separately (model.json
    `continents`); Argentina has one model, for the continent its cell-days carry, "study_area". A continent
    that could not be fitted (Antarctica) has none."""
    if "continents" in model:
        return {c: v.get("models", {}) for c, v in model["continents"].items()}
    return {"study_area": model["models"]}


def run(cfg: Config) -> None:
    silver, model_dir = cfg.out / "silver", cfg.out / "model"
    model = json.loads((model_dir / "model.json").read_text())
    models = continent_models(model)
    eras = resolve_eras(cfg)
    through = dt.date.fromisoformat(eras[-1]["end"])
    month_end = (through.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    in_progress = None if through == month_end else {"month": through.strftime("%Y-%m"), "days": through.day}
    con = connect()
    con.execute("SET preserve_insertion_order = false")  # lets the global run's sorts spill to disk
    con.execute(f"CREATE VIEW cell_day AS SELECT * FROM read_parquet('{silver}/cell_day.parquet')")
    found = [r[0] for r in con.execute("SELECT DISTINCT continent FROM cell_day ORDER BY 1").fetchall()]
    if unknown := sorted(set(found) - set(models)):
        raise SystemExit(f"publish: cell-days in {unknown} have no entry in model.json; re-run fit")
    continents = sorted(set(found))
    gold = cfg.dir("gold")
    version = next_version(gold)
    out = gold / version
    out.mkdir()
    con.execute(f"SET temp_directory = '{out / '_tmp'}'")  # spills of the global run, removed at the end

    # A satellite needs converting if any continent has a model for it (Terra, Aqua). In a continent without one
    # (Antarctica: too few fires to fit) its days are left without data rather than counted unconverted.
    con.execute("CREATE TABLE cont(continent VARCHAR, fitted BOOLEAN)")
    con.executemany("INSERT INTO cont VALUES (?, ?)", [[c, bool(models[c])] for c in continents])
    modelled = sorted({s for m in models.values() for s in m})
    con.execute("CREATE TABLE usable(continent VARCHAR, sat VARCHAR)")
    sats = sorted({s for e in eras for s in e["chain"]})
    con.executemany("INSERT INTO usable VALUES (?, ?)",
                    [[c, s] for c in continents for s in sats if s not in modelled or s in models[c]])

    # Which satellite each day uses, per continent: the first in the era's chain with any detection in that
    # continent that day (Argentina: the study box). A continent without a fitted model is too sparse for "no
    # detection" to mean an outage (Antarctica has detections on about a third of days), so it uses the whole
    # run's coverage. "World" (only with several continents) is the same choice over the whole run: the month
    # status of a search with no fire anywhere in it.
    cov_cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{silver}/coverage.parquet')").fetchall()]
    if "continent" in cov_cols:
        con.execute(f"CREATE VIEW cov_raw AS SELECT sat, continent, d FROM read_parquet('{silver}/coverage.parquet') WHERE n_raw > 0")
    elif len(continents) == 1:
        con.execute(f"CREATE VIEW cov_raw AS SELECT sat, '{continents[0]}' AS continent, d "
                    f"FROM read_parquet('{silver}/coverage.parquet') WHERE n_raw > 0")
    else:
        raise SystemExit("publish: silver/coverage.parquet has no continent column; run "
                         "`python -m firecal_pipeline coverage` (or cells) first")
    con.execute("CREATE TABLE world AS SELECT DISTINCT sat, d FROM cov_raw")
    con.execute("""CREATE TABLE cov AS
                   SELECT r.continent, r.sat, r.d FROM cov_raw r JOIN cont USING (continent) WHERE cont.fitted
                   UNION ALL SELECT c.continent, w.sat, w.d FROM world w, cont c WHERE NOT c.fitted""")
    status_areas = continents + (["World"] if len(continents) > 1 else [])
    if len(continents) > 1:
        con.execute("INSERT INTO cov SELECT 'World', sat, d FROM world")
        con.execute("INSERT INTO usable SELECT DISTINCT 'World', sat FROM usable")
    con.execute("CREATE TABLE era(start DATE, stop DATE, source VARCHAR, rank INT, sat VARCHAR)")
    for e in eras:
        for rank, sat in enumerate(e["chain"]):
            con.execute("INSERT INTO era VALUES (?, ?, ?, ?, ?)", [e["start"], e["end"], e["source"], rank, sat])
    con.execute("CREATE TABLE area(continent VARCHAR)")
    con.executemany("INSERT INTO area VALUES (?)", [[a] for a in status_areas])
    con.execute("""
        CREATE TABLE days AS
        WITH cal AS (SELECT a.continent, CAST(d AS DATE) AS d, source FROM area a, era,
                       generate_series(start, stop, INTERVAL 1 DAY) AS t(d) WHERE rank = 0),
             options AS (SELECT c.continent, c.d, e.rank, e.sat FROM cal c
                         JOIN era e ON c.d BETWEEN e.start AND e.stop
                         JOIN usable u ON u.continent = c.continent AND u.sat = e.sat
                         JOIN cov ON cov.continent = c.continent AND cov.sat = e.sat AND cov.d = c.d)
        SELECT cal.continent, cal.d, cal.source, arg_min(o.sat, o.rank) AS sat, min(o.rank) AS rank
        FROM cal LEFT JOIN options o USING (continent, d) GROUP BY ALL""")

    # Multipliers: per (continent, model satellite, day/night, res-3 area); an area without one uses its res-2
    # parent's where model.json has them (the resolution-2 stand-in), otherwise its continent's (Argentina: the
    # study area's) value. A res-3 cell spanning two continents has a multiplier in each.
    con.execute("CREATE TABLE ratio(continent VARCHAR, sat VARCHAR, dn VARCHAR, r3 UBIGINT, r DOUBLE)")
    con.execute("CREATE TABLE parent_ratio(continent VARCHAR, sat VARCHAR, dn VARCHAR, r2 UBIGINT, r DOUBLE)")
    con.execute("CREATE TABLE region_ratio(continent VARCHAR, sat VARCHAR, dn VARCHAR, r DOUBLE)")
    # Seasonal multipliers (PREREGISTRATION.md §7, upgrade 2), where kept: per area, pass and season (DJF, MAM,
    # JJA, SON by calendar month). An area-season without one uses the area's multiplier as above.
    con.execute("CREATE TABLE season_ratio(continent VARCHAR, sat VARCHAR, dn VARCHAR, r3 UBIGINT, q VARCHAR, r DOUBLE)")
    for cont, ms in models.items():
        for sat, m in ms.items():
            con.executemany("INSERT INTO region_ratio VALUES (?, ?, ?, ?)", [[cont, sat, dn, r] for dn, r in m["region"].items()])
            con.executemany("INSERT INTO ratio VALUES (?, ?, ?, h3_string_to_h3(?), ?)",
                            [[cont, sat, dn, s, r] for dn, d in m["strata"].items() for s, r in d.items()])
            parents = [[cont, sat, dn, s, r] for dn, d in m.get("parents", {}).items() for s, r in d.items()]
            if parents:
                con.executemany("INSERT INTO parent_ratio VALUES (?, ?, ?, h3_string_to_h3(?), ?)", parents)
            seasons = [[cont, sat, dn, s, q, r] for dn, d in m.get("seasons", {}).items()
                       for s, qs in d.items() for q, r in qs.items()]
            if seasons:
                con.executemany("INSERT INTO season_ratio VALUES (?, ?, ?, h3_string_to_h3(?), ?, ?)", seasons)
    sr = int(model["stratum_resolution"])
    # A view: the global run has 350 M cell-days, too many to hold in memory; each output below reads it once.
    con.execute(f"""
        CREATE VIEW harmonized AS
        SELECT c.cell8, c.continent, c.d, d.source, c.n_hot, c.frp,
               -- S-NPP is the target. NOAA-20 uses its multipliers only when model.json has them (the
               -- pre-registered rule kept the conversion); otherwise it counts as S-NPP.
               CASE WHEN c.sat = 'snpp' OR (c.sat = 'noaa20' AND rr.r IS NULL) THEN 1.0
                    ELSE coalesce(sr_.r, r.r, pr.r, rr.r) END AS value
        FROM cell_day c
        JOIN days d ON d.continent = c.continent AND d.d = c.d AND d.sat = c.sat
        LEFT JOIN ratio r ON r.continent = c.continent AND r.sat = c.sat AND r.dn = c.dn
                         AND r.r3 = h3_cell_to_parent(c.cell8, {sr})
        LEFT JOIN parent_ratio pr ON pr.continent = c.continent AND pr.sat = c.sat AND pr.dn = c.dn
                                 AND pr.r2 = h3_cell_to_parent(c.cell8, {sr - 1})
        LEFT JOIN region_ratio rr ON rr.continent = c.continent AND rr.sat = c.sat AND rr.dn = c.dn
        LEFT JOIN season_ratio sr_ ON sr_.continent = c.continent AND sr_.sat = c.sat AND sr_.dn = c.dn
                                   AND sr_.r3 = h3_cell_to_parent(c.cell8, {sr})
                                   AND sr_.q = CASE WHEN month(c.d) IN (12, 1, 2) THEN 'DJF'
                                                    WHEN month(c.d) IN (3, 4, 5) THEN 'MAM'
                                                    WHEN month(c.d) IN (6, 7, 8) THEN 'JJA' ELSE 'SON' END""")

    # Everything the app shows is summed from one pass at the finest app level, per continent (written to disk:
    # the global table does not fit in memory).
    fine = max(cfg["grid"]["app_resolutions"])
    agg = out / "_agg.parquet"
    con.execute(f"""
        COPY (SELECT h3_cell_to_parent(cell8, {fine}) AS cell, continent, year(d)::SMALLINT AS year,
                     month(d)::TINYINT AS month, any_value(source) AS source, sum(value) AS value, count(*) AS raw,
                     sum(n_hot) AS detections, sum(frp) AS frp, count(*) FILTER (WHERE value IS NULL) AS missing
              FROM harmonized GROUP BY ALL)
        TO '{agg}' (FORMAT parquet)""")
    assert con.execute(f"SELECT sum(missing) FROM '{agg}'").fetchone()[0] == 0

    rows = {}
    for res in cfg["grid"]["app_resolutions"]:
        path = out / f"monthly_res{res}.parquet"
        con.execute(f"""
            COPY (SELECT h3_cell_to_parent(cell, {res}) AS cell, year, month,
                         any_value(source) AS source, sum(value)::FLOAT AS value, sum(raw)::INTEGER AS raw,
                         sum(detections)::INTEGER AS detections, sum(frp)::FLOAT AS frp
                  FROM '{agg}' GROUP BY ALL ORDER BY cell, year, month)
            TO '{path}' (FORMAT parquet, COMPRESSION zstd)""")
        rows[f"res{res}"] = con.execute(f"SELECT count(*), count(DISTINCT cell) FROM '{path}'").fetchone()
        # Each hexagon's converted total per continent over the whole series: the API gives a search the model,
        # error ranges and month status of the continent holding most of its fire-days (docs/api.md).
        con.execute(f"""
            COPY (SELECT h3_cell_to_parent(cell, {res}) AS cell, continent, sum(value)::FLOAT AS value
                  FROM '{agg}' GROUP BY ALL ORDER BY cell, continent)
            TO '{out}/continents_res{res}.parquet' (FORMAT parquet, COMPRESSION zstd)""")
        if in_progress:
            # Month to date: the same days 1..D of the in-progress calendar month, in every year.
            con.execute(f"""
                COPY (SELECT h3_cell_to_parent(cell8, {res}) AS cell, year(d)::SMALLINT AS year, sum(value)::FLOAT AS value
                      FROM harmonized WHERE month(d) = {through.month} AND day(d) <= {through.day}
                      GROUP BY ALL ORDER BY cell, year)
                TO '{out}/mtd_res{res}.parquet' (FORMAT parquet, COMPRESSION zstd)""")
    agg.unlink()
    shutil.rmtree(out / "_tmp", ignore_errors=True)

    # Filtered hotspot rows for the CSV export, with the app's hexagon at each level and whether the
    # detection came from the satellite the calendar counts that day in its continent. Skipped where
    # [api] hotspot_export = false (the global run: billions of rows, not split for serving yet); the API then
    # refuses the export with a message.
    first, last = eras[0]["start"], eras[-1]["end"]
    if cfg["api"].get("hotspot_export", True):
        con.execute(f"""
            COPY (SELECT h3_cell_to_parent(b.cell8, 4) AS cell4, h3_cell_to_parent(b.cell8, 5) AS cell5,
                         h3_cell_to_parent(b.cell8, 6) AS cell6, b.lat, b.lon, b.acq_utc, b.local_date, b.sat, b.dn,
                         b.confidence, b.frp, coalesce(d.sat = b.sat, false) AS in_calendar
                  FROM read_parquet('{cfg.out}/bronze/*/*.parquet') b
                  LEFT JOIN days d ON d.continent = b.continent AND d.d = b.local_date
                  WHERE b.keep AND b.local_date BETWEEN DATE '{first}' AND DATE '{last}'
                  ORDER BY cell4, b.acq_utc)
            TO '{out}/hotspots.parquet' (FORMAT parquet, COMPRESSION zstd)""")
        rows["hotspots"] = con.execute(f"SELECT count(*), count(DISTINCT cell6) FROM '{out}/hotspots.parquet'").fetchone()

    # Month status per continent (Argentina: "study_area"; with several continents also "World").
    con.execute(f"""
        COPY (SELECT continent, year(d)::SMALLINT AS year, month(d)::TINYINT AS month, any_value(source) AS source,
                     day(last_day(min(d)))::TINYINT AS days, count(sat)::TINYINT AS days_with_data,
                     count(*) FILTER (WHERE rank > 0)::TINYINT AS days_filled
              FROM days GROUP BY ALL ORDER BY ALL) TO '{out}/month_status.parquet' (FORMAT parquet)""")

    def filled_and_gaps(area: str):
        filled = con.execute("SELECT sat, count(*) FROM days WHERE continent = ? AND rank > 0 GROUP BY sat ORDER BY sat",
                             [area]).fetchall()
        gaps = con.execute("""SELECT strftime(min(d), '%Y-%m-%d'), strftime(max(d), '%Y-%m-%d'), count(*) FROM (
                                SELECT d, d - CAST(row_number() OVER (ORDER BY d) AS INT) AS grp
                                FROM days WHERE continent = ? AND sat IS NULL)
                              GROUP BY grp ORDER BY 1""", [area]).fetchall()
        return dict(filled), [{"start": a, "end": b, "days": n} for a, b, n in gaps]

    status = {a: filled_and_gaps(a) for a in status_areas}
    filled, gaps = status[status_areas[-1]]  # Argentina: the study area; global: the whole run ("World")

    # Error ranges: misses.parquet gets a continent column (Argentina's fit writes none: "study_area").
    miss_cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM '{model_dir}/misses.parquet'").fetchall()]
    con.execute(f"""COPY (SELECT {"" if "continent" in miss_cols else f"'{continents[0]}' AS continent, "}*
                          FROM '{model_dir}/misses.parquet') TO '{out}/misses.parquet' (FORMAT parquet)""")
    for f in ("model.json", "validation.json"):
        shutil.copy(model_dir / f, out / f)
    manifest = {
        "version": version,
        "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "region": {"bbox": cfg.bbox, "countries": cfg["data"]["countries"]},
        "unit": "VIIRS-equivalent burning cell-days (H3 res-8 cell, local solar date, day or night pass)",
        "series_start": eras[0]["start"][:7], "series_end": eras[-1]["end"][:7],
        "through": eras[-1]["end"], "in_progress": in_progress,
        "eras": eras,
        "resolutions": cfg["grid"]["app_resolutions"],
        "rows": {k: {"rows": v[0], "cells": v[1]} for k, v in rows.items()},
        "days_filled_by": filled,
        "gaps": gaps,
        # Per continent: whether it has a fitted model, and its own filled days and gaps (the continent's
        # satellite choice). Argentina has the one entry "study_area".
        "continents": {a: {"fitted": a == "World" or bool(models[a]), "days_filled_by": status[a][0], "gaps": status[a][1]}
                       for a in status_areas},
        "hotspot_export": bool(cfg["api"].get("hotspot_export", True)),
        "model": {"calibration_years": model["calibration_years"], "shrinkage_k": model["shrinkage_k"],
                  "stratum_resolution": sr},
        "inputs_sha256": fingerprint(cfg),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    (gold / "CURRENT").write_text(version + "\n")
    print("published", version, json.dumps(manifest["rows"]), "filled", filled, "gaps", len(gaps), flush=True)
