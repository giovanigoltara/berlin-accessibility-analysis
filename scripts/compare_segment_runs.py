"""Check a single-district segment run against the citywide run.

If the 2 km buffer is enough to avoid edge effects, a segment should get the
same values whether it was computed in the district run or the citywide run.
Segments are matched by midpoint (within 1 m) and length (within 1 m), since
the two runs clean slightly different networks. Writes
output/segments_<district>_vs_berlin.csv: matched share and Spearman rank
correlation per measure.

With --run-a, --run-b and --out any two runs can be compared, e.g. two
citywide runs made with different hash seeds (docs/validation.md §8); only
segments marked residential in both are then compared.
"""
import argparse

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.stats import spearmanr

import _bootstrap  # noqa: F401

from berlin_access.config import load_config

MEASURES = ["cc_harmonic_{r}_ang", "cc_betweenness_{r}_ang", "nain_{r}", "nach_{r}", "cc_harmonic_{r}", "cc_betweenness_{r}"]

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--district", default="Friedrichshain-Kreuzberg")
    ap.add_argument("--run-a", default=None, help="segment GeoPackage (default: output/segments_<district>.gpkg)")
    ap.add_argument("--run-b", default=None, help="segment GeoPackage (default: output/segments_berlin.gpkg)")
    ap.add_argument("--out", default=None, help="output CSV (default: output/segments_<district>_vs_berlin.csv)")
    args = ap.parse_args()
    cfg = load_config()
    out = cfg.path("output")
    name = args.district.lower()
    a = gpd.read_file(args.run_a or out / f"segments_{name}.gpkg")
    b = gpd.read_file(args.run_b or out / "segments_berlin.gpkg")
    a = a[a["live"]] if args.district == "Berlin" else a[a["live"] & (a["district"] == args.district)]
    b = b[b["live"]]
    if args.run_a and args.run_b:
        a, b = a[a["residential"]], b[b["residential"]]
    ma = a.geometry.interpolate(0.5, normalized=True)
    mb = b.geometry.interpolate(0.5, normalized=True)
    d, j = cKDTree(np.c_[mb.x, mb.y]).query(np.c_[ma.x, ma.y])
    ok = (d < 1.0) & (np.abs(a["length_m"].to_numpy() - b["length_m"].to_numpy()[j]) < 1.0)
    rows = []
    for r in (400, 800, 1200, 2000):
        for m in MEASURES:
            col = m.format(r=r)
            x, y = a[col].to_numpy()[ok], b[col].to_numpy()[j[ok]]
            rows.append({"radius_m": r, "measure": col, "matched_segments": int(ok.sum()),
                         "share_matched": round(ok.mean(), 3), "spearman": round(spearmanr(x, y).statistic, 4),
                         "median_abs_rel_diff": round(float(np.median(np.abs(x - y) / np.maximum(np.abs(y), 1e-9))), 4)})
    res = pd.DataFrame(rows)
    res.to_csv(args.out or out / f"segments_{name}_vs_berlin.csv", index=False)
    print(res.to_string(index=False))
