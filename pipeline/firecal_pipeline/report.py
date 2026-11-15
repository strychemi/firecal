"""model + silver -> model/report.json: the baseline's rule statuses with luck ranges, per study area.

PREREGISTRATION.md §4 and §7 (2026-11-15, global run): for each continent (Argentina: its one study area),
recompute every luck range with the Argentina bootstrap and report the baseline's rules 3, 4 and 5.

Luck ranges repeat science/rule_checks/checks.py: resample the calibration years with replacement,
B = 4,000 times, seed 20261114, recompute the statistic on the pooled resampled years, and report the
2.5th-97.5th percentiles (and the SD where a margin needs it).

  Scores    whole-area (area-months with >= 100 S-NPP cell-days) and small-area (2-degree blocks with >= 50)
            typical error, leaving one calibration year out, with their bootstrap SD.
  Rule 3    tilt b by day and night over whole-area months; pass if |b| <= 0.03 by day and <= 0.06 at night.
            Too noisy to test (§4, item 4) when the luck range reaches past the pass mark on both sides.
  Rule 4    backward-join gap (fit 2018-2022, predict 2013-2017), resampling the predicted years; pass within
            +-7 % for day and night together and by day, +-10 % at night.
  Rule 5    80 % range coverage of small-area months (2-degree blocks, day and night together), averaged over
            left-out years; pass at 75-85 %. As in checks.py: the range is the 10th-90th percentile of
            ln(V / V_hat) from the other calibration years, in 5 bins of predicted count (quintiles of ln V_hat).
            The app's own ranges (fit.py: one table per size of area, the same method) are judged beside it,
            for res-4 cells, res-3 cells and 2-degree blocks (PREREGISTRATION.md §7, 2026-11-15).

Known limit of the small-area score: 2-degree blocks shrink toward the poles (area ~ cos latitude; at 60 degrees
half the equator's), so northern blocks reach 50 cell-days less often and northern continents are scored on fewer,
noisier block-months. Paired comparisons share the blocks, so this mostly widens luck ranges there rather than
biasing a decision. If an upgrade's result in a northern continent is borderline, check it on an equal-area H3 grid,
with that check's rule written into PREREGISTRATION.md §7 first.

Rules 1, 2 and 6 compare versions, so they apply when an upgrade is tested (§5), not to the baseline alone.

Upgrade 1, the resolution-2 stand-in (PREREGISTRATION.md §7, 2026-11-15), is decided per continent on Aqua:
  Rule 6    leave-area-out on data-rich res-3 areas (>= 2,000 Aqua fair cell-days in the calibration years):
            predict each calibration year of the hidden area from the continent's r and from its res-2
            parent's r_p (k = 200), both fitted on the rest; median |V_hat - V| / V over area-years with V > 0;
            resample areas 1,000 times; pass if the 95 % range of (error with r - error with r_p) is above zero.
            Fewer than 20 data-rich areas: too few areas to test.
  No harm   where rule 6 passes, leaving one year out, stand-in against baseline on the same resampled years:
            rule 2 (whole-area loss <= max(2, 2 x paired SD)); rules 4 and 5 still pass where the baseline
            passes, and where the baseline fails rule 4 the gap is at most 0.5 points further from zero.
            Rule 1's gain and rule 3's tilt are reported. Terra is scored with the stand-in, reported only.
The stand-in uses its own random generator (seed 20261114 per continent), so the baseline's luck ranges
are unchanged.
"""
import json

import numpy as np
import pandas as pd

from . import fit as F
from .config import Config

SEED, B = 20261114, 4000
TILT_MARK = {"D": 0.03, "N": 0.06}
GAP_MARK = {"all": 7.0, "D": 7.0, "N": 10.0}
COVER = (75.0, 85.0)
MODELS = ("aqua", "terra")  # NOAA-20 is used unconverted; Terra is reported, not pass/fail (§6)
PARENT_K, RICH, MIN_RICH, B_AREAS, GAP_SLACK = 200.0, 2000, 20, 1000, 0.5


def ci(x) -> list[float]:
    return [round(float(v), 3) for v in np.percentile(x, [2.5, 97.5])]


def boot(rng, years, fn) -> np.ndarray:
    ys = np.array(years)
    return np.array([fn(rng.choice(ys, len(ys))) for _ in range(B)])


def errors_by_year(p: pd.DataFrame, level: str, min_obs: int) -> dict:
    a = p.groupby(F.by(level))[["pred", "obs"]].sum().reset_index()
    a = a[a.obs >= min_obs]
    e = (a.pred - a.obs).abs() / a.obs * 100
    return {y: e[a.y == y].to_numpy() for y in sorted(a.y.unique())}


