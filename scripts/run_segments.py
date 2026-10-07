"""Phase 1: angular segment analysis for one district (pilot) or all.

Usage: python scripts/run_segments.py --district Friedrichshain-Kreuzberg

Writes
  output/segments_<district>.gpkg                 all measures per segment (git-ignored, large)
  output/segments_<district>_summary.csv          distribution of each measure inside the district
  output/segments_<district>_top10.csv            top 10 named streets by NACH / choice / NAIN per radius
  output/segments_<district>_main_streets.csv     percentile rank of known main streets
  output/maps/segments_<district>_nach_<r>.png    NACH maps at 800 m and 2000 m
  data/derived/segments_<district>_primal.pkl     cleaned primal graph (cache)
"""
import argparse
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
from berlin_access.pipeline import load_lor  # noqa: E402

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
CONTEXT = "#d9d8d3"
RAMP = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"]  # validated ordinal ramp, see make_maps.py
WIDTHS = [0.35, 0.55, 0.8, 1.2, 1.8]

# Streets expected to be among the most central, for the sanity check
# (lower-case OSM names): the main arterials and shopping streets of each pilot
# district. Frankfurter Allee, Kottbusser Damm and Oranienstraße come from the
# project brief; Karl-Marx-Allee, Warschauer, Skalitzer, Gneisenau-, Yorckstraße
# and Mehringdamm were named before the first run; Petersburger, Boxhagener and
# Revaler Straße were added after it.
MAIN_STREETS = {
    "Friedrichshain-Kreuzberg": [
        "frankfurter allee", "karl-marx-allee", "warschauer straße", "skalitzer straße", "kottbusser damm",
        "oranienstraße", "gneisenaustraße", "yorckstraße", "mehringdamm", "petersburger straße",
        "boxhagener straße", "revaler straße",
    ],
}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def nach_map(seg, ctx, outline, r, district, path):
    """Segments in quintile classes of NACH, darker and thicker = higher. Context
    (buffer) segments thin gray. Quintiles because NACH is a relative measure."""
    col = f"nach_{r}"
    q = seg[col].quantile([0.2, 0.4, 0.6, 0.8]).to_numpy()
    cls = np.searchsorted(q, seg[col].to_numpy(), side="right")
    fig, ax = plt.subplots(figsize=(12, 8.5), dpi=150, facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ctx.plot(ax=ax, color=CONTEXT, linewidth=0.3)
    for k in range(5):
        part = seg[cls == k]
        if len(part):
            part.plot(ax=ax, color=RAMP[k], linewidth=WIDTHS[k], capstyle="round")
    outline.boundary.plot(ax=ax, color=TEXT_2, linewidth=0.8, linestyle=(0, (4, 2)))
    xmin, ymin, xmax, ymax = outline.total_bounds
    pad = 600
    ax.set_xlim(xmin - pad, xmax + pad)
    ax.set_ylim(ymin - pad, ymax + pad)
    ax.set_axis_off()
    ax.set_title(f"Normalised angular choice (NACH), radius {r} m: {district}", loc="left", fontsize=13, color=TEXT)
    labels = ["lowest 20%", "20-40%", "40-60%", "60-80%", "highest 20%"]
    handles = [plt.Line2D([], [], color=c, linewidth=w * 2.2, label=lbl) for c, w, lbl in zip(RAMP, WIDTHS, labels)]
    handles.append(plt.Line2D([], [], color=CONTEXT, linewidth=1, label="buffer (context only)"))
    ax.legend(handles=handles, loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=9,
              labelcolor=TEXT_2, title="Segments by NACH quintile", title_fontsize=9, alignment="left")
    fig.text(0.01, 0.01, "Angular segment analysis with cityseer on the cleaned OSM pedestrian network; "
             "2 km network buffer. Data: OpenStreetMap (ODbL).", fontsize=7, color=TEXT_2)
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
    district = lor[lor["district"] == args.district]
    if district.empty:
        raise SystemExit(f"unknown district {args.district}; choose from {sorted(lor['district'].unique())}")
    study = district.union_all()
    area = study.buffer(args.buffer_m)
    area_wgs = gpd.GeoSeries([area], crs=crs).to_crs(4326).iloc[0]
    meta = {"district": args.district, "buffer_m": args.buffer_m, "distances": sg.DISTANCES}

    cache = der / f"segments_{name}_primal.pkl"
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

    seg = n[n["live"]].copy()
    ctx = n[~n["live"]]
    meta["segments_in_district"] = int(len(seg))
    meta["segments_in_buffer"] = int(len(ctx))

    measures = [c for c in seg.columns if c.startswith(("cc_", "nain_", "nach_"))]
    seg[measures].describe(percentiles=[0.1, 0.5, 0.9]).T.round(4).to_csv(out / f"segments_{name}_summary.csv")

    # Top 10 distinct named streets per measure and radius (a street's value =
    # its highest segment), for the sanity check against known main streets.
    named = seg[seg["street"].notna()]
    rows = []
    for r in sg.DISTANCES:
        for measure, col in (("NACH", f"nach_{r}"), ("angular choice", f"cc_betweenness_{r}_ang"), ("NAIN", f"nain_{r}")):
            top = named.groupby("street")[col].max().sort_values(ascending=False).head(10)
            for rank, (street, value) in enumerate(top.items(), start=1):
                rows.append({"radius_m": r, "measure": measure, "rank": rank, "street": street, "value": round(value, 4)})
    pd.DataFrame(rows).to_csv(out / f"segments_{name}_top10.csv", index=False)

    # Where known main streets rank: median percentile of their segments in the district.
    rows = []
    for street in MAIN_STREETS.get(args.district, []):
        x = seg["street"].fillna("").str.contains(street, regex=False)
        row = {"street": street, "segments": int(x.sum()), "length_m": round(float(seg.loc[x, "length_m"].sum()), 0)}
        for r in (800, 2000):
            for label, col in (("choice", f"cc_betweenness_{r}_ang"), ("nach", f"nach_{r}"), ("nain", f"nain_{r}")):
                row[f"{label}_{r}_pct"] = round(float(seg[col].rank(pct=True)[x].median()), 2) if x.any() else None
        rows.append(row)
    pd.DataFrame(rows).to_csv(out / f"segments_{name}_main_streets.csv", index=False)

    for r in (800, 2000):
        nach_map(seg, ctx, district.dissolve(), r, args.district, out / "maps" / f"segments_{name}_nach_{r}.png")

    (out / f"segments_{name}_metadata.json").write_text(json.dumps(meta, indent=2, default=str))
    log("done")


if __name__ == "__main__":
    main()
