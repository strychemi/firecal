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
            The app's own ranges (fit.py: all area sizes pooled, fixed bins) are reported beside it.

Rules 1, 2 and 6 compare versions, so they apply when an upgrade is tested (§5), not to the baseline alone.
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


def area_report(rng, g: pd.DataFrame, model: str, cfg: Config) -> dict:
    k = float(cfg["harmonization"]["shrinkage_k"])
    cal = cfg.calibration_years
    loyo = pd.concat([F.predict(g, model, F.fit(g, model, [t for t in cal if t != y], k), [y]) for y in cal])
    half = len(cal) // 2
    back = F.predict(g, model, F.fit(g, model, cal[half:], k), cal[:half])
    mm = F.misses(loyo)
    app_cover = F.coverage(mm, "block", cal) if (mm.level == "block").any() else None
    return {
        "whole_area": score(rng, loyo, "region", 100, cal),
        "small_area_2deg": score(rng, loyo, "block", 50, cal),
        "rule3_tilt": tilt_rule(rng, loyo, cal),
        "rule4_backward_gap": {"fit": [cal[half], cal[-1]], "predict": [cal[0], cal[half - 1]],
                               **gap_rule(rng, back, cal[:half])},
        "rule5_range_coverage": {**coverage_rule(loyo, cal), "app_ranges_block_pct": app_cover},
        "fair_cell_days": {s: int(g[g.sat == s].n.sum()) for s in (model, "snpp")},
    }


def run(cfg: Config) -> None:
    rng = np.random.default_rng(SEED)
    out = {"bootstrap": {"seed": SEED, "B": B, "resample": "calibration years"}, "areas": {}}
    data = {m: F.load(cfg, m) for m in MODELS}
    areas = sorted(set().union(*(set(g.continent) for g in data.values())))
    for area in areas:
        out["areas"][area] = {}
        for model in MODELS:
            g = data[model]
            g = g[g.continent == area].drop(columns="continent")
            if not F.fittable(g, model, cfg.calibration_years):
                out["areas"][area][model] = {"status": "cannot be fitted: a training set has no fair cell-days "
                                                       "of both satellites on a pass"}
                print(f"{area:14s} {model:5s} cannot be fitted", flush=True)
                continue
            r = area_report(rng, g, model, cfg)
            out["areas"][area][model] = r
            t, gp = r["rule3_tilt"], r["rule4_backward_gap"]
            print(f"{area:14s} {model:5s} whole {r['whole_area']['median']} (sd {r['whole_area'].get('sd')})  "
                  f"small {r['small_area_2deg']['median']} (sd {r['small_area_2deg'].get('sd')})  "
                  f"tilt D {t.get('D', {}).get('b')} {t.get('D', {}).get('status')}, "
                  f"N {t.get('N', {}).get('b')} {t.get('N', {}).get('status')}  "
                  f"gap {gp.get('all', {}).get('gap_pct')} {gp.get('all', {}).get('status')}  "
                  f"cover {r['rule5_range_coverage']['block_pct']}", flush=True)
    (cfg.dir("model") / "report.json").write_text(json.dumps(out, indent=1))
