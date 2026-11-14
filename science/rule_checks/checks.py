"""Check whether each proposed model-selection rule can be decided by the data.

Uses the baseline model family only (Aqua -> S-NPP ratio of sums, day/night, H3 strata with
shrinkage), in the exploratory Argentina box. No upgrade candidate is fitted here.
Run: uv run --python 3.13 --with duckdb --with pandas --with numpy --with pyarrow checks.py
"""
import itertools, json, pathlib
import numpy as np, pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
D = ROOT / "data" / "derived" / "rule_checks"
rng = np.random.default_rng(20261114)
CAL = list(range(2013, 2023)); TEST = [2023, 2024, 2025]; B = 4000
out = {}

m = pd.read_parquet(D / "monthly.parquet")
m = m[m.y >= 2013]
KEY = ["y", "m", "dn", "blat", "blon"]
obs = m[m.sat == "snpp"].groupby(KEY).n.sum().rename("obs")
aq = m[m.sat == "aqua"]
A = {lv: aq.groupby(KEY + [lv]).n.sum().rename("a").reset_index() for lv in ("r3", "r2")}
A[None] = aq.groupby(KEY).n.sum().rename("a").reset_index()
def yearly(lv):
    g = ["y", "dn"] + ([lv] if lv else [])
    s = m.groupby(g + ["sat"]).n.sum().unstack("sat").fillna(0)
    return s.reset_index()
Y = {lv: yearly(lv) for lv in ("r3", "r2", None)}

def ratios(train, lv, k):
    reg = Y[None][Y[None].y.isin(train)].groupby("dn")[["aqua", "snpp"]].sum()
    reg = (reg.snpp / reg.aqua).rename("rreg")
    if lv is None:
        return reg
    s = Y[lv][Y[lv].y.isin(train)].groupby([lv, "dn"])[["aqua", "snpp"]].sum().reset_index().join(reg, on="dn")
    s["r"] = (s.snpp + k * s.rreg) / (s.aqua + k)
    return s.set_index([lv, "dn"]).r, reg

def predict(years, train, lv, k):
    a = A[lv][A[lv].y.isin(years)]
    if lv is None:
        r = a.dn.map(ratios(train, None, 0))
    else:
        rs, reg = ratios(train, lv, k)
        r = pd.Series(pd.MultiIndex.from_frame(a[[lv, "dn"]]).map(rs), index=a.index).fillna(a.dn.map(reg))
    p = (a.a * r).groupby([a[c] for c in KEY]).sum().rename("pred")
    o = obs[obs.index.get_level_values("y").isin(years)]
    return pd.concat([o, p], axis=1).fillna(0).reset_index()

def loyo(lv, k, years=CAL):
    return pd.concat([predict([y], [t for t in years if t != y], lv, k) for y in years])

def agg(df, by):  # sum day+night unless 'dn' in by
    return df.groupby(by)[["obs", "pred"]].sum().reset_index()
REG = ["y", "m"]; BLK = ["y", "m", "blat", "blon"]
def ape(df, by, minobs):
    g = agg(df, by); g = g[g.obs >= minobs]
    return g.assign(ape=(g.pred - g.obs).abs() / g.obs * 100)
def by_year(df, col):
    return {y: v[col].to_numpy() for y, v in df.groupby("y")}
def boot(fn, years):
    ys = np.array(years)
    return np.array([fn(rng.choice(ys, len(ys))) for _ in range(B)])
def ci(x): return [round(float(v), 3) for v in np.percentile(x, [2.5, 97.5])]

CANDS = [(None, 0)] + list(itertools.product(("r2", "r3"), (50, 200, 1000)))
L = {c: loyo(*c) for c in CANDS}
base = L[("r3", 50)]

# ---- B. How much do the median and p90 errors move by chance? -------------------------------
def metric_noise(c, by, minobs):
    e = by_year(ape(L[c], by, minobs), "ape")
    allv = np.concatenate(list(e.values()))
    bs = boot(lambda ys: np.percentile(np.concatenate([e[y] for y in ys]), [50, 90]), CAL)
    return dict(n=len(allv), median=round(float(np.median(allv)), 2), p90=round(float(np.percentile(allv, 90)), 2),
                sd_median=round(float(bs[:, 0].std()), 2), sd_p90=round(float(bs[:, 1].std()), 2))
