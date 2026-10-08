"""Phase 1: angular segment analysis for one district (pilot) or all of Berlin.

Usage: python scripts/run_segments.py --district Friedrichshain-Kreuzberg
       python scripts/run_segments.py --district Berlin      # whole city, reported per district

With --district Berlin the city is analysed as one network (city + 2 km
buffer) and each segment is assigned to the district containing its midpoint;
ranks and percentiles are then computed within each district, so they are
comparable with a single-district run. Output names use "berlin".

Writes
  output/segments_<district>.gpkg                 all measures per segment (git-ignored, large)
  output/segments_<district>_summary.csv          distribution of each measure inside the district
  output/segments_<district>_top10.csv            top 10 named streets by NACH / choice / NAIN per radius
  output/segments_<district>_main_streets.csv     percentile rank of known main streets
  output/maps/segments_<district>_nach_<r>.png    NACH maps at 800 m and 2000 m
  data/derived/segments_<district>_primal.pkl     cleaned primal graph (cache)
"""
import argparse
import os
import json
import pickle
import re
import time

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from cityseer.tools import graphs  # noqa: E402
from pyrosm import OSM  # noqa: E402

import _bootstrap  # noqa: F401, E402

from berlin_access import segments as sg  # noqa: E402
from berlin_access.config import load_config  # noqa: E402
from berlin_access.reference_streets import ADDED_AFTER_RESULTS, REFERENCE_STREETS, SEEN  # noqa: E402
from berlin_access.pipeline import load_lor  # noqa: E402

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
CONTEXT = "#d9d8d3"
RAMP = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"]  # validated ordinal ramp, see make_maps.py
WIDTHS = [0.35, 0.55, 0.8, 1.2, 1.8]