def score(rng, p, level, min_obs, years) -> dict:
    e = errors_by_year(p, level, min_obs)
    if not e:
        return {"median": None, "n": 0}
    pooled = lambda ys: np.median(np.concatenate([e.get(y, np.array([])) for y in ys]) if len(ys) else [np.nan])
    bs = boot(rng, [y for y in years if y in e], pooled)
    allv = np.concatenate(list(e.values()))
    return {"median": round(float(np.median(allv)), 2), "sd": round(float(np.nanstd(bs)), 2),
            "ci95": ci(bs[~np.isnan(bs)]), "n": int(len(allv))}


def tilt_rule(rng, p, years) -> dict:
    out = {}
    for dn, d in p.groupby("dn"):
        a = d.groupby(["y", "mo"])[["pred", "obs"]].sum().reset_index()
        a = a[(a.pred > 0) & (a.obs > 0)]
        by_y = {y: g for y, g in a.groupby("y")}
        ys = [y for y in years if y in by_y]
        if len(ys) < 3:
            out[dn] = {"status": "too few months"}
            continue
        def slope(sample):
            g = pd.concat([by_y[y] for y in sample])
            return np.polyfit(np.log(g.pred), np.log(g.obs / g.pred), 1)[0]
        b, bs = slope(ys), boot(rng, ys, slope)
        lo, hi = ci(bs)
        mark = TILT_MARK[dn]
        status = "too noisy to test" if lo < -mark and hi > mark else ("pass" if abs(b) <= mark else "fail")
        out[dn] = {"b": round(float(b), 3), "ci95": [lo, hi], "sd": round(float(bs.std()), 3), "mark": mark,
                   "status": status}
    return out


def gap_rule(rng, p, years) -> dict:
    out = {}
    for key, d in [("all", p)] + list(p.groupby("dn")):
        a = d.groupby("y")[["pred", "obs"]].sum()
        ys = [y for y in years if y in a.index and a.obs[y] > 0]
        if not ys:
            out[key] = {"status": "no data"}
            continue
        f = lambda s: 100 * np.log(a.pred.loc[list(s)].sum() / a.obs.loc[list(s)].sum())
        g, bs = f(ys), boot(rng, ys, f)
        mark = GAP_MARK[key]
        out[key] = {"gap_pct": round(float(g), 2), "ci95": ci(bs), "mark": mark,
                    "status": "pass" if abs(g) <= mark else "fail"}
    return out


def coverage_rule(p: pd.DataFrame, years, nbins: int = 5) -> dict:
    g = p.groupby(["y", "mo", "blat", "blon"])[["pred", "obs"]].sum().reset_index()
    g = g[(g.pred > 0) & (g.obs > 0)].copy()
    if len(g) < nbins * 10:
        return {"block_pct": None, "status": "too few months"}
    g["res"] = np.log(g.obs / g.pred)
    g["bin"] = pd.qcut(np.log(g.pred), nbins, labels=False)
    by_year = {}
    for y in years:
        te, tr = g[g.y == y], g[g.y != y]
        if te.empty:
            continue
        q = tr.groupby("bin").res.quantile([0.1, 0.9]).unstack()
        by_year[int(y)] = float(((te.res >= te.bin.map(q[0.1])) & (te.res <= te.bin.map(q[0.9]))).mean() * 100)
    mean = float(np.mean(list(by_year.values())))
    return {"block_pct": round(mean, 1), "by_year": {y: round(v, 1) for y, v in by_year.items()},
            "status": "pass" if COVER[0] <= mean <= COVER[1] else "fail"}


