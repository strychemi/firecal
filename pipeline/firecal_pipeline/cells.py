"""bronze -> silver: burning cell-days and daily coverage.

silver/cell_day.parquet   sat, d, dn, cell8, continent, n_hot, frp   (filtered hotspots only)
silver/coverage.parquet   sat, continent, d, n_raw            (any detection in the continent, unfiltered)
silver/observed.parquet   sat, r3, d, dn                      (outage-check units with fire each satellite observed)
silver/passes.parquet     sat, continent, d, dn, fallback     (passes FIRMS holds; whole-area fallback passes)

Coverage picks the satellite for each published day and continent: one with no detection anywhere in the
continent (Argentina: the study box) that day has no data there (PREREGISTRATION.md, rule 7). Observed decides which units the fit may use
(PREREGISTRATION.md §7, 2026-11-15; see granules.py).
"""
from . import granules
from .config import Config, connect


def write_coverage(con, silver) -> None:
    """silver/coverage.parquet from the view b over bronze. `python -m firecal_pipeline coverage` rewrites only this
    file, for a silver/ built before coverage was split by continent."""
    con.execute(f"""COPY (SELECT sat, continent, local_date AS d, count(*)::INTEGER AS n_raw FROM b
                          GROUP BY ALL ORDER BY sat, continent, d)
                    TO '{silver}/coverage.parquet' (FORMAT parquet)""")


def coverage(cfg: Config) -> None:
    con = connect()
    con.execute(f"CREATE VIEW b AS SELECT sat, continent, local_date FROM read_parquet('{cfg.out}/bronze/*/*.parquet')")
    write_coverage(con, cfg.dir("silver"))


def run(cfg: Config) -> None:
    bronze = cfg.out / "bronze"
    silver = cfg.dir("silver")
    con = connect()
    con.execute(f"CREATE VIEW b AS SELECT * FROM read_parquet('{bronze}/*/*.parquet')")
    con.execute(f"""COPY (SELECT sat, local_date AS d, dn, cell8, continent, count(*)::INTEGER AS n_hot, sum(frp) AS frp
                          FROM b WHERE keep GROUP BY ALL ORDER BY cell8, d)
                    TO '{silver}/cell_day.parquet' (FORMAT parquet, COMPRESSION zstd)""")
    write_coverage(con, silver)
    for row in con.execute(f"""SELECT sat, count(*), min(d), max(d)
                               FROM read_parquet('{silver}/cell_day.parquet') GROUP BY sat ORDER BY sat""").fetchall():
        print("cell-days", *row, flush=True)
    granules.build(cfg, con, silver)
