"""FRP-floor check: if both sensors count only fires both can detect, does the ratio go to ~1
and the activity slope vanish?

Cell-day FRP = total fire radiative power (MW) of kept detections in one H3 res-8 cell during one
overpass (largest overpass of the day/night). A cell-day counts at floor F if that total >= F.
Run: uv run --python 3.13 --with duckdb --with pandas --with numpy --with pyarrow frp_check.py
"""
import json, pathlib, tempfile, zipfile
import duckdb, numpy as np, pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "data"; OUT = RAW / "derived" / "rule_checks"
BBOX = (-76.0, -56.0, -50.0, -20.0)
COUNTRIES = ["Argentina", "Bolivia", "Brazil", "Chile", "Paraguay", "Uruguay", "Falkland"]
FLOORS = [0, 5, 10, 20, 30, 50, 100, 200]
CAL = list(range(2013, 2023))
rng = np.random.default_rng(20261114)

con = duckdb.connect(str(OUT / "frp.duckdb"))
con.execute("INSTALL h3 FROM community; LOAD h3;")
con.execute("CREATE OR REPLACE TABLE cellfrp(sat VARCHAR, d DATE, dn VARCHAR, cell UBIGINT, frp DOUBLE)")
for y in range(2013, 2026):
    for fam in ("modis", "viirs-snpp"):
        with zipfile.ZipFile(RAW / f"{fam}_{y}_all_countries.zip") as z, tempfile.TemporaryDirectory() as tmp:
            for name in z.namelist():
                if not name.endswith(".csv") or not any(c in name for c in COUNTRIES):
                    continue
                p = z.extract(name, tmp)
                sat, keep = (("'aqua'", "satellite = 'Aqua' AND type = 0 AND TRY_CAST(confidence AS INT) >= 30") if fam == "modis"
                             else ("'snpp'", "type = 0 AND lower(confidence) IN ('n', 'h')"))
                con.execute(f"""
                  INSERT INTO cellfrp
                  SELECT sat, d, dn, cell, max(f) FROM (
                    SELECT {sat} AS sat, acq_time,
                      CAST(strptime(acq_date || ' ' || lpad(acq_time, 4, '0'), '%Y-%m-%d %H%M')
                           + to_seconds(CAST(round(longitude / 15.0 * 3600) AS BIGINT)) AS DATE) AS d,
                      daynight AS dn, h3_latlng_to_cell(latitude, longitude, 8) AS cell, sum(frp) AS f
                    FROM read_csv('{p}', header=true, types={{'acq_time':'VARCHAR','confidence':'VARCHAR',
                         'acq_date':'VARCHAR','satellite':'VARCHAR','daynight':'VARCHAR'}})
                    WHERE longitude BETWEEN {BBOX[0]} AND {BBOX[2]} AND latitude BETWEEN {BBOX[1]} AND {BBOX[3]} AND {keep}
                    GROUP BY ALL
                  ) GROUP BY ALL""")
    print(y, flush=True)
# a cell-day can be split across country files or two inserts: collapse, then keep matched days only
con.execute(f"""CREATE OR REPLACE TABLE cd AS
  WITH matched AS (SELECT d FROM read_parquet('{OUT / 'presence.parquet'}') GROUP BY d HAVING count(DISTINCT sat) = 2)
  SELECT sat, d, dn, cell, max(frp) AS frp FROM cellfrp JOIN matched USING (d) GROUP BY ALL""")
cases = ", ".join(f"count(*) FILTER (WHERE frp >= {f}) AS n{f}" for f in FLOORS)
m = con.execute(f"SELECT sat, year(d) AS y, month(d) AS m, dn, {cases}, sum(frp) AS frp FROM cd GROUP BY ALL").df()
q = con.execute("SELECT sat, dn, quantile_cont(frp, [0.1, 0.25, 0.5, 0.75, 0.9]) AS q FROM cd WHERE year(d) BETWEEN 2013 AND 2022 GROUP BY ALL ORDER BY ALL").fetchall()

w = m.pivot_table(index=["y", "m", "dn"], columns="sat", values=[f"n{f}" for f in FLOORS] + ["frp"], fill_value=0)
def slope(df, xcol):
    g = df[(df.a >= 30) & (df.v >= 30)]
    if g.y.nunique() < 8 or len(g) < 40: return None
    gy = {y: t for y, t in g.groupby("y")}; ys = np.array(sorted(gy))
    def f(sel):
        t = pd.concat([gy[y] for y in sel]); return np.polyfit(np.log(t[xcol]), np.log(t.v / t.a), 1)[0]
    bs = np.array([f(rng.choice(ys, len(ys))) for _ in range(1000)])
    return dict(slope=round(float(f(ys)), 3), ci95=[round(float(v), 3) for v in np.percentile(bs, [2.5, 97.5])], months=len(g))
res = {"frp_quantiles_MW": [dict(sat=s, dn=d, p10_p25_p50_p75_p90=[round(x, 1) for x in qq]) for s, d, qq in q], "floors": []}
for dn in ("D", "N"):
    for f in FLOORS:
        t = w.xs(dn, level="dn")[f"n{f}"].reset_index().rename(columns={"aqua": "a", "snpp": "v"}); t = t[t.y.isin(CAL)]
        yr = t.groupby("y")[["a", "v"]].sum()
        bs = [(lambda s: yr.v.loc[s].sum() / yr.a.loc[s].sum())(rng.choice(yr.index, len(yr))) for _ in range(2000)]
        res["floors"].append(dict(dn=dn, floor_MW=f, aqua=int(t.a.sum()), viirs=int(t.v.sum()),
            share_of_aqua_kept=round(float(t.a.sum() / w.xs(dn, level="dn")["n0"].reset_index().query("y in @CAL").aqua.sum()), 3),
            ratio=round(float(t.v.sum() / t.a.sum()), 3), ratio_ci95=[round(float(v), 3) for v in np.percentile(bs, [2.5, 97.5])],
            slope_vs_aqua=slope(t, "a"), slope_vs_viirs=slope(t, "v")))
    t = w.xs(dn, level="dn")["frp"].reset_index(); t = t[t.y.isin(CAL)]
    res[f"total_frp_ratio_{dn}"] = round(float(t.snpp.sum() / t.aqua.sum()), 3)
(pathlib.Path(__file__).parent / "frp_results.json").write_text(json.dumps(res, indent=1))
for r in res["frp_quantiles_MW"]: print(r)
print("total FRP ratio D/N", res["total_frp_ratio_D"], res["total_frp_ratio_N"])
for r in res["floors"]:
    sa, sv = r["slope_vs_aqua"], r["slope_vs_viirs"]
    print(r["dn"], f'{r["floor_MW"]:>4}', f'aqua {r["aqua"]:>7} kept {r["share_of_aqua_kept"]:.2f}', f'ratio {r["ratio"]:.2f} {r["ratio_ci95"]}',
          "slopeA", (sa["slope"], sa["ci95"], sa["months"]) if sa else None, "slopeV", (sv["slope"], sv["ci95"]) if sv else None)