def rule6(rng, g: pd.DataFrame, model: str, cal) -> dict:
    """Leave-area-out: the continent's r against the res-2 parent's r_p as the stand-in for a hidden area."""
    t = g[g.y.isin(cal)]
    yr = t.groupby(["r3", "r2", "y", "dn", "sat"]).n.sum().unstack("sat", fill_value=0)
    yr = yr.reindex(columns=[model, "snpp"], fill_value=0).reset_index()
    a3 = yr.groupby(["r3", "r2", "dn"])[[model, "snpp"]].sum().reset_index()
    rich = a3.groupby("r3")[model].sum()
    rich = rich[rich >= RICH].index
    if len(rich) < MIN_RICH:
        return {"rich_areas": int(len(rich)), "status": "too few areas to test", "pass": False}
    cont = a3.groupby("dn")[[model, "snpp"]].sum()
    par = a3.groupby(["r2", "dn"])[[model, "snpp"]].sum()
    a = a3[a3.r3.isin(rich)].copy()
    c = cont.loc[a.dn].to_numpy()
    p = par.loc[list(zip(a.r2, a.dn))].to_numpy()
    own = a[[model, "snpp"]].to_numpy()
    if (c[:, 0] - own[:, 0] <= 0).any():
        # The hidden area holds all of the continent's model cell-days on a pass, so the rest gives no r.
        bad = a[c[:, 0] - own[:, 0] <= 0]
        return {"rich_areas": int(len(rich)), "status": "cannot be tested: an area holds all of the continent's "
                f"{model} cell-days on a pass ({', '.join(bad.r3 + ' ' + bad.dn)})", "pass": False}
    a["r_reg"] = (c[:, 1] - own[:, 1]) / (c[:, 0] - own[:, 0])
    a["r_par"] = (p[:, 1] - own[:, 1] + PARENT_K * a.r_reg) / (p[:, 0] - own[:, 0] + PARENT_K)
    me = yr[yr.r3.isin(rich)].merge(a[["r3", "dn", "r_reg", "r_par"]], on=["r3", "dn"])
    me["p_reg"], me["p_par"] = me[model] * me.r_reg, me[model] * me.r_par
    e = me.groupby(["r3", "y"])[["snpp", "p_reg", "p_par"]].sum().reset_index()
    e = e[e.snpp > 0]
    e["e_reg"] = (e.p_reg - e.snpp).abs() / e.snpp * 100
    e["e_par"] = (e.p_par - e.snpp).abs() / e.snpp * 100
    areas = e.r3.unique()
    by = {r: d[["e_reg", "e_par"]].to_numpy() for r, d in e.groupby("r3")}
    bs = []
    for _ in range(B_AREAS):
        d = np.concatenate([by[r] for r in rng.choice(areas, len(areas))])
        bs.append(np.median(d[:, 0]) - np.median(d[:, 1]))
    lo, hi = ci(bs)
    diff = float(e.e_reg.median() - e.e_par.median())
    return {"rich_areas": int(len(areas)), "area_years": int(len(e)),
            "error_continent_r": round(float(e.e_reg.median()), 2), "error_parent_r2": round(float(e.e_par.median()), 2),
            "diff_pts": round(diff, 2), "diff_ci95": [lo, hi], "diff_sd": round(float(np.std(bs)), 2),
            "status": "pass" if lo > 0 else "fail", "pass": bool(lo > 0)}


def paired(rng, base, new, level, min_obs, years) -> dict:
    """Paired change new - base in a typical error, resampling the same calibration years for both."""
    eb, en = errors_by_year(base, level, min_obs), errors_by_year(new, level, min_obs)
    ys = [y for y in years if y in eb and y in en]
    med = lambda e, s: np.median(np.concatenate([e[y] for y in s]))
    bs = boot(rng, ys, lambda s: med(en, s) - med(eb, s))
    return {"base": round(float(med(eb, ys)), 2), "new": round(float(med(en, ys)), 2),
            "change_pts": round(float(med(en, ys) - med(eb, ys)), 2), "ci95": ci(bs), "sd": round(float(bs.std()), 3)}


def standin_report(g: pd.DataFrame, model: str, cfg: Config, base: dict) -> dict:
    """Upgrade 1 (PREREGISTRATION.md §7, 2026-11-15): rule 6, then rules 1-5 as no-harm checks."""
    rng = np.random.default_rng(SEED)
    k, cal = float(cfg["harmonization"]["shrinkage_k"]), cfg.calibration_years
    out = {"rule6": rule6(rng, g, model, cal)}
    if not out["rule6"]["pass"]:
        out["kept"] = False
        return out
    half = len(cal) // 2
    run = lambda pk: (pd.concat([F.predict(g, model, F.fit(g, model, [t for t in cal if t != y], k, pk), [y])
                                 for y in cal]),
                      F.predict(g, model, F.fit(g, model, cal[half:], k, pk), cal[:half]))
    (lb, bb), (ln, bn) = run(None), run(PARENT_K)
    moved = (ln.pred - lb.pred).abs() > 1e-9  # same rows in the same order: both come from g's groupby
    out["predictions_changed"] = {"area_months": int(moved.sum()),
                                  "share_of_predicted_pct": round(float(lb.pred[moved].sum() / lb.pred.sum() * 100), 4)}
    out["rule1_small_area"] = paired(rng, lb, ln, "block", 50, cal)
    w = paired(rng, lb, ln, "region", 100, cal)
    w["margin"] = round(max(2.0, 2 * w["sd"]), 3)
    w["status"] = "pass" if w["change_pts"] <= w["margin"] else "fail"
    out["rule2_whole_area"] = w
    gb, gn = base["rule4_backward_gap"], gap_rule(rng, bn, cal[:half])
    r4 = {}
    for key in ("all", "D", "N"):
        b, n = gb[key], gn[key]
        if b.get("status") == "pass":
            st = n["status"]
        else:
            st = "pass" if abs(n["gap_pct"]) - abs(b["gap_pct"]) <= GAP_SLACK else "fail"
        r4[key] = {"base": b.get("gap_pct"), "new": n.get("gap_pct"), "base_status": b.get("status"), "status": st}
    out["rule4_backward_gap"] = r4
    c5 = coverage_rule(ln, cal)
    bpass = base["rule5_range_coverage"]["status"] == "pass"
    out["rule5_range_coverage"] = {"base": base["rule5_range_coverage"]["block_pct"], "new": c5["block_pct"],
                                   "status": c5["status"] if bpass else "not required (baseline fails)"}
    out["rule3_tilt_reported"] = tilt_rule(rng, ln, cal)
    harm_ok = (w["status"] == "pass" and all(v["status"] == "pass" for v in r4.values())
               and out["rule5_range_coverage"]["status"] != "fail")
    out["kept"] = bool(out["rule6"]["pass"] and harm_ok)
    return out