def paired(c1, c2, by, minobs):
    e1, e2 = ape(L[c1], by, minobs), ape(L[c2], by, minobs)
    e1, e2 = by_year(e1, "ape"), by_year(e2, "ape")
    f = lambda ys: (np.percentile(np.concatenate([e1[y] for y in ys]), [50, 90])
                    - np.percentile(np.concatenate([e2[y] for y in ys]), [50, 90]))
    bs = boot(f, CAL); d = f(CAL)
    return dict(diff_median=round(float(d[0]), 2), sd=round(float(bs[:, 0].std()), 2), ci95=ci(bs[:, 0]),
                diff_p90=round(float(d[1]), 2), sd_p90=round(float(bs[:, 1].std()), 2), ci95_p90=ci(bs[:, 1]))
out["B_metric_noise"] = {
    "region": metric_noise(("r3", 50), REG, 100),
    "block2deg_min50": metric_noise(("r3", 50), BLK, 50),
    "block2deg_min500": metric_noise(("r3", 50), BLK, 500),
    "paired_r3k50_minus_r3k200_region": paired(("r3", 50), ("r3", 200), REG, 100),
    "paired_r3k50_minus_r3k200_block50": paired(("r3", 50), ("r3", 200), BLK, 50),
    "paired_r3k50_minus_nostrata_region": paired(("r3", 50), (None, 0), REG, 100),
    "paired_r3k50_minus_nostrata_block50": paired(("r3", 50), (None, 0), BLK, 50),
}
out["B_candidates"] = {f"{c[0]}_k{c[1]}": dict(region=round(float(ape(L[c], REG, 100).ape.median()), 2),
                       block50=round(float(ape(L[c], BLK, 50).ape.median()), 2)) for c in CANDS}

# ---- A. Decile-bias rule vs a slope test -----------------------------------------------------
def decile_check(g, label):
    g = g[(g.obs > 0) & (g.pred > 0)].copy()
    g["res"] = np.log(g.obs / g.pred); g["lp"] = np.log(g.pred)
    g["dec"] = pd.qcut(g.lp, 10, labels=False)
    dec = (np.expm1(g.groupby("dec").res.mean()) * 100).round(1).tolist()
    r = (g.res - g.res.mean()).to_numpy(); d = g.dec.to_numpy()
    null = np.array([np.abs(np.expm1(pd.Series(rng.permutation(r)).groupby(d).mean())).max() * 100 for _ in range(2000)])
    gy = {y: v for y, v in g.groupby("y")}
    def slope(ys):
        x = np.concatenate([gy[y].lp for y in ys]); z = np.concatenate([gy[y].res for y in ys])
        return np.polyfit(x, z, 1)[0]
    bs = boot(slope, CAL)
    VIZ_STASH[label] = (g[['y', 'm', 'pred', 'obs']].copy(), null, np.polyfit(g.lp, g.res, 1))
    return dict(scale=label, n=len(g), per_decile_n=int(len(g) / 10), decile_bias_pct_obs_over_pred=dec,
                null_max_abs_decile_bias_median=round(float(np.median(null)), 1),
                null_prob_fail_3pct=round(float((null > 3).mean()), 3),
                slope=round(float(slope(CAL)), 3), slope_ci95=ci(bs), slope_sd=round(float(bs.std()), 3))
A_out = []; VIZ_STASH = {}
for dn in ("D", "N"):
    A_out.append(decile_check(agg(base[base.dn == dn], REG), f"region {dn}"))
    A_out.append(decile_check(agg(base[base.dn == dn], ["y", "m", "blat", "blon"]).query("obs >= 50"), f"block>=50 {dn}"))
A_out.append(decile_check(agg(base, REG), "region D+N"))
out["A_decile_vs_slope"] = A_out

# ---- C. Seam gap: in-sample vs out of sample -------------------------------------------------
def gap(df, years):
    g = agg(df, ["y"]); gy = g.set_index("y")
    f = lambda ys: np.log(gy.pred.loc[list(ys)].sum() / gy.obs.loc[list(ys)].sum()) * 100
    bs = boot(f, years)
    return dict(gap_pct=round(float(f(years)), 2), ci95=ci(bs),
                by_year={int(y): round(float(np.log(r.pred / r.obs) * 100), 1) for y, r in gy.iterrows()})
def gaps(df, years):
    return {"all": gap(df, years), "day": gap(df[df.dn == "D"], years), "night": gap(df[df.dn == "N"], years)}
