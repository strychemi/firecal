"""silver -> model: MODIS-to-S-NPP multipliers, validation, and miss sizes for error ranges.

Baseline model from PREREGISTRATION.md section 2, fitted separately for Aqua and Terra:
day/night multipliers per H3 res-3 area, shrunk toward the study-area multiplier,
    r = sum V / sum M,    r_s = (V_s + k r) / (M_s + k),    V_hat = r_s * M
fitted on calibration years, on fair units: H3 res-3 cell, local solar date and pass that both
satellites observed (PREREGISTRATION.md §7, 2026-11-15; silver/observed.parquet from granules.py).

NOAA-20 (used on S-NPP outage days) is fitted the same way on 2018-2022, its overlap with S-NPP, and
compared with no conversion (multiplier 1) by the rule in PREREGISTRATION.md section 7 (2026-11-15).
Its multipliers go into model.json only if that rule keeps them; otherwise publish uses 1.

Resolution-2 stand-in (PREREGISTRATION.md §7, 2026-11-15), in the areas listed in [harmonization]
standin_areas: a res-3 area with no fair cell-days on a pass uses its res-2 parent's multiplier
(model.json "parents"), shrunk toward r with parent_k; areas with data are unchanged.

model/model.json        multipliers used by publish
model/validation.json   leave-one-year-out scores, tilt, backward join, held-out years
model/misses.parquet    past misses ln(V / V_hat) by predicted-count bin (10th/90th percentiles)
"""
import json

import numpy as np
import pandas as pd

from .config import Config, connect

MODELS = ("aqua", "terra", "noaa20")
FIRST_YEAR = {"noaa20": 2018}  # NOAA-20 data starts 2018-04-01
# PREREGISTRATION.md section 7, 2026-11-15: keep the NOAA-20 conversion only if it beats no conversion by
# at least this much on the small-area score and is no worse than this on the whole-area score.
KEEP_SMALL_GAIN, MAX_WHOLE_LOSS = 0.5, 2.0
IDENTITY = {"region": {"D": 1.0, "N": 1.0}, "strata": {}}
LEVELS = ("r4", "r3", "block", "region")  # aggregation levels pooled for the miss table
BIN_EDGES = [0, 10, 30, 100, 300, 1000, 3000, 10000, 30000, np.inf]
MIN_BIN_N = 30


def fair_ctes(silver, model: str) -> str:
    """SQL common table expressions ending in `fair` (continent, u3, d, dn); `cd` holds the cell-days."""
    sats = f"('{model}', 'snpp')"
    return f"""cd AS (SELECT *, h3_cell_to_parent(cell8, 3) AS u3
                    FROM read_parquet('{silver}/cell_day.parquet') WHERE sat IN {sats}),
             obs AS (SELECT * FROM read_parquet('{silver}/observed.parquet') WHERE sat IN {sats}),
             pass AS (SELECT * FROM read_parquet('{silver}/passes.parquet') WHERE sat IN {sats}),
             units AS (SELECT DISTINCT continent, u3, d, dn FROM cd),
             seen AS (SELECT u.*, p.sat FROM units u
                      JOIN pass p ON p.continent = u.continent AND p.d = u.d AND p.dn = u.dn
                      LEFT JOIN obs o ON o.sat = p.sat AND o.r3 = u.u3 AND o.d = u.d AND o.dn = u.dn
                      WHERE p.fallback OR o.sat IS NOT NULL),
             fair AS (SELECT continent, u3, d, dn FROM seen GROUP BY ALL HAVING count(DISTINCT sat) = 2)"""


def load(cfg: Config, model: str) -> pd.DataFrame:
    """Monthly counts on fair units, at the finest grouping any score needs, with each row's continent.

    A unit is a continent, H3 res-3 cell, local solar date and pass. A satellite observed it if FIRMS holds
    the satellite's data on that pass in that continent (silver/passes.parquet) and either the pass uses the
    whole-area fallback or a granule covers the cell (silver/observed.parquet). Fair: both satellites observed."""
    silver = cfg.out / "silver"
    con = connect()
    sr = int(cfg["harmonization"]["stratum_resolution"])
    return con.execute(f"""
        WITH {fair_ctes(silver, model)}
        SELECT continent, year(d) AS y, month(d) AS mo, dn, sat,
               printf('%x', h3_cell_to_parent(cell8, {sr})) AS r3,
               printf('%x', h3_cell_to_parent(cell8, {sr - 1})) AS r2,
               printf('%x', h3_cell_to_parent(cell8, 4)) AS r4,
               CAST(floor(h3_cell_to_lat(cell8) / 2) AS INT) AS blat,
               CAST(floor(h3_cell_to_lng(cell8) / 2) AS INT) AS blon,
               count(*)::BIGINT AS n
        FROM cd JOIN fair USING (continent, u3, d, dn) GROUP BY ALL""").df()