def area_report(rng, g: pd.DataFrame, model: str, cfg: Config) -> dict:
    k = float(cfg["harmonization"]["shrinkage_k"])
    cal = cfg.calibration_years
    loyo = pd.concat([F.predict(g, model, F.fit(g, model, [t for t in cal if t != y], k), [y]) for y in cal])
    half = len(cal) // 2
    back = F.predict(g, model, F.fit(g, model, cal[half:], k), cal[:half])
    mm = F.misses(loyo)
    app_cover = F.coverage_by_size(mm, cal)  # the app's ranges, by size of area (§7, 2026-11-15)
    return {
        "whole_area": score(rng, loyo, "region", 100, cal),
        "small_area_2deg": score(rng, loyo, "block", 50, cal),
        "rule3_tilt": tilt_rule(rng, loyo, cal),
        "rule4_backward_gap": {"fit": [cal[half], cal[-1]], "predict": [cal[0], cal[half - 1]],
                               **gap_rule(rng, back, cal[:half])},
        "rule5_range_coverage": {**coverage_rule(loyo, cal), "app_ranges_by_size_pct": app_cover},
        "fair_cell_days": {s: int(g[g.sat == s].n.sum()) for s in (model, "snpp")},
    }


def app_ranges(r: dict) -> dict:
    return r["rule5_range_coverage"]["app_ranges_by_size_pct"]


def run(cfg: Config) -> None:
    rng = np.random.default_rng(SEED)
    out = {"bootstrap": {"seed": SEED, "B": B, "resample": "calibration years"}, "areas": {}}
    data = {m: F.load(cfg, m) for m in MODELS}
    areas = sorted(set().union(*(set(g.continent) for g in data.values())))
    for area in areas:
        out["areas"][area], kept = {}, False
        for model in MODELS:
            g = data[model]
            g = g[g.continent == area].drop(columns="continent")
            if not F.fittable(g, model, cfg.calibration_years):
                out["areas"][area][model] = {"status": "cannot be fitted: a training set has no fair cell-days "
                                                       "of both satellites on a pass"}
                print(f"{area:14s} {model:5s} cannot be fitted", flush=True)
                continue
            r = area_report(rng, g, model, cfg)
            if model == "aqua":
                r["standin_r2"] = standin_report(g, model, cfg, r)
                kept = r["standin_r2"]["kept"]
                print(f"{area:14s} stand-in {json.dumps(r['standin_r2'])}", flush=True)
            elif kept:  # Terra follows Aqua's decision, reported only
                srng, cal, k = np.random.default_rng(SEED), cfg.calibration_years, float(cfg["harmonization"]["shrinkage_k"])
                lo = lambda pk: pd.concat([F.predict(g, model, F.fit(g, model, [t for t in cal if t != y], k, pk), [y])
                                           for y in cal])
                lb, ln = lo(None), lo(PARENT_K)
                r["standin_r2"] = {"reported_only": True, "small_area": paired(srng, lb, ln, "block", 50, cal),
                                   "whole_area": paired(srng, lb, ln, "region", 100, cal)}
            out["areas"][area][model] = r
            t, gp = r["rule3_tilt"], r["rule4_backward_gap"]
            print(f"{area:14s} {model:5s} whole {r['whole_area']['median']} (sd {r['whole_area'].get('sd')})  "
                  f"small {r['small_area_2deg']['median']} (sd {r['small_area_2deg'].get('sd')})  "
                  f"tilt D {t.get('D', {}).get('b')} {t.get('D', {}).get('status')}, "
                  f"N {t.get('N', {}).get('b')} {t.get('N', {}).get('status')}  "
                  f"gap {gp.get('all', {}).get('gap_pct')} {gp.get('all', {}).get('status')}  "
                  f"cover {r['rule5_range_coverage']['block_pct']}  app ranges {json.dumps(app_ranges(r))}",
                  flush=True)
    (cfg.dir("model") / "report.json").write_text(json.dumps(out, indent=1))