def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def nach_map(seg, ctx, outline, r, district, path, figsize=(12, 8.5), width_scale=1.0):
    """Segments in quintile classes of NACH, darker and thicker = higher. Context
    (buffer) segments thin gray. Quintiles because NACH is a relative measure."""
    col = f"nach_{r}"
    q = seg[col].quantile([0.2, 0.4, 0.6, 0.8]).to_numpy()
    cls = np.searchsorted(q, seg[col].to_numpy(), side="right")
    fig, ax = plt.subplots(figsize=figsize, dpi=150, facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ctx.plot(ax=ax, color=CONTEXT, linewidth=0.3)
    for k in range(5):
        part = seg[cls == k]
        if len(part):
            part.plot(ax=ax, color=RAMP[k], linewidth=WIDTHS[k] * width_scale, capstyle="round")
    outline.boundary.plot(ax=ax, color=TEXT_2, linewidth=0.8, linestyle=(0, (4, 2)))
    xmin, ymin, xmax, ymax = outline.total_bounds
    pad = 600
    ax.set_xlim(xmin - pad, xmax + pad)
    ax.set_ylim(ymin - pad, ymax + pad)
    ax.set_axis_off()
    ax.set_title(f"Normalised angular choice (NACH), radius {r} m: {district}", loc="left", fontsize=13, color=TEXT)
    if district == "Berlin":
        ax.text(0.0, -0.01, "Quintiles over all Berlin segments.", transform=ax.transAxes, fontsize=8, color=TEXT_2)
    labels = ["lowest 20%", "20-40%", "40-60%", "60-80%", "highest 20%"]
    handles = [plt.Line2D([], [], color=c, linewidth=w * 2.2, label=lbl) for c, w, lbl in zip(RAMP, WIDTHS, labels)]
    handles.append(plt.Line2D([], [], color=CONTEXT, linewidth=1, label="non-residential or buffer\n(in network, not ranked)"))
    ax.legend(handles=handles, loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=9,
              labelcolor=TEXT_2, title="Segments by NACH quintile", title_fontsize=9, alignment="left")
    fig.text(0.01, 0.01, "Angular segment analysis with cityseer on the cleaned OSM street network (2 km buffer). "
             "Coloured: residential streets (homes within 50 m). Data: OpenStreetMap (ODbL), "
             "Einwohnerregister 31.12.2025.", fontsize=7, color=TEXT_2)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    ap.add_argument("--district", default="Friedrichshain-Kreuzberg")
    ap.add_argument("--buffer-m", type=int, default=2000)
    args = ap.parse_args()
    cfg = load_config(args.config)
    crs = cfg["crs"]
    epsg = int(crs.split(":")[1])
    out, der = cfg.path("output"), cfg.path("derived")
    (out / "maps").mkdir(parents=True, exist_ok=True)
    name = slug(args.district)
    if args.buffer_m < max(sg.DISTANCES):
        raise SystemExit("buffer must be at least the largest radius to avoid edge effects")

    lor = load_lor(cfg.path("lor"), crs)
    districts = lor.dissolve("district").reset_index()[["district", "geometry"]]
    whole_city = args.district == "Berlin"
    district = districts if whole_city else districts[districts["district"] == args.district]
    if district.empty:
        raise SystemExit(f"unknown district {args.district}; choose Berlin or one of {sorted(districts['district'])}")
    study = district.union_all()
    area = study.buffer(args.buffer_m)
    area_wgs = gpd.GeoSeries([area], crs=crs).to_crs(4326).iloc[0]
    meta = {"study_area": args.district, "buffer_m": args.buffer_m, "distances": sg.DISTANCES}

    # The cleaned network depends on the hash seed (see _bootstrap.py), so it is part of the cache name.
    seed = os.environ.get("PYTHONHASHSEED", "random")
    meta["python_hash_seed"] = seed
    cache = der / f"segments_{name}_primal_v{sg.WAY_SELECTION_VERSION}_seed{seed}.pkl"
    if cache.exists():
        log(f"using cached primal graph {cache.name}")
        G, meta["network"] = pickle.loads(cache.read_bytes())
    else:
        log("reading OSM (district + buffer)")
        osm = OSM(str(cfg.path("pbf")), bounding_box=area_wgs, keep_metadata=False)
        nodes, edges, wstats = sg.read_ways(osm, crs)
        G = sg.build_primal(nodes, edges, crs)
        wstats["primal_edges_before_cleaning"] = G.number_of_edges()
        log(f"primal graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges; cleaning")
        G = sg.clean(G, sg.local_areas(osm), area_wgs, epsg)
        wstats["primal_edges_after_cleaning"] = G.number_of_edges()
        meta["network"] = wstats
        cache.write_bytes(pickle.dumps((G, wstats)))
    log(f"network: {meta['network']}")

    G = sg.mark_live(G, study)
    D = graphs.nx_to_dual(G)
    log(f"dual graph: {D.number_of_nodes()} segments; computing centralities")
    n = sg.centralities(D)
    n["street"] = sg.segment_names(G, n)
    n = gpd.GeoDataFrame(n.drop(columns=["geom", "primal_edge"], errors="ignore"),
                         geometry=gpd.GeoSeries(n["primal_edge"].to_numpy(), crs=crs, index=n.index))
    n["length_m"] = n.geometry.length
    n.to_file(out / f"segments_{name}.gpkg", layer="segments", driver="GPKG")

    # Residential streets: segments with a building with residents (Phase 0
    # allocation) within the frontage buffer. All streets stay in the network
    # for routing; only residential ones are ranked, summarised and coloured.
    bld_file = der / "building_walk_dist.parquet"
    if not bld_file.exists():
        raise SystemExit("run scripts/run_accessibility.py first: residential streets need its building residents")
    buf = cfg.raw.get("segment_residential_buffer_m", 50)
    front = sg.residential_frontage(n, gpd.read_parquet(bld_file), buf)
    n = n.join(front)
    meta["residential_buffer_m"] = buf
    meta["live_segments"] = int(n["live"].sum())
    meta["live_residential_segments"] = int((n["live"] & n["residential"]).sum())
    # District of each live segment: the one containing its midpoint (nearest
    # district for the few whose midpoint lies just outside the city).
    live = n[n["live"]]
    mid = gpd.GeoDataFrame(geometry=live.geometry.interpolate(0.5, normalized=True), crs=crs)
    n.loc[live.index, "district"] = gpd.sjoin_nearest(mid, districts, how="left")["district"].groupby(level=0).first()
    n.to_file(out / f"segments_{name}.gpkg", layer="segments", driver="GPKG")

    seg = n[n["live"] & n["residential"]].copy()
    ctx = n[~(n["live"] & n["residential"])]
    meta["segments_reported"] = int(len(seg))
    meta["segments_context"] = int(len(ctx))
    meta["segments_reported_by_district"] = seg["district"].value_counts().sort_index().to_dict()
    meta["live_segments_by_district"] = n.loc[live.index, "district"].value_counts().sort_index().to_dict()

    measures = [c for c in seg.columns if c.startswith(("cc_", "nain_", "nach_"))]
    seg[measures].describe(percentiles=[0.1, 0.5, 0.9]).T.round(4).to_csv(out / f"segments_{name}_summary.csv")

    top_rows, main_rows, dist_rows = [], [], []
    for dname, g in seg.groupby("district"):
        # Top 10 distinct named streets per measure and radius (a street's value =
        # its highest segment), for the sanity check against known main streets.
        named = g[g["street"].notna()]
        for r in sg.DISTANCES:
            for measure, col in (("NACH", f"nach_{r}"), ("angular choice", f"cc_betweenness_{r}_ang"), ("NAIN", f"nain_{r}")):
                top = named.groupby("street")[col].max().sort_values(ascending=False).head(10)
                for rank, (street, value) in enumerate(top.items(), start=1):
                    top_rows.append({"district": dname, "radius_m": r, "measure": measure, "rank": rank,
                                     "street": street, "value": round(value, 4)})
        # Where known main streets rank: median percentile of their segments in the district.
        for street in REFERENCE_STREETS.get(dname, []):
            x = g["street"].fillna("").str.contains(street, regex=False)
            provenance = ("seen in top three" if (dname, street) in SEEN
                          else "added after results" if (dname, street) in ADDED_AFTER_RESULTS else "fixed in advance")
            row = {"district": dname, "street": street, "provenance": provenance, "segments": int(x.sum()),
                   "length_m": round(float(g.loc[x, "length_m"].sum()), 0)}
            for r in (800, 2000):
                for label, col in (("choice", f"cc_betweenness_{r}_ang"), ("choice_lw", f"cc_betweenness_{r}_ang_lw"),
                                   ("nach", f"nach_{r}"), ("nain", f"nain_{r}")):
                    row[f"{label}_{r}_pct"] = round(float(g[col].rank(pct=True)[x].median()), 2) if x.any() else None
            main_rows.append(row)
        n_live = meta["live_segments_by_district"].get(dname, 0)
        row = {"district": dname, "live_segments": n_live, "segments": len(g),
               "residential_share": round(len(g) / n_live, 3) if n_live else None,
               "network_km": round(g["length_m"].sum() / 1000, 1),
               "median_segment_m": round(g["length_m"].median(), 1)}
        for r in (800, 2000):
            row[f"median_nain_{r}"] = round(g[f"nain_{r}"].median(), 3)
            row[f"median_nach_{r}"] = round(g[f"nach_{r}"].median(), 3)
        dist_rows.append(row)
    pd.DataFrame(top_rows).to_csv(out / f"segments_{name}_top10.csv", index=False)
    if main_rows:
        pd.DataFrame(main_rows).to_csv(out / f"segments_{name}_main_streets.csv", index=False)
    pd.DataFrame(dist_rows).to_csv(out / f"segments_{name}_by_district.csv", index=False)

    title = "Berlin" if whole_city else args.district
    size, ws = ((14, 10.5), 0.45) if whole_city else ((12, 8.5), 1.0)
    for r in (800, 2000):
        nach_map(seg, ctx, district, r, title, out / "maps" / f"segments_{name}_nach_{r}.png", size, ws)

    (out / f"segments_{name}_metadata.json").write_text(json.dumps(meta, indent=2, default=str))
    log("done")


if __name__ == "__main__":
    main()
