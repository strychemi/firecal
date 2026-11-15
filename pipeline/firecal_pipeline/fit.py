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
model/misses.parquet    80 % ranges: per size of area (res-4, res-3, 2° block, study area) with its typical
                        area, 5 bins of predicted count, 10th/90th percentiles of past misses ln(V / V_hat)
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
LEVELS = ("r4", "r3", "block", "region")  # sizes of area, each with its own miss table
N_BINS = 5  # quintiles of ln V_hat within each size (rule 5; PREREGISTRATION.md §7, 2026-11-15)
EARTH_R_KM = 6371.0088


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


# ---- Tilt correction by fire strength (PREREGISTRATION.md §7, 2026-11-15, upgrade 3) ----
# Each MODIS cell-day falls in one of three FRP classes, with edges at the terciles of MODIS cell-day FRP on
# fair units in the training years, per study area (continent) and pass. A fold names a training set:
# "all" (calibration years), "back" (the later half, for the backward join) and "y<year>" (leave that year out).
N_CLASSES = 3
POISSON_TOL, POISSON_MAX_IT = 1e-9, 20000


def folds(cal) -> dict:
    half = len(cal) // 2
    return {"all": list(cal), "back": list(cal[half:]), **{f"y{y}": [t for t in cal if t != y] for y in cal}}


def frp_edges(cfg: Config, model: str, continent: str | None = None) -> pd.DataFrame:
    """Tercile edges of MODIS cell-day FRP on fair units, per fold, continent and pass."""
    silver, con = cfg.out / "silver", connect()
    where = f"AND continent = '{continent}'" if continent else ""
    parts = []
    for fid, years in folds(cfg.calibration_years).items():
        parts.append(con.execute(f"""
            WITH {fair_ctes(silver, model)}
            SELECT '{fid}' AS fold, continent, dn, quantile_cont(coalesce(frp, 0), [1 / 3, 2 / 3]) AS q
            FROM cd JOIN fair USING (continent, u3, d, dn)
            WHERE sat = '{model}' AND year(d) IN ({", ".join(map(str, years))}) {where}
            GROUP BY ALL""").df())
    e = pd.concat(parts, ignore_index=True)
    e["e1"], e["e2"] = e.q.str[0], e.q.str[1]
    return e.drop(columns="q")


