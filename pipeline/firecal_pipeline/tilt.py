"""silver -> model/tilt_report.json: the tilt correction by fire strength, tested per study area.

PREREGISTRATION.md §7 (2026-11-15, upgrade 3). Each MODIS cell-day falls in one of three FRP classes (tercile
edges of MODIS cell-day FRP on fair units in the training years, per continent and pass); class weights are
fitted by Poisson maximum likelihood on res-3 area-months, and each area gets a correction toward 1 (k = 50;
its res-2 parent's with k = 200 where the stand-in is kept). fit.py: frp_edges, load_frp, fit_frp, predict_frp.

Against the current accepted version (baseline, stand-in where kept, app ranges by size), on Aqua:
  rule 3  must pass by day and at night (too noisy to test counts as not passing)
  rule 1  small-area gain >= 0.5 points, paired luck range entirely on the improving side
  rule 2  whole-area loss <= max(2, 2 x paired SD)
  rule 4  backward-join gap as written (+-7 % all and day, +-10 % night)
  rule 5  the app's ranges by size, rebuilt from the corrected misses, 75-85 % for res-4, res-3 and 2-degree blocks
Kept only if all pass. Terra is reported where Aqua keeps it. Luck ranges: report.py's bootstrap, own generator
per study area (seed 20261114).
"""
import json

import numpy as np
import pandas as pd

from . import fit as F
from . import report as R
from .config import Config, connect

SMALL_GAIN = 0.5


def small_tilt(p: pd.DataFrame) -> dict:
    """Tilt on 2-degree block-months (reported only)."""
    out = {}
    for dn, d in p.groupby("dn"):
        a = d.groupby(["y", "mo", "blat", "blon"])[["pred", "obs"]].sum()
        a = a[(a.pred > 0) & (a.obs > 0)]
        if len(a) < 3:  # too few block-months to fit a line; reported only, so don't stop the run
            out[dn] = None
            continue
        out[dn] = round(float(np.polyfit(np.log(a.pred), np.log(a.obs / a.pred), 1)[0]), 3)
    return out


def versions(g, model, cfg, pk):
    k, cal = float(cfg["harmonization"]["shrinkage_k"]), cfg.calibration_years
    half = len(cal) // 2
    cur = (pd.concat([F.predict(g, model, F.fit(g, model, [t for t in cal if t != y], k, pk), [y]) for y in cal]),
           F.predict(g, model, F.fit(g, model, cal[half:], k, pk), cal[:half]))
    new = (pd.concat([F.predict_frp(g, model, F.fit_frp(g, model, f"y{y}", [t for t in cal if t != y], k, pk), [y])
                      for y in cal]),
           F.predict_frp(g, model, F.fit_frp(g, model, "back", cal[half:], k, pk), cal[:half]))
    return cur, new, F.fit_frp(g, model, "all", cal, k, pk)


def test(g, model, cfg, pk) -> dict:
    rng = np.random.default_rng(R.SEED)
    cal = cfg.calibration_years
    half = len(cal) // 2
    (lb, bb), (ln, bn), final = versions(g, model, cfg, pk)
    out = {"beta_all": {dn: [round(b, 4) for b in v] for dn, v in final["beta"].items()}}
    t_cur, t_new = R.tilt_rule(rng, lb, cal), R.tilt_rule(rng, ln, cal)
    out["rule3_tilt"] = {"current": t_cur, "new": t_new,
                         "status": "pass" if all(t_new.get(dn, {}).get("status") == "pass" for dn in ("D", "N")) else "fail"}
    out["small_area_tilt_reported"] = {"current": small_tilt(lb), "new": small_tilt(ln)}
    r1 = R.paired(rng, lb, ln, "block", 50, cal)
    r1["status"] = "pass" if r1["change_pts"] <= -SMALL_GAIN and r1["ci95"][1] < 0 else "fail"
    out["rule1_small_area"] = r1
    r2 = R.paired(rng, lb, ln, "region", 100, cal)
    r2["margin"] = round(max(2.0, 2 * r2["sd"]), 3)
    r2["status"] = "pass" if r2["change_pts"] <= r2["margin"] else "fail"
    out["rule2_whole_area"] = r2
    g_cur, g_new = R.gap_rule(rng, bb, cal[:half]), R.gap_rule(rng, bn, cal[:half])
    out["rule4_backward_gap"] = {"current": g_cur, "new": g_new,
                                 "status": "pass" if all(g_new[k].get("status") == "pass" for k in ("all", "D", "N")) else "fail"}
    c_cur, c_new = F.coverage_by_size(F.misses(lb), cal), F.coverage_by_size(F.misses(ln), cal)
    out["rule5_app_ranges"] = {"current": c_cur, "new": c_new, "status": c_new["status"]}
    out["kept"] = all(out[r]["status"] == "pass" for r in
                      ("rule3_tilt", "rule1_small_area", "rule2_whole_area", "rule4_backward_gap", "rule5_app_ranges"))
    return out


def run(cfg: Config) -> None:
    areas = sorted(set(connect().execute(
        f"SELECT DISTINCT continent FROM read_parquet('{cfg.out / 'silver'}/cell_day.parquet')").df().continent))
    out = {"bootstrap": {"seed": R.SEED, "B": R.B}, "areas": {}}
    for area in areas:
        res, kept = {}, False
        for model in R.MODELS:
            if model == "terra" and not kept:
                res[model] = {"status": "not tested: Aqua did not keep the correction here"}
                continue
            g, edges = F.load_frp(cfg, model, area)
            if g.empty or not F.fittable(g.drop(columns="continent"), model, cfg.calibration_years):
                res[model] = {"status": "cannot be fitted"}
                print(f"{area:14s} {model:5s} cannot be fitted", flush=True)
                continue
            g = g.drop(columns="continent")
            r = test(g, model, cfg, F.parent_k(cfg, area))
            e = edges[edges.fold == "all"]
            r["frp_edges_all_MW"] = {dn: [round(float(x), 2) for x in (d.e1.iloc[0], d.e2.iloc[0])] for dn, d in e.groupby("dn")}
            if model == "terra":
                r["reported_only"] = True
            res[model] = r
            kept = kept or (model == "aqua" and r["kept"])
            t = r["rule3_tilt"]["new"]
            print(f"{area:14s} {model:5s} kept {r['kept']}  tilt D {t.get('D', {}).get('b')} N {t.get('N', {}).get('b')} "
                  f"(was D {r['rule3_tilt']['current'].get('D', {}).get('b')} N {r['rule3_tilt']['current'].get('N', {}).get('b')})  "
                  f"small {r['rule1_small_area']['change_pts']:+} {r['rule1_small_area']['ci95']}  "
                  f"whole {r['rule2_whole_area']['change_pts']:+}  gap {r['rule4_backward_gap']['new']['all'].get('gap_pct')} "
                  f"N {r['rule4_backward_gap']['new']['N'].get('gap_pct')}  ranges {r['rule5_app_ranges']['status']}", flush=True)
        out["areas"][area] = res
    (cfg.dir("model") / "tilt_report.json").write_text(json.dumps(out, indent=1))