def shrunk(t: pd.DataFrame, level: str, model: str, reg: dict, k: float) -> dict:
    """{dn: {area: (V_s + k r) / (M_s + k)}} for every area at `level` with fair cell-days on that pass."""
    s = t.groupby([level, "dn", "sat"]).n.sum().unstack("sat", fill_value=0)
    s = s.reindex(columns=[model, "snpp"], fill_value=0).reset_index()
    s["r"] = (s["snpp"] + k * s.dn.map(reg)) / (s[model] + k)
    return {dn: dict(zip(d[level], d.r)) for dn, d in s.groupby("dn")}


def fit(g: pd.DataFrame, model: str, years, k: float, parent_k: float | None = None) -> dict:
    """Section 2 baseline. With parent_k (PREREGISTRATION.md §7, resolution-2 stand-in), areas with no
    fair cell-days on a pass use their res-2 parent's multiplier, shrunk toward r with parent_k."""
    t = g[g.y.isin(years)]
    tot = t.groupby(["dn", "sat"]).n.sum().unstack("sat")
    reg = (tot["snpp"] / tot[model]).to_dict()
    m = {"region": reg, "strata": shrunk(t, "r3", model, reg, k)}
    if parent_k is not None:
        m["parents"] = shrunk(t, "r2", model, reg, parent_k)
    return m


def predict(g: pd.DataFrame, model: str, m: dict, years) -> pd.DataFrame:
    """Rows of the model satellite in `years`, with V_hat; plus observed S-NPP rows."""
    a = g[(g.sat == model) & g.y.isin(years)].copy()
    lookup = {(dn, r3): r for dn, d in m["strata"].items() for r3, r in d.items()}
    parent = {(dn, r2): r for dn, d in m.get("parents", {}).items() for r2, r in d.items()}
    a["pred"] = [n * lookup.get((dn, r3), parent.get((dn, r2), m["region"][dn]))
                 for n, dn, r3, r2 in zip(a.n, a.dn, a.r3, a.r2)]
    v = g[(g.sat == "snpp") & g.y.isin(years)].rename(columns={"n": "obs"})
    keys = ["y", "mo", "dn", "r3", "r4", "blat", "blon"]
    return pd.concat([a[keys + ["pred"]], v[keys + ["obs"]]]).fillna(0).groupby(keys, as_index=False).sum()


def by(level: str) -> list[str]:
    return {"r4": ["y", "mo", "r4"], "r3": ["y", "mo", "r3"], "block": ["y", "mo", "blat", "blon"],
            "region": ["y", "mo"]}[level]


def typical_error(p: pd.DataFrame, level: str, min_obs: int) -> dict:
    a = p.groupby(by(level))[["pred", "obs"]].sum()
    a = a[a.obs >= min_obs]
    e = (a.pred - a.obs).abs() / a.obs * 100
    return {"median": round(float(e.median()), 2), "p90": round(float(e.quantile(0.9)), 2), "n": int(len(e))}


def tilt(p: pd.DataFrame) -> dict:
    out = {}
    for dn, d in p.groupby("dn"):
        a = d.groupby(["y", "mo"])[["pred", "obs"]].sum()
        a = a[(a.pred > 0) & (a.obs > 0)]
        out[dn] = round(float(np.polyfit(np.log(a.pred), np.log(a.obs / a.pred), 1)[0]), 3)
    return out


def gap(p: pd.DataFrame) -> dict:
    g = {"all": 100 * np.log(p.pred.sum() / p.obs.sum())}
    for dn, d in p.groupby("dn"):
        g[dn] = 100 * np.log(d.pred.sum() / d.obs.sum())
    return {k: round(float(v), 2) for k, v in g.items()}


