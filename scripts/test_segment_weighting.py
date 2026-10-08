"""Does segment-length weighting change angular choice in a district?

Crops the cached citywide segment map (scripts/run_segments.py --district
Berlin) to the district + 2 km, computes angular choice and integration
unweighted and weighted by segment length (cityseer `segment_weighted`:
choice counts each route by origin length x destination length), and
compares the two on residential streets inside the district.

Writes output/segments_<district>_weighting_test.csv (reference streets) and
output/segments_<district>_weighting_top10.csv.

Usage: python scripts/test_segment_weighting.py --district Mitte
"""
import argparse
import pickle
import re

import geopandas as gpd
import numpy as np
import pandas as pd
from cityseer.metrics import networks
from cityseer.tools import graphs
from cityseer.tools import io as cs_io
from scipy.stats import spearmanr

import _bootstrap  # noqa: F401

from berlin_access import segments as sg
from berlin_access.config import load_config
from berlin_access.pipeline import load_lor

# Fixed before looking at any weighted or unweighted Mitte results: main
# streets of the historic centre, Wedding and Moabit.
REFERENCE_STREETS = {
    "Mitte": [
        "friedrichstraße", "unter den linden", "leipziger straße", "torstraße", "karl-liebknecht-straße",
        "invalidenstraße", "brunnenstraße", "müllerstraße", "turmstraße", "alt-moabit",
        "rosenthaler straße", "badstraße",
    ],
}
RADII = [800, 2000]


def run(D, weighted):
    nodes, _e, ns = cs_io.network_structure_from_nx(D)
    nodes = networks.centrality_simplest(
        ns, nodes, distances=RADII,
        closeness={"density": "1", "harmonic": "1 / (1 + c / 90)", "td": "c / 90"},
        betweenness={"betweenness": "1"}, postprocess={}, segment_weighted=weighted,
    )
    return nodes


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--district", default="Mitte")
    ap.add_argument("--buffer-m", type=int, default=2000)
    args = ap.parse_args()
    cfg = load_config()
    crs, out, der = cfg["crs"], cfg.path("output"), cfg.path("derived")
    name = re.sub(r"[^a-z0-9]+", "-", args.district.lower()).strip("-")

    lor = load_lor(cfg.path("lor"), crs)
    study = lor[lor["district"] == args.district].union_all()
    area = study.buffer(args.buffer_m)
    G, _ = pickle.loads((der / f"segments_berlin_primal_v{sg.WAY_SELECTION_VERSION}.pkl").read_bytes())
    from shapely import contains_xy

    keys = list(G.nodes)
    inside = contains_xy(area, np.array([G.nodes[k]["x"] for k in keys]), np.array([G.nodes[k]["y"] for k in keys]))
    G = G.subgraph([k for k, i in zip(keys, inside) if i]).copy()
    G = sg.mark_live(G, study)
    D = graphs.nx_to_dual(G)

    a, b = run(D, False), run(D, True)
    a["street"] = sg.segment_names(G, a)
    geom = gpd.GeoSeries(a["primal_edge"].to_numpy(), crs=crs, index=a.index)
    segs = gpd.GeoDataFrame({"street": a["street"], "live": a["live"]}, geometry=geom, crs=crs)
    segs["length_m"] = segs.length
    segs = segs.join(sg.residential_frontage(segs, gpd.read_parquet(der / "building_walk_dist.parquet"),
                                             cfg.raw.get("segment_residential_buffer_m", 50)))
    for r in RADII:
        for m, col in (("choice", f"cc_betweenness_{r}_ang"), ("harmonic", f"cc_harmonic_{r}_ang")):
            segs[f"{m}_{r}"] = a[col]
            segs[f"{m}_{r}_lw"] = b[col]
    live = segs[segs["live"]]
    rep = live[live["residential"]]

    rows = []
    for street in REFERENCE_STREETS.get(args.district, []):
        x_all = live["street"].fillna("").str.contains(street, regex=False)
        x = rep["street"].fillna("").str.contains(street, regex=False)
        row = {"street": street, "segments_live": int(x_all.sum()), "segments_residential": int(x.sum()),
               "median_segment_m": round(float(live.loc[x_all, "length_m"].median()), 1) if x_all.any() else None}
        for r in RADII:
            for col in (f"choice_{r}", f"choice_{r}_lw"):
                row[f"{col}_pct"] = round(float(rep[col].rank(pct=True)[x].median()), 2) if x.any() else None
        rows.append(row)
    pd.DataFrame(rows).to_csv(out / f"segments_{name}_weighting_test.csv", index=False)

    top_rows = []
    named = rep[rep["street"].notna()]
    for r in RADII:
        for col, label in ((f"choice_{r}", "unweighted"), (f"choice_{r}_lw", "length-weighted")):
            top = named.groupby("street")[col].max().sort_values(ascending=False).head(10)
            for rank, (street, _v) in enumerate(top.items(), start=1):
                seg_len = named.loc[named["street"] == street, "length_m"].median()
                top_rows.append({"radius_m": r, "choice": label, "rank": rank, "street": street,
                                 "median_segment_m": round(float(seg_len), 1)})
    pd.DataFrame(top_rows).to_csv(out / f"segments_{name}_weighting_top10.csv", index=False)

    summary = {"segments_live": int(len(live)), "segments_residential": int(len(rep)),
               "median_segment_m_residential": round(float(rep["length_m"].median()), 1)}
    for r in RADII:
        summary[f"spearman_choice_{r}"] = round(spearmanr(rep[f"choice_{r}"], rep[f"choice_{r}_lw"]).statistic, 3)
        summary[f"spearman_harmonic_{r}"] = round(spearmanr(rep[f"harmonic_{r}"], rep[f"harmonic_{r}_lw"]).statistic, 3)
    pd.Series(summary).to_csv(out / f"segments_{name}_weighting_summary.csv", header=["value"])
    print(pd.Series(summary).to_string())
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
