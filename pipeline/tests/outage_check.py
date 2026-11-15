"""The pre-fit check of the outage-check unit on Argentina (PREREGISTRATION.md §7, 2026-11-15, rule 7 part 6).

Reads silver/ after `cells`; uses no fit result.
  1. Known outages: units each satellite observed per day around S-NPP 2022-07-27..08-10, Aqua 2022-04-01..16
     and the 2024 S-NPP days the whole-box rule marked as outages.
  2. Units that change fair status: units (res-3 cell, local date, pass) where either satellite has a burning
     cell-day, fair under the old rule (both satellites have a detection somewhere in the box that day) and/or
     the new one (both observed the unit), with the cell-days they hold.

    uv run python tests/outage_check.py
"""
import datetime as dt

from firecal_pipeline.config import Config, connect
from firecal_pipeline.granules import fit_years

cfg = Config.load()
silver = cfg.out / "silver"
con = connect()
ys = fit_years(cfg)
con.execute(f"CREATE VIEW obs AS SELECT * FROM read_parquet('{silver}/observed.parquet')")
con.execute(f"CREATE VIEW cov AS SELECT * FROM read_parquet('{silver}/coverage.parquet') WHERE n_raw > 0")
con.execute(f"""CREATE VIEW cd AS SELECT *, printf('%x', h3_cell_to_parent(cell8, 3)) AS u3
                FROM read_parquet('{silver}/cell_day.parquet') WHERE year(d) BETWEEN {ys[0]} AND {ys[-1]}""")


def per_day(sat: str, a: str, z: str) -> None:
    rows = con.execute(f"""
        WITH days AS (SELECT CAST(t AS DATE) AS d FROM generate_series(DATE '{a}', DATE '{z}', INTERVAL 1 DAY) g(t))
        SELECT days.d, count(*) FILTER (o.dn = 'D' AND o.src = 'granule') AS day_units,
                  count(*) FILTER (o.dn = 'N' AND o.src = 'granule') AS night_units,
                  count(*) FILTER (o.src = 'fallback') AS fallback,
                  (SELECT n_raw FROM cov c WHERE c.sat = '{sat}' AND c.d = days.d) AS detections
        FROM days LEFT JOIN obs o ON o.d = days.d AND o.sat = '{sat}' GROUP BY days.d ORDER BY days.d""").fetchall()
    print(f"\n{sat} {a} .. {z}: observed units (day, night), fallback passes, unfiltered detections in the box")
    for d, du, nu, fb, n in rows:
        print(f"  {d}  {du:4d} {nu:4d}  {fb}  {n or 0}")


print("1. Known outages")
per_day("snpp", "2022-07-24", "2022-08-13")
per_day("aqua", "2022-03-29", "2022-04-19")
gaps = [r[0] for r in con.execute("""
    SELECT CAST(t AS DATE) d FROM generate_series(DATE '2024-01-01', DATE '2024-12-31', INTERVAL 1 DAY) g(t)
    WHERE CAST(t AS DATE) NOT IN (SELECT d FROM cov WHERE sat = 'snpp') ORDER BY 1""").fetchall()]
print("\n2024 S-NPP days with no detection in the box (whole-box rule outages):", [str(d) for d in gaps])
for d in gaps:
    per_day("snpp", str(d - dt.timedelta(days=1)), str(d + dt.timedelta(days=1)))

print("\n2. Units changing fair status (units with a burning cell-day of either satellite)")
for model in ("aqua", "terra", "noaa20"):
    r = con.execute(f"""
        WITH units AS (SELECT u3, d, dn, count(*) FILTER (sat = '{model}') AS m, count(*) FILTER (sat = 'snpp') AS v
                       FROM cd WHERE sat IN ('{model}', 'snpp') GROUP BY ALL),
             old AS (SELECT d FROM cov WHERE sat IN ('{model}', 'snpp') GROUP BY d HAVING count(DISTINCT sat) = 2),
             seen AS (SELECT u.u3, u.d, u.dn, o.sat FROM units u JOIN obs o ON o.r3 = u.u3 AND o.d = u.d AND o.dn = u.dn
                      WHERE o.sat IN ('{model}', 'snpp')
                      UNION ALL
                      SELECT u.u3, u.d, u.dn, o.sat FROM units u JOIN obs o ON o.r3 IS NULL AND o.d = u.d AND o.dn = u.dn
                      WHERE o.sat IN ('{model}', 'snpp')),
             new AS (SELECT u3, d, dn FROM seen GROUP BY ALL HAVING count(DISTINCT sat) = 2),
             t AS (SELECT u.*, u.d IN (SELECT d FROM old) AS was, (u.u3, u.d, u.dn) IN (SELECT (u3, d, dn) FROM new) AS now
                   FROM units u)
        SELECT was, now, count(*), sum(m), sum(v) FROM t GROUP BY ALL ORDER BY was DESC, now DESC""").fetchall()
    tot = [sum(x[i] for x in r) for i in (2, 3, 4)]
    print(f"\n{model} vs snpp: {tot[0]:,} units, {tot[1]:,} {model} and {tot[2]:,} snpp cell-days")
    for was, now, n, m, v in r:
        lab = {(True, True): "fair before and now", (True, False): "fair before, not now",
               (False, True): "not fair before, fair now", (False, False): "fair neither"}[(was, now)]
        print(f"  {lab:28s} {n:9,} units ({100 * n / tot[0]:5.2f} %)  {model} {m:9,} ({100 * m / max(tot[1], 1):5.2f} %)"
              f"  snpp {v:10,} ({100 * v / tot[2]:5.2f} %)")
