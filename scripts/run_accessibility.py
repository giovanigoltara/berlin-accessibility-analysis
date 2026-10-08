"""Run the walk-to-transit pipeline and write output/*.csv.

Usage: python scripts/run_accessibility.py [--config config.yaml]
"""
import argparse

import _bootstrap  # noqa: F401

from berlin_access.config import load_config
from berlin_access.pipeline import run

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    run(load_config(ap.parse_args().config))
