"""firecal pipeline: python -m firecal_pipeline {download,granules,ingest,cells,coverage,fit,report,tilt,publish,prune,all}

"all" runs every step except download, which needs a FIRMS MAP_KEY (see download.py), granules, which
downloads NASA granule records (see granules.py), and prune,
which deletes old published versions (scripts/refresh.sh runs it). "coverage" rewrites only
silver/coverage.parquet (part of cells), for a silver/ written before coverage was split by continent."""
import argparse

from .config import Config


def main() -> None:
    ap = argparse.ArgumentParser(prog="firecal")
    ap.add_argument("step", choices=["download", "granules", "ingest", "cells", "coverage", "fit", "report", "tilt", "publish", "prune", "all"])
    ap.add_argument("--force", action="store_true", help="rebuild bronze files that already exist")
    args = ap.parse_args()
    cfg = Config.load()
    steps = ["ingest", "cells", "fit", "publish"] if args.step == "all" else [args.step]
    for step in steps:
        if step == "download":
            from . import download
            download.run(cfg)
        elif step == "granules":
            from . import granules
            granules.download(cfg)
        elif step == "ingest":
            from . import ingest
            ingest.run(cfg, args.force)
        elif step == "cells":
            from . import cells
            cells.run(cfg)
        elif step == "coverage":
            from . import cells
            cells.coverage(cfg)
        elif step == "fit":
            from . import fit
            fit.run(cfg)
        elif step == "report":
            from . import report
            report.run(cfg)
        elif step == "tilt":
            from . import tilt
            tilt.run(cfg)
        elif step == "publish":
            from . import publish
            publish.run(cfg)
        elif step == "prune":
            from . import publish
            publish.prune(cfg)


if __name__ == "__main__":
    main()