out["C_seam"] = {
    "in_sample_2013_2022": gaps(predict(CAL, CAL, "r3", 50), CAL),
    "loyo_2013_2022": gaps(base, CAL),
    "backward_fit2018_22_pred2013_17": gaps(predict(CAL[:5], CAL[5:], "r3", 50), CAL[:5]),
    "forward_fit2013_17_pred2018_22": gaps(predict(CAL[5:], CAL[:5], "r3", 50), CAL[5:]),
    "heldout_2023_2025": gaps(predict(TEST, CAL, "r3", 50), TEST),
}
bw = predict(CAL[:5], CAL[5:], "r3", 50)
out["C_backward_errors"] = dict(region_median=round(float(ape(bw, REG, 100).ape.median()), 2),
                                region_p90=round(float(ape(bw, REG, 100).ape.quantile(.9)), 2),
                                loyo_same_years_median=round(float(ape(base[base.y <= 2017], REG, 100).ape.median()), 2))

# ---- D. Bands from past errors: honest vs circular coverage ----------------------------------
def coverage(g, nbins):
    g = g[(g.pred > 0)].copy(); zero = float((g.obs == 0).mean())
    g = g[g.obs > 0]; g["res"] = np.log(g.obs / g.pred)
    g["bin"] = pd.qcut(np.log(g.pred), nbins, labels=False) if nbins > 1 else 0
    honest, circ = {}, {}
    for y in CAL:
        te = g[g.y == y]
        for name, tr, store in (("h", g[g.y != y], honest), ("c", g, circ)):
            q = tr.groupby("bin").res.quantile([.1, .9]).unstack()
            lo, hi = te.bin.map(q[.1]), te.bin.map(q[.9])
            store[y] = float(((te.res >= lo) & (te.res <= hi)).mean() * 100)
    h = np.array(list(honest.values())); c = np.array(list(circ.values()))
    return dict(n=len(g), share_obs_zero=round(zero, 3), honest_mean=round(float(h.mean()), 1),
                honest_by_year=[round(float(v)) for v in h], honest_min=round(float(h.min())), honest_max=round(float(h.max())),
                circular_mean=round(float(c.mean()), 1),
                band_width_pct=[round(float(np.expm1(v) * 100)) for v in g.res.quantile([.1, .9])])
out["D_bands_80pct"] = {"region_month": coverage(agg(base, REG), 1),
                        "block_month_5bins": coverage(agg(base, BLK), 5)}

# ---- E. Fallback rule: sparse blocks vs leaving whole strata out ------------------------------
blk = agg(base, BLK)
tot = blk.groupby(["blat", "blon"]).obs.sum()
sparse = tot[tot <= tot.quantile(1 / 3)].index
sb = blk.set_index(["blat", "blon"]).loc[sparse].reset_index()
sb_sc = sb[sb.obs >= 50].assign(ape=lambda d: (d.pred - d.obs).abs() / d.obs * 100)
e = by_year(sb_sc, "ape")
bs = boot(lambda ys: np.median(np.concatenate([e.get(y, np.array([])) for y in ys])), CAL)
E = dict(sparse_blocks=len(sparse), block_months=len(sb), share_scorable_min50=round(len(sb_sc) / len(sb), 3),
         share_obs_zero=round(float((sb.obs == 0).mean()), 3), median_ape=round(float(sb_sc.ape.median()), 1),
         sd_median=round(float(np.nanstd(bs)), 1))
# leave-stratum-out: predict data-rich res-3 strata from the region ratio vs their res-2 parent's ratio
s3 = Y["r3"][Y["r3"].y.isin(CAL)]
par = m[["r3", "r2"]].drop_duplicates("r3").set_index("r3").r2
tot3 = s3.groupby("r3").aqua.sum(); rich = tot3[tot3 >= 2000].index
reg = s3.groupby("dn")[["aqua", "snpp"]].sum()
rows = []
for r in rich:
    oth = s3[s3.r3 != r]
    rr = oth.groupby("dn")[["aqua", "snpp"]].sum(); rr = rr.snpp / rr.aqua
    op = oth[oth.r3.map(par) == par[r]].groupby("dn")[["aqua", "snpp"]].sum().reindex(["D", "N"]).fillna(0)
    rp = (op.snpp + 200 * rr) / (op.aqua + 200)
    me = s3[s3.r3 == r].groupby(["y", "dn"])[["aqua", "snpp"]].sum().reset_index()
    me["p_reg"] = me.aqua * me.dn.map(rr); me["p_par"] = me.aqua * me.dn.map(rp)
    g = me.groupby("y")[["snpp", "p_reg", "p_par"]].sum()
    rows.append(pd.DataFrame(dict(r3=r, y=g.index, e_reg=(g.p_reg - g.snpp).abs() / g.snpp * 100,
                                  e_par=(g.p_par - g.snpp).abs() / g.snpp * 100)))