def misses(p: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for level in LEVELS:
        a = p.groupby(by(level))[["pred", "obs"]].sum().reset_index()
        a = a[(a.pred > 0) & (a.obs > 0)]
        rows.append(pd.DataFrame({"y": a.y, "pred": a.pred, "miss": np.log(a.obs / a.pred), "level": level}))
    return pd.concat(rows, ignore_index=True)


def bin_table(m: pd.DataFrame) -> pd.DataFrame:
    m = m.assign(bin=pd.cut(m.pred, BIN_EDGES, right=False, labels=False))
    q = m.groupby("bin").miss.agg(q10=lambda s: s.quantile(0.1), q90=lambda s: s.quantile(0.9), n="size")
    q = q.reindex(range(len(BIN_EDGES) - 1))
    ok = q.index[q.n.fillna(0) >= MIN_BIN_N]
    for b in q.index[q.n.fillna(0) < MIN_BIN_N]:  # borrow from the nearest bin with enough months
        near = ok[np.argmin(np.abs(ok - b))]
        q.loc[b, ["q10", "q90"]] = q.loc[near, ["q10", "q90"]]
    q["lo"], q["hi"] = BIN_EDGES[:-1], BIN_EDGES[1:]
    return q.reset_index()[["lo", "hi", "q10", "q90", "n"]].fillna({"n": 0})


def coverage(m: pd.DataFrame, level: str, years) -> float:
    """Share of left-out-year months inside an 80 % range built from the other years."""
    inside = []
    for y in years:
        t = bin_table(m[(m.y != y)])
        h = m[(m.y == y) & (m.level == level)]
        b = pd.cut(h.pred, BIN_EDGES, right=False, labels=False)
        inside.append(((h.miss >= t.q10.values[b]) & (h.miss <= t.q90.values[b])).mean())
    return round(float(np.mean(inside)) * 100, 1)


def fittable(g: pd.DataFrame, model: str, cal) -> bool:
    """Every leave-one-year-out training set has fair cell-days of both satellites on both passes."""
    t = g[g.y.isin(cal)].groupby(["y", "dn", "sat"]).n.sum()
    for y in cal:
        train = t[t.index.get_level_values("y") != y].groupby(["dn", "sat"]).sum()
        if any(train.get((dn, s), 0) <= 0 for dn in ("D", "N") for s in (model, "snpp")):
            return False
    return True


def parent_k(cfg: Config, area: str) -> float | None:
    """The res-2 stand-in's k where PREREGISTRATION.md §7 (2026-11-15) kept it for this area, else None."""
    h = cfg["harmonization"]
    return float(h["parent_k"]) if area in h.get("standin_areas", []) else None


def fit_area(g_all: dict, cfg: Config, label: str, area: str = "study_area") -> tuple[dict, dict, list]:
    """Fit and validate every model on one study area (Argentina's box, or one continent)."""
    h = cfg["harmonization"]
    k = float(h["shrinkage_k"])
    held = list(range(cfg.calibration_years[-1] + 1, cfg["data"]["last_year"] + 1))
    models, validation, tables = {}, {}, []
    for model in MODELS:
        cal = [y for y in cfg.calibration_years if y >= FIRST_YEAR.get(model, 0)]
        g = g_all[model]
        pk = parent_k(cfg, area) if model != "noaa20" else None  # NOAA-20 stays at multiplier 1 either way
        if not fittable(g, model, cal):
            validation[model] = {"status": "cannot be fitted: a training set has no fair cell-days of both "
                                           "satellites on a pass"}
            print(f"{label} {model}: {validation[model]['status']}", flush=True)
            continue
        loyo = pd.concat([predict(g, model, fit(g, model, [t for t in cal if t != y], k, pk), [y]) for y in cal])
        mm = misses(loyo)
        half = len(cal) // 2
        back = predict(g, model, fit(g, model, cal[half:], k, pk), cal[:half])
        final = fit(g, model, cal, k, pk)
        test = predict(g, model, final, held)
        validation[model] = {
            "leave_one_year_out": {"whole_area": typical_error(loyo, "region", 100),
                                   "small_area_2deg": typical_error(loyo, "block", 50),
                                   "tilt": tilt(loyo), "gap_pct": gap(loyo),
                                   "range_coverage_pct": {"r4": coverage(mm, "r4", cal),
                                                          "block": coverage(mm, "block", cal)}},
            "backward_join": {"fit": [cal[half], cal[-1]], "predict": [cal[0], cal[half - 1]], "gap_pct": gap(back)},
            "held_out": {"years": held, "whole_area": typical_error(test, "region", 100), "gap_pct": gap(test)},
        }
        if model == "noaa20":
            none = predict(g, model, IDENTITY, cal)  # nothing is fitted, so no year needs leaving out
            conv, base = validation[model]["leave_one_year_out"], {
                "whole_area": typical_error(none, "region", 100), "small_area_2deg": typical_error(none, "block", 50),
                "tilt": tilt(none), "gap_pct": gap(none)}
            small_gain = base["small_area_2deg"]["median"] - conv["small_area_2deg"]["median"]
            whole_loss = conv["whole_area"]["median"] - base["whole_area"]["median"]
            keep = small_gain >= KEEP_SMALL_GAIN and whole_loss <= MAX_WHOLE_LOSS
            none_held = predict(g, model, IDENTITY, held)
            validation[model]["no_conversion"] = {
                "leave_one_year_out": base,
                "held_out": {"whole_area": typical_error(none_held, "region", 100), "gap_pct": gap(none_held)}}
            validation[model]["decision"] = {"small_area_gain_pts": round(small_gain, 2),
                                             "whole_area_loss_pts": round(whole_loss, 2),
                                             "kept": bool(keep)}
            print(label, "noaa20 no conversion", json.dumps(base), "decision", validation[model]["decision"], flush=True)
            if not keep:
                print(label, "noaa20 multipliers", final["region"], "(not used)", flush=True)
                continue
        models[model] = {
            "region": {dn: round(r, 4) for dn, r in final["region"].items()},
            "strata": {dn: {s: round(r, 4) for s, r in d.items()} for dn, d in final["strata"].items()},
        }
        if "parents" in final:
            models[model]["parents"] = {dn: {s: round(r, 4) for s, r in d.items()} for dn, d in final["parents"].items()}
        if model != "noaa20":  # VIIRS months carry no error range
            tables.append(bin_table(mm).assign(model=model))
        print(label, model, json.dumps(validation[model]["leave_one_year_out"]), "multipliers", models[model]["region"], flush=True)
    return models, validation, tables


def run(cfg: Config) -> None:
    """One study area (Argentina): model.json as before. Continents (global run, PREREGISTRATION.md §7):
    each continent is fitted as its own study area, under "continents" in model.json and validation.json."""
    h = cfg["harmonization"]
    out_dir = cfg.dir("model")
    model_json = {"target": h["target"], "stratum_resolution": h["stratum_resolution"],
                  "shrinkage_k": float(h["shrinkage_k"]),
                  "calibration_years": [cfg.calibration_years[0], cfg.calibration_years[-1]]}
    g_all = {model: load(cfg, model) for model in MODELS}
    areas = sorted(set().union(*(set(g.continent) for g in g_all.values())))
    if areas == ["study_area"]:
        models, validation, tables = fit_area({m: g.drop(columns="continent") for m, g in g_all.items()}, cfg, "")
        if parent_k(cfg, "study_area") is not None:
            model_json["parent_k"] = parent_k(cfg, "study_area")
        model_json["models"] = models
        misses_df = pd.concat(tables)[["model", "lo", "hi", "q10", "q90", "n"]]
    else:
        model_json["continents"], validation, tables = {}, {"continents": {}}, []
        for c in areas:
            models, val, tab = fit_area({m: g[g.continent == c].drop(columns="continent") for m, g in g_all.items()},
                                        cfg, c, c)
            model_json["continents"][c] = {"models": models}
            if parent_k(cfg, c) is not None:
                model_json["continents"][c]["parent_k"] = parent_k(cfg, c)
            validation["continents"][c] = val
            tables += [t.assign(continent=c) for t in tab]
        misses_df = pd.concat(tables)[["continent", "model", "lo", "hi", "q10", "q90", "n"]]
    (out_dir / "model.json").write_text(json.dumps(model_json, indent=1))
    (out_dir / "validation.json").write_text(json.dumps(validation, indent=1))
    misses_df.to_parquet(out_dir / "misses.parquet", index=False)
