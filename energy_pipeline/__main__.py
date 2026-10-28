"""Command-line entry point.

    python -m energy_pipeline              # run the full pipeline
    python -m energy_pipeline --export-only  # rebuild the CSVs from the database
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import store
from .config import load_config
from .export import export_powerbi
from .pipeline import run


def main() -> int:
    parser = argparse.ArgumentParser(description="Weather-Aware Energy Intelligence pipeline")
    parser.add_argument("--config", type=Path, help="path to config.toml")
    parser.add_argument("--export-only", action="store_true", help="only regenerate the Power BI CSVs")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    cfg = load_config(args.config)

    if args.export_only:
        conn = store.connect(cfg.database)
        export_powerbi(conn, cfg)
        conn.close()
        return 0

    try:
        run(cfg)
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