lso = pd.concat(rows)
strata = lso.r3.unique()
def f(_):
    pick = rng.choice(strata, len(strata)); d = pd.concat([lso[lso.r3 == s] for s in pick])
    return [d.e_reg.median(), d.e_par.median(), d.e_reg.median() - d.e_par.median()]
bs = np.array([f(0) for _ in range(1000)])
E.update(leave_stratum_out=dict(rich_strata=len(strata), stratum_years=len(lso),
         median_ape_region_fallback=round(float(lso.e_reg.median()), 1), median_ape_parent_fallback=round(float(lso.e_par.median()), 1),
         sd_each=[round(float(bs[:, 0].std()), 1), round(float(bs[:, 1].std()), 1)],
         paired_diff=round(float(lso.e_reg.median() - lso.e_par.median()), 1), paired_diff_ci95=ci(bs[:, 2])))
out["E_fallback"] = E

# ---- F. Nested cross-validation: how optimistic is selecting on the reporting folds? ----------
def score(df): return float(ape(df, BLK, 50).ape.median())
flat_pick = min(CANDS, key=lambda c: score(L[c]))
nested, picks = [], {}
for y in CAL:
    inner = [t for t in CAL if t != y]
    best = min(CANDS, key=lambda c: score(loyo(*c, years=inner)))
    picks[y] = f"{best[0]}_k{best[1]}"
    nested.append(predict([y], inner, *best))
nested = pd.concat(nested)
def both(df): return dict(region=round(float(ape(df, REG, 100).ape.median()), 2), block50=round(score(df), 2))
out["F_nested"] = dict(flat_pick=f"{flat_pick[0]}_k{flat_pick[1]}", flat=both(L[flat_pick]), nested=both(nested), picks_by_year=picks)

# ---- G. Outage rule: does "no detection anywhere in the box" find the known gaps? -------------
p = pd.read_parquet(D / "presence.parquet"); G = {}
for sat in ("aqua", "snpp"):
    have = set(pd.to_datetime(p[p.sat == sat].d).dt.date)
    days = pd.date_range("2012-02-01", "2025-12-30").date
    miss = [d for d in days if d not in have]; runs = []
    for d in miss:
        if runs and (d - runs[-1][1]).days == 1: runs[-1][1] = d
        else: runs.append([d, d])
    G[sat] = dict(missing_days=len(miss), runs_3plus=[f"{a}..{b} ({(b - a).days + 1}d)" for a, b in runs if (b - a).days >= 2])
out["G_outages"] = G

(pathlib.Path(__file__).parent / "results.json").write_text(json.dumps(out, indent=1, default=str))
print(json.dumps(out, indent=1, default=str))

# ---- Data for the teaching page ---------------------------------------------------------------
viz = dict(results=out)
ra = agg(base, REG).merge(A[None].groupby(REG).a.sum().reset_index(), on=REG)
te = agg(predict(TEST, CAL, "r3", 50), REG).merge(A[None].groupby(REG).a.sum().reset_index(), on=REG)
ser = pd.concat([ra, te]).sort_values(REG)
viz["series"] = dict(ym=[f"{y}-{mm:02d}" for y, mm in zip(ser.y, ser.m)], aqua=ser.a.round().astype(int).tolist(),
                     viirs=ser.obs.round().astype(int).tolist(), conv=ser.pred.round().astype(int).tolist())
rr = ratios(CAL, None, 0)
viz["ratios"] = dict(day=round(float(rr["D"]), 2), night=round(float(rr["N"]), 2))
def pack(label):
    g, null, fit = VIZ_STASH[label]
    h, edges = np.histogram(null, bins=np.arange(0, np.ceil(null.max()) + 1, 1.0 if null.max() > 12 else 0.5))
    return dict(pts=[[int(a), int(b), round(float(c)), round(float(d))] for a, b, c, d in g.to_numpy()],
                fit=[round(float(fit[0]), 4), round(float(fit[1]), 4)], hist=h.tolist(), edges=[round(float(e), 2) for e in edges])
viz["activity"] = {k: pack(k) for k in ("region D", "region N", "block>=50 D")}
for k in ("block>=50 D",): viz["activity"][k].pop("pts")
pp = p[(pd.to_datetime(p.d) >= "2022-06-15") & (pd.to_datetime(p.d) <= "2022-09-05")]
days = [str(d.date()) for d in pd.date_range("2022-06-15", "2022-09-05")]
viz["outage"] = dict(days=days, **{s: [int(dict(zip(pp[pp.sat == s].d.astype(str), pp[pp.sat == s].n_cells)).get(d, 0)) for d in days] for s in ("aqua", "snpp")})
(pathlib.Path(__file__).parent / "viz_data.json").write_text(json.dumps(viz, default=str))
