"""silver -> model/seasonal_report.json: seasonal multipliers, tested per study area.

PREREGISTRATION.md §7 (2026-11-15, upgrade 2). Each res-3 area gets a multiplier per season (DJF, MAM, JJA,
SON by calendar month) and pass, shrunk toward the area's multiplier of the current version with k = 50:
    r_s,q = (V_s,q + k r_s) / (M_s,q + k)
where r_s is the current multiplier (its own; its res-2 parent's where the stand-in is kept and it has no data;
otherwise the continent's). A season with no data gets r_s.

Against the current accepted version, on Aqua:
  rule 1  small-area gain >= 0.5 points, paired luck range entirely on the improving side
  rule 2  whole-area loss <= max(2, 2 x paired SD)
  rule 4  still passes where the current version passes; where it fails, at most 0.5 points further from zero
  rule 5  the app's ranges by size, rebuilt from the seasonal misses, 75-85 % for res-4, res-3 and 2-degree blocks
  rule 3  reported
Kept only if rules 1, 2, 4 and 5 pass. Terra is reported where Aqua keeps it.
"""
import json

import numpy as np
import pandas as pd

from . import fit as F
from . import report as R
from .config import Config

SEASON = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM",
          6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"}
SMALL_GAIN, GAP_SLACK = 0.5, 0.5


def area_mult(m: dict, dn: str, r3: str, r2: str) -> float:
    return m["strata"].get(dn, {}).get(r3, m.get("parents", {}).get(dn, {}).get(r2, m["region"][dn]))


def fit_seasonal(g: pd.DataFrame, model: str, years, k: float, pk) -> dict:
    base = F.fit(g, model, years, k, pk)
    t = g[g.y.isin(years)].assign(q=lambda d: d.mo.map(SEASON))
    s = t.groupby(["r3", "r2", "dn", "q", "sat"]).n.sum().unstack("sat", fill_value=0)
    s = s.reindex(columns=[model, "snpp"], fill_value=0).reset_index()
    rs = np.array([area_mult(base, dn, r3, r2) for dn, r3, r2 in zip(s.dn, s.r3, s.r2)])
    s["r"] = (s.snpp + k * rs) / (s[model] + k)
    base["seasons"] = {(dn, r3, q): r for dn, r3, q, r in zip(s.dn, s.r3, s.q, s.r)}
    return base


def predict_seasonal(g: pd.DataFrame, model: str, m: dict, years) -> pd.DataFrame:
    a = g[(g.sat == model) & g.y.isin(years)].copy()
    a["pred"] = [n * m["seasons"].get((dn, r3, SEASON[mo]), area_mult(m, dn, r3, r2))
                 for n, dn, r3, r2, mo in zip(a.n, a.dn, a.r3, a.r2, a.mo)]
    v = g[(g.sat == "snpp") & g.y.isin(years)].rename(columns={"n": "obs"})
    keys = ["y", "mo", "dn", "r3", "r4", "blat", "blon"]
    return pd.concat([a[keys + ["pred"]], v[keys + ["obs"]]]).fillna(0).groupby(keys, as_index=False).sum()


def test(g: pd.DataFrame, model: str, cfg: Config, pk) -> dict:
    rng = np.random.default_rng(R.SEED)
    k, cal = float(cfg["harmonization"]["shrinkage_k"]), cfg.calibration_years
    half = len(cal) // 2
    lb = pd.concat([F.predict(g, model, F.fit(g, model, [t for t in cal if t != y], k, pk), [y]) for y in cal])
    bb = F.predict(g, model, F.fit(g, model, cal[half:], k, pk), cal[:half])
    ln = pd.concat([predict_seasonal(g, model, fit_seasonal(g, model, [t for t in cal if t != y], k, pk), [y])
                    for y in cal])
    bn = predict_seasonal(g, model, fit_seasonal(g, model, cal[half:], k, pk), cal[:half])
    out = {}
    r1 = R.paired(rng, lb, ln, "block", 50, cal)
    r1["status"] = "pass" if r1["change_pts"] <= -SMALL_GAIN and r1["ci95"][1] < 0 else "fail"
    out["rule1_small_area"] = r1
    r2 = R.paired(rng, lb, ln, "region", 100, cal)
    r2["margin"] = round(max(2.0, 2 * r2["sd"]), 3)
    r2["status"] = "pass" if r2["change_pts"] <= r2["margin"] else "fail"
    out["rule2_whole_area"] = r2
    gc, gn = R.gap_rule(rng, bb, cal[:half]), R.gap_rule(rng, bn, cal[:half])
    r4 = {}
    for key in ("all", "D", "N"):
        c, n = gc[key], gn[key]
        st = n["status"] if c.get("status") == "pass" else (
            "pass" if abs(n["gap_pct"]) - abs(c["gap_pct"]) <= GAP_SLACK else "fail")
        r4[key] = {"current": c.get("gap_pct"), "new": n.get("gap_pct"), "current_status": c.get("status"), "status": st}
    r4["status"] = "pass" if all(r4[x]["status"] == "pass" for x in ("all", "D", "N")) else "fail"
    out["rule4_backward_gap"] = r4
    cc, cn = F.coverage_by_size(F.misses(lb), cal), F.coverage_by_size(F.misses(ln), cal)
    out["rule5_app_ranges"] = {"current": cc, "new": cn, "status": cn["status"]}
    out["rule3_tilt_reported"] = {"current": R.tilt_rule(rng, lb, cal), "new": R.tilt_rule(rng, ln, cal)}
    out["kept"] = all(out[r]["status"] == "pass" for r in
                      ("rule1_small_area", "rule2_whole_area", "rule4_backward_gap", "rule5_app_ranges"))
    return out


def run(cfg: Config) -> None:
    out = {"bootstrap": {"seed": R.SEED, "B": R.B}, "areas": {}}
    data = {m: F.load(cfg, m) for m in R.MODELS}
    for area in sorted(set().union(*(set(g.continent) for g in data.values()))):
        res, kept = {}, False
        for model in R.MODELS:
            if model == "terra" and not kept:
                res[model] = {"status": "not tested: Aqua did not keep seasonal multipliers here"}
                continue
            g = data[model]
            g = g[g.continent == area].drop(columns="continent")
            if g.empty or not F.fittable(g, model, cfg.calibration_years):
                res[model] = {"status": "cannot be fitted"}
                print(f"{area:14s} {model:5s} cannot be fitted", flush=True)
                continue
            r = test(g, model, cfg, F.parent_k(cfg, area))
            if model == "terra":
                r["reported_only"] = True
            res[model] = r
            kept = kept or (model == "aqua" and r["kept"])
            r4 = r["rule4_backward_gap"]
            print(f"{area:14s} {model:5s} kept {r['kept']}  small {r['rule1_small_area']['base']}->{r['rule1_small_area']['new']} "
                  f"{r['rule1_small_area']['ci95']}  whole {r['rule2_whole_area']['base']}->{r['rule2_whole_area']['new']}  "
                  f"gap all {r4['all']['current']}->{r4['all']['new']} N {r4['N']['current']}->{r4['N']['new']} {r4['status']}  "
                  f"ranges {r['rule5_app_ranges']['status']}", flush=True)
        out["areas"][area] = res
    (cfg.dir("model") / "seasonal_report.json").write_text(json.dumps(out, indent=1))
