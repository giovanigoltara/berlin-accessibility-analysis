"""Compare Place Syntax Tool results with the Python cross-check.

After running PST in QGIS (docs/pst_howto.md), save the origins layer with its
new PST columns, then map each PST column to the matching Python column:

  python scripts/compare_pst_results.py \\
      --pst output/pst/pst_results_friedrichshain-kreuzberg.gpkg --layer origins \\
      --map ARw800su=reach_su_800 --map ARw400anyf=reach_anyf_400 --map ADwsu=dist_su

PST column names depend on the options chosen (analysis code AR/AD, distance
type and radius such as w800, then the attraction name), so they are passed
explicitly rather than guessed. Rows are matched on osm_id.

Writes output/pst/pst_vs_python_<district>.csv with, per mapped pair: rows
matched, exact agreement share (reach), median absolute difference, Spearman.
"""
import argparse
import re

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import _bootstrap  # noqa: F401

from berlin_access.config import load_config

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pst", required=True, help="GeoPackage or other file with PST results on the origins")
    ap.add_argument("--layer", default="origins")
    ap.add_argument("--district", default="Friedrichshain-Kreuzberg")
    ap.add_argument("--map", action="append", required=True, help="PST_COLUMN=python_column")
    args = ap.parse_args()
    cfg = load_config()
    name = re.sub(r"[^a-z0-9]+", "-", args.district.lower()).strip("-")
    py = pd.read_csv(cfg.path("output") / "pst" / f"python_reach_{name}.csv")
    ps = gpd.read_file(args.pst, layer=args.layer)
    m = ps.drop(columns="geometry").merge(py, on="osm_id", how="inner", suffixes=("_pst", ""))
    rows = []
    for pair in args.map:
        pcol, ycol = pair.split("=", 1)
        x = pd.to_numeric(m[pcol], errors="coerce").to_numpy(float)
        y = m[ycol].to_numpy(float)
        ok = np.isfinite(x) & np.isfinite(y)
        rows.append({
            "pst_column": pcol, "python_column": ycol, "rows_matched": int(ok.sum()),
            "share_equal": round(float(np.mean(np.isclose(x[ok], y[ok], atol=0.5))), 3),
            "median_abs_diff": round(float(np.median(np.abs(x[ok] - y[ok]))), 2),
            "spearman": round(float(spearmanr(x[ok], y[ok]).statistic), 3) if ok.sum() > 2 else None,
        })
    res = pd.DataFrame(rows)
    res.to_csv(cfg.path("output") / "pst" / f"pst_vs_python_{name}.csv", index=False)
    print(res.to_string(index=False))