def load_frp(cfg: Config, model: str, continent: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """load() plus, for every fold, the model satellite's cell-days per FRP class (columns c_<fold>_<class>)."""
    silver, con = cfg.out / "silver", connect()
    sr = int(cfg["harmonization"]["stratum_resolution"])
    e = frp_edges(cfg, model, continent)
    need = len(folds(cfg.calibration_years))
    if e.empty or (e.groupby("dn").fold.nunique() < need).any() or e.dn.nunique() < 2:
        return pd.DataFrame(), e  # a training set has no MODIS cell-days on a pass: cannot be fitted
    w = e.pivot_table(index=["continent", "dn"], columns="fold", values=["e1", "e2"])
    w.columns = [f"{a}_{f}" for a, f in w.columns]
    con.register("edges", w.reset_index())
    cls = []
    for fid in folds(cfg.calibration_years):
        x = "coalesce(cd.frp, 0)"
        cls += [f"count(*) FILTER (WHERE sat = '{model}' AND {x} < e1_{fid})::INT AS c_{fid}_0",
                f"count(*) FILTER (WHERE sat = '{model}' AND {x} >= e1_{fid} AND {x} < e2_{fid})::INT AS c_{fid}_1",
                f"count(*) FILTER (WHERE sat = '{model}' AND {x} >= e2_{fid})::INT AS c_{fid}_2"]
    where = f"WHERE continent = '{continent}'" if continent else ""
    g = con.execute(f"""
        WITH {fair_ctes(silver, model)}
        SELECT continent, year(d) AS y, month(d) AS mo, dn, sat,
               printf('%x', h3_cell_to_parent(cell8, {sr})) AS r3,
               printf('%x', h3_cell_to_parent(cell8, {sr - 1})) AS r2,
               printf('%x', h3_cell_to_parent(cell8, 4)) AS r4,
               CAST(floor(h3_cell_to_lat(cell8) / 2) AS INT) AS blat,
               CAST(floor(h3_cell_to_lng(cell8) / 2) AS INT) AS blon,
               count(*)::BIGINT AS n, {", ".join(cls)}
        FROM cd JOIN fair USING (continent, u3, d, dn) JOIN edges USING (continent, dn) {where}
        GROUP BY ALL""").df()
    return g, e


def poisson_weights(M: np.ndarray, V: np.ndarray, start: float) -> np.ndarray:
    """Poisson maximum likelihood, identity link, beta >= 0: E[V] = M @ beta. Multiplicative updates."""
    keep = M.sum(axis=1) > 0
    M, V = M[keep].astype(float), V[keep].astype(float)
    beta = np.full(M.shape[1], start)
    colsum = M.sum(axis=0)
    ll_old = -np.inf
    for _ in range(POISSON_MAX_IT):
        mu = M @ beta
        ll = float(np.sum(V * np.log(np.maximum(mu, 1e-300)) - mu))
        if abs(ll - ll_old) <= POISSON_TOL * abs(ll):
            break
        ll_old = ll
        beta = beta * (M.T @ (V / np.maximum(mu, 1e-300))) / np.where(colsum > 0, colsum, 1)
    return beta


def fit_frp(g: pd.DataFrame, model: str, fid: str, years, k: float, parent_k: float | None = None) -> dict:
    """Class weights beta_f per pass on res-3 area-months, then per-area corrections c_s toward 1."""
    t = g[g.y.isin(years)]
    cols = [f"c_{fid}_{c}" for c in range(N_CLASSES)]
    out = {"fold": fid, "beta": {}, "corr": {}, "parents": {}}
    for dn, d in t.groupby("dn"):
        a = d[d.sat == model].groupby(["r3", "r2", "mo", "y"])[cols].sum()
        v = d[d.sat == "snpp"].groupby(["r3", "r2", "mo", "y"]).n.sum()
        am = a.join(v.rename("V"), how="outer").fillna(0)
        start = am.V.sum() / am[cols].to_numpy().sum()
        beta = poisson_weights(am[cols].to_numpy(), am.V.to_numpy(), start)
        am["W"] = am[cols].to_numpy() @ beta
        out["beta"][dn] = [float(b) for b in beta]
        for lvl, kk, key in (("r3", k, "corr"), ("r2", parent_k, "parents")):
            if kk is None:
                continue
            s = am.groupby(level=lvl)[["V", "W"]].sum()
            out[key][dn] = dict(zip(s.index, (s.V + kk) / (s.W + kk)))
    if parent_k is None:
        out.pop("parents")
    return out


def predict_frp(g: pd.DataFrame, model: str, m: dict, years) -> pd.DataFrame:
    """Like predict(): V_hat = c_s x sum_f beta_f M_f, with c_s from the area, its parent, or 1."""
    fid = m["fold"]
    cols = [f"c_{fid}_{c}" for c in range(N_CLASSES)]
    a = g[(g.sat == model) & g.y.isin(years)].copy()
    w = np.zeros(len(a))
    c = np.ones(len(a))
    for dn in ("D", "N"):
        sel = (a.dn == dn).to_numpy()
        if not sel.any() or dn not in m["beta"]:
            continue
        w[sel] = a.loc[sel, cols].to_numpy() @ np.array(m["beta"][dn])
        corr, par = m["corr"].get(dn, {}), m.get("parents", {}).get(dn, {})
        c[sel] = [corr.get(r3, par.get(r2, 1.0)) for r3, r2 in zip(a.r3[sel], a.r2[sel])]
    a["pred"] = w * c
    v = g[(g.sat == "snpp") & g.y.isin(years)].rename(columns={"n": "obs"})
    keys = ["y", "mo", "dn", "r3", "r4", "blat", "blon"]
    return pd.concat([a[keys + ["pred"]], v[keys + ["obs"]]]).fillna(0).groupby(keys, as_index=False).sum()


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
    """80 % ranges for one size of area: 5 bins at the quintiles of ln V_hat, 10th/90th percentile of the
    miss in each (rule 5's method). lo/hi are V_hat edges; the outer bins are open."""
    edges = np.quantile(np.log(m.pred), np.linspace(0, 1, N_BINS + 1)[1:-1])
    b = np.searchsorted(edges, np.log(m.pred), side="right")
    q = m.groupby(b).miss.agg(q10=lambda s: s.quantile(0.1), q90=lambda s: s.quantile(0.9), n="size")
    q = q.reindex(range(N_BINS))
    ok = q.index[q.n.fillna(0) > 0]
    for i in q.index[q.n.fillna(0) == 0]:  # empty bin (repeated quantile edges): borrow the nearest bin's range
        q.loc[i, ["q10", "q90"]] = q.loc[ok[np.argmin(np.abs(ok - i))], ["q10", "q90"]].to_numpy()
    lo = np.concatenate([[0.0], np.exp(edges)])
    hi = np.concatenate([np.exp(edges), [np.inf]])
    return pd.DataFrame({"lo": lo, "hi": hi, "q10": q.q10.to_numpy(), "q90": q.q90.to_numpy(),
                         "n": q.n.fillna(0).astype(int).to_numpy()})


def size_tables(m: pd.DataFrame, areas: dict) -> pd.DataFrame:
    """One bin table per size of area, with that size's typical area (km²)."""
    return pd.concat([bin_table(m[m.level == lv]).assign(size=lv, area_km2=areas[lv]) for lv in LEVELS],
                     ignore_index=True)


def coverage(m: pd.DataFrame, level: str, years) -> float:
    """Share of left-out-year months of one size inside an 80 % range built from the other years' months
    of that size."""
    inside = []
    for y in years:
        t = bin_table(m[(m.y != y) & (m.level == level)])
        h = m[(m.y == y) & (m.level == level)]
        if h.empty:
            continue
        b = np.searchsorted(t.hi.to_numpy()[:-1], h.pred.to_numpy(), side="right")
        inside.append(((h.miss >= t.q10.to_numpy()[b]) & (h.miss <= t.q90.to_numpy()[b])).mean())
    return round(float(np.mean(inside)) * 100, 1)


def typical_areas(g: pd.DataFrame) -> dict:
    """Median area (km²) of the units of each size in the study area; the whole area for "region"."""
    con = connect()
    cell_km2 = lambda cells: con.execute(
        "SELECT h3_cell_area(h3_string_to_h3(c), 'km^2') FROM unnest(?) t(c)", [list(cells)]).df().iloc[:, 0]
    r3 = cell_km2(g.r3.unique())
    b = g[["blat", "blon"]].drop_duplicates()
    block = EARTH_R_KM ** 2 * np.radians(2) * (np.sin(np.radians(2 * b.blat + 2)) - np.sin(np.radians(2 * b.blat)))
    return {"r4": round(float(cell_km2(g.r4.unique()).median()), 1), "r3": round(float(r3.median()), 1),
            "block": round(float(block.median()), 1), "region": round(float(r3.sum()), 1)}


COVERAGE_MARKS = (75.0, 85.0)  # rule 5, by size of area (PREREGISTRATION.md §7, 2026-11-15)


def coverage_by_size(mm: pd.DataFrame, cal) -> dict:
    out = {lv: coverage(mm, lv, cal) for lv in LEVELS}
    out["status"] = "pass" if all(COVERAGE_MARKS[0] <= out[lv] <= COVERAGE_MARKS[1]
                                  for lv in ("r4", "r3", "block")) else "fail"
    return out


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
        fit_fn, pred_fn = fit, predict
        if model != "noaa20" and area in h.get("seasonal_areas", []):  # PREREGISTRATION.md §7, upgrade 2
            from . import seasonal
            fit_fn, pred_fn = seasonal.fit_seasonal, seasonal.predict_seasonal
        if not fittable(g, model, cal):
            validation[model] = {"status": "cannot be fitted: a training set has no fair cell-days of both "
                                           "satellites on a pass"}
            print(f"{label} {model}: {validation[model]['status']}", flush=True)
            continue
        loyo = pd.concat([pred_fn(g, model, fit_fn(g, model, [t for t in cal if t != y], k, pk), [y]) for y in cal])
        mm = misses(loyo)
        half = len(cal) // 2
        back = pred_fn(g, model, fit_fn(g, model, cal[half:], k, pk), cal[:half])
        final = fit_fn(g, model, cal, k, pk)
        test = pred_fn(g, model, final, held)
        validation[model] = {
            "leave_one_year_out": {"whole_area": typical_error(loyo, "region", 100),
                                   "small_area_2deg": typical_error(loyo, "block", 50),
                                   "tilt": tilt(loyo), "gap_pct": gap(loyo),
                                   "range_coverage_pct": coverage_by_size(mm, cal)},
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
        if "seasons" in final:  # {dn: {r3: {season: r}}}
            sea = {}
            for (dn, r3, q), r in final["seasons"].items():
                sea.setdefault(dn, {}).setdefault(r3, {})[q] = round(r, 4)
            models[model]["seasons"] = sea
        if model != "noaa20":  # VIIRS months carry no error range
            tables.append(size_tables(mm, typical_areas(g)).assign(model=model))
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
        misses_df = pd.concat(tables)[["model", "size", "area_km2", "lo", "hi", "q10", "q90", "n"]]
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
        misses_df = pd.concat(tables)[["continent", "model", "size", "area_km2", "lo", "hi", "q10", "q90", "n"]]
    (out_dir / "model.json").write_text(json.dumps(model_json, indent=1))
    (out_dir / "validation.json").write_text(json.dumps(validation, indent=1))
    misses_df.to_parquet(out_dir / "misses.parquet", index=False)
