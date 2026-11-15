"""firecal pipeline: python -m firecal_pipeline {download,ingest,cells,fit,publish,example,all}

"all" runs every step except download, which needs a FIRMS MAP_KEY (see download.py)."""
import argparse

from .config import Config


def main() -> None:
    ap = argparse.ArgumentParser(prog="firecal")
    ap.add_argument("step", choices=["download", "ingest", "cells", "fit", "publish", "example", "all"])
    ap.add_argument("--force", action="store_true", help="rebuild bronze files that already exist")
    args = ap.parse_args()
    cfg = Config.load()
    steps = ["ingest", "cells", "fit", "publish", "example"] if args.step == "all" else [args.step]
    for step in steps:
        if step == "download":
            from . import download
            download.run(cfg)
        elif step == "ingest":
            from . import ingest
            ingest.run(cfg, args.force)
        elif step == "cells":
            from . import cells
            cells.run(cfg)
        elif step == "fit":
            from . import fit
            fit.run(cfg)
        elif step == "publish":
            from . import publish
            publish.run(cfg)
        elif step == "example":
            from . import reference
            reference.write_examples(cfg)


if __name__ == "__main__":
    main()
