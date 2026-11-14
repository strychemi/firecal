"""bronze -> silver: burning cell-days and daily coverage.

silver/cell_day.parquet   sat, d, dn, cell8, n_hot, frp       (filtered hotspots only)
silver/coverage.parquet   sat, d, n_raw                       (any detection in the box, unfiltered)

A satellite with no detection anywhere in the study box on a day is treated as having no data
that day (PREREGISTRATION.md, rule 7). Coverage is what that rule reads.
"""
from .config import Config, connect


def run(cfg: Config) -> None:
    bronze = cfg.out / "bronze"
    silver = cfg.dir("silver")
    con = connect()
    con.execute(f"CREATE VIEW b AS SELECT * FROM read_parquet('{bronze}/*/*.parquet')")
    con.execute(f"""COPY (SELECT sat, local_date AS d, dn, cell8, count(*)::INTEGER AS n_hot, sum(frp) AS frp
                          FROM b WHERE keep GROUP BY ALL ORDER BY cell8, d)
                    TO '{silver}/cell_day.parquet' (FORMAT parquet, COMPRESSION zstd)""")
    con.execute(f"""COPY (SELECT sat, local_date AS d, count(*)::INTEGER AS n_raw FROM b GROUP BY ALL ORDER BY sat, d)
                    TO '{silver}/coverage.parquet' (FORMAT parquet)""")
    for row in con.execute(f"""SELECT sat, count(*), min(d), max(d)
                               FROM read_parquet('{silver}/cell_day.parquet') GROUP BY sat ORDER BY sat""").fetchall():
        print("cell-days", *row, flush=True)
