"""silver -> model: MODIS-to-S-NPP multipliers, validation, and miss sizes for error ranges.

Baseline model from PREREGISTRATION.md section 2, fitted separately for Aqua and Terra:
day/night multipliers per H3 res-3 area, shrunk toward the study-area multiplier,
    r = sum V / sum M,    r_s = (V_s + k r) / (M_s + k),    V_hat = r_s * M
fitted on calibration years, on days both satellites have data.

NOAA-20 (used on S-NPP outage days) is fitted the same way on 2018-2022, its overlap with S-NPP, and
compared with no conversion (multiplier 1) by the rule in PREREGISTRATION.md section 7 (2026-11-15).
Its multipliers go into model.json only if that rule keeps them; otherwise publish uses 1.

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


def load(cfg: Config, model: str) -> pd.DataFrame:
    """Monthly counts on matched days, at the finest grouping any score needs."""
    silver = cfg.out / "silver"
    con = connect()
    sr = int(cfg["harmonization"]["stratum_resolution"])
    return con.execute(f"""
        WITH cov AS (SELECT * FROM read_parquet('{silver}/coverage.parquet') WHERE n_raw > 0),
             matched AS (SELECT d FROM cov WHERE sat IN ('{model}', 'snpp') GROUP BY d HAVING count(DISTINCT sat) = 2)
        SELECT year(d) AS y, month(d) AS mo, dn, sat,
               printf('%x', h3_cell_to_parent(cell8, {sr})) AS r3,
               printf('%x', h3_cell_to_parent(cell8, 4)) AS r4,
               CAST(floor(h3_cell_to_lat(cell8) / 2) AS INT) AS blat,
               CAST(floor(h3_cell_to_lng(cell8) / 2) AS INT) AS blon,
               count(*)::BIGINT AS n
        FROM read_parquet('{silver}/cell_day.parquet') JOIN matched USING (d)
        WHERE sat IN ('{model}', 'snpp') GROUP BY ALL""").df()


def fit(g: pd.DataFrame, model: str, years, k: float) -> dict:
    t = g[g.y.isin(years)]
    tot = t.groupby(["dn", "sat"]).n.sum().unstack("sat")
    reg = (tot["snpp"] / tot[model]).to_dict()
    s = t.groupby(["r3", "dn", "sat"]).n.sum().unstack("sat", fill_value=0)
    s = s.reindex(columns=[model, "snpp"], fill_value=0).reset_index()
    s["r"] = (s["snpp"] + k * s.dn.map(reg)) / (s[model] + k)
    strata = {dn: dict(zip(d.r3, d.r)) for dn, d in s.groupby("dn")}
    return {"region": reg, "strata": strata}


def predict(g: pd.DataFrame, model: str, m: dict, years) -> pd.DataFrame:
    """Rows of the model satellite in `years`, with V_hat; plus observed S-NPP rows."""
    a = g[(g.sat == model) & g.y.isin(years)].copy()
    lookup = {(dn, r3): r for dn, d in m["strata"].items() for r3, r in d.items()}
    a["pred"] = [n * lookup.get((dn, r3), m["region"][dn]) for n, dn, r3 in zip(a.n, a.dn, a.r3)]
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


def run(cfg: Config) -> None:
    h = cfg["harmonization"]
    k = float(h["shrinkage_k"])
    held = list(range(cfg.calibration_years[-1] + 1, cfg["data"]["last_year"] + 1))
    out_dir = cfg.dir("model")
    model_json = {"target": h["target"], "stratum_resolution": h["stratum_resolution"], "shrinkage_k": k,
                  "calibration_years": [cfg.calibration_years[0], cfg.calibration_years[-1]], "models": {}}
    validation, tables = {}, []
    for model in MODELS:
        cal = [y for y in cfg.calibration_years if y >= FIRST_YEAR.get(model, 0)]
        g = load(cfg, model)
        loyo = pd.concat([predict(g, model, fit(g, model, [t for t in cal if t != y], k), [y]) for y in cal])
        mm = misses(loyo)
        half = len(cal) // 2
        back = predict(g, model, fit(g, model, cal[half:], k), cal[:half])
        final = fit(g, model, cal, k)
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
            print("noaa20 no conversion", json.dumps(base), "decision", validation[model]["decision"], flush=True)
            if not keep:
                print("noaa20 multipliers", final["region"], "(not used)", flush=True)
                continue
        model_json["models"][model] = {
            "region": {dn: round(r, 4) for dn, r in final["region"].items()},
            "strata": {dn: {s: round(r, 4) for s, r in d.items()} for dn, d in final["strata"].items()},
        }
        if model != "noaa20":  # VIIRS months carry no error range
            tables.append(bin_table(mm).assign(model=model))
        print(model, json.dumps(validation[model]["leave_one_year_out"]), "multipliers", model_json["models"][model]["region"], flush=True)
    (out_dir / "model.json").write_text(json.dumps(model_json, indent=1))
    (out_dir / "validation.json").write_text(json.dumps(validation, indent=1))
    pd.concat(tables)[["model", "lo", "hi", "q10", "q90", "n"]].to_parquet(out_dir / "misses.parquet", index=False)
