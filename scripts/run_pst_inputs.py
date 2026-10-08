"""Phase 2: export Place Syntax Tool inputs and run the Python cross-check.

Usage: python scripts/run_pst_inputs.py --district Friedrichshain-Kreuzberg

Writes
  output/pst/pst_inputs_<district>.gpkg   layers for QGIS/PST:
      segments      segment lines of the citywide Phase 1 map within district + 2 km
      origins       residential buildings in the district (points), with residents
      destinations  stations inside Berlin within district + 2 km, 0/1 columns per mode
      study_area    the district polygon
      unlinks       points where segment lines cross without being connected
  output/pst/python_reach_<district>.csv  per-building attraction reach and distance
  output/pst/python_reach_<district>_by_planungsraum.csv   resident-weighted summary
  output/pst/python_reach_<district>_summary.json          counts and checks

Requires scripts/run_accessibility.py and scripts/run_segments.py --district Berlin.
"""
import argparse
import json
import re

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import _bootstrap  # noqa: F401

from berlin_access import gtfs_modes, pst
from berlin_access.config import load_config
from berlin_access.pipeline import load_lor

RADII = [400, 800]
DIST_LIMIT_M = 2000
COLUMNS = ["sb", "ub", "tr", "bu", "rb", "su", "anyf"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    ap.add_argument("--district", default="Friedrichshain-Kreuzberg")
    ap.add_argument("--buffer-m", type=int, default=2000)
    args = ap.parse_args()
    cfg = load_config(args.config)
    crs, out, der = cfg["crs"], cfg.path("output"), cfg.path("derived")
    pdir = out / "pst"
    pdir.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^a-z0-9]+", "-", args.district.lower()).strip("-")

    lor = load_lor(cfg.path("lor"), crs)
    city = lor.union_all()
    study = lor[lor["district"] == args.district].union_all()
    area = study.buffer(args.buffer_m)
    meta = {"district": args.district, "buffer_m": args.buffer_m, "radii_m": RADII, "distance_limit_m": DIST_LIMIT_M}

    # Segments: the citywide Phase 1 segment map, cropped.
    seg = gpd.read_file(out / "segments_berlin.gpkg", bbox=tuple(area.bounds))
    seg = seg[seg.intersects(area)].reset_index(drop=True)
    seg = gpd.GeoDataFrame({
        "seg_id": np.arange(len(seg)), "street": seg["street"], "district": seg["district"],
        "in_study": (seg["district"] == args.district) & seg["live"].astype(bool),
        "residential": seg["residential"].astype(bool), "length_m": seg.geometry.length.round(1),
    }, geometry=seg.geometry, crs=crs)

    # Origins: residential buildings in the district.
    b = gpd.read_parquet(der / "building_walk_dist.parquet").to_crs(crs)
    b = b[(b["district"] == args.district) & (b["residents"] > 0)].reset_index(drop=True)
    orig = gpd.GeoDataFrame({
        "osm_id": b["osm_id"], "plr_id": b["plr_id"], "residents": b["residents"].round(2),
        "res65": b["residents_65plus"].round(2),
    }, geometry=b.geometry, crs=crs)

    # Destinations: stations inside Berlin (strict city limit, as in Phase 0).
    tables = gtfs_modes.read_gtfs_tables(cfg.path("gtfs"))
    routes = gtfs_modes.classify_routes(tables["routes"])
    fq = cfg["frequency"]
    dep = gtfs_modes.stop_departures(tables, routes, str(fq["date"]), fq["window"][0], fq["window"][1])
    window_min = (pd.Timestamp(f"2000-01-01 {fq['window'][1]}") - pd.Timestamp(f"2000-01-01 {fq['window'][0]}")).seconds / 60
    st = pst.stations(gtfs_modes.stop_modes(tables, routes), dep, window_min / fq["max_headway_min"])
    st = gpd.GeoDataFrame(st, geometry=gpd.points_from_xy(st["stop_lon"], st["stop_lat"], crs=4326)).to_crs(crs)
    st = st[st.within(city) & st.within(area)].drop(columns=["stop_lon", "stop_lat"]).reset_index(drop=True)
    meta["stations_by_column"] = {c: int(st[c].sum()) for c in COLUMNS}

    gpkg = pdir / f"pst_inputs_{name}.gpkg"
    seg.to_file(gpkg, layer="segments", driver="GPKG")
    orig.to_file(gpkg, layer="origins", driver="GPKG")
    st.to_file(gpkg, layer="destinations", driver="GPKG")
    gpd.GeoDataFrame({"district": [args.district]}, geometry=[study], crs=crs).to_file(gpkg, layer="study_area", driver="GPKG")
    unl = pst.unlink_points(seg)
    unl.to_file(gpkg, layer="unlinks", driver="GPKG")
    meta.update(segments=len(seg), origins=len(orig), destinations=len(st), unlink_points=len(unl))
    print(f"wrote {gpkg.name}: {len(seg)} segments, {len(orig)} origins, {len(st)} stations")

    # Python cross-check: walking distance on the same segment lines.
    g = pst.SegmentGraph(seg)
    o_att, d_att = g.attach(orig.geometry), g.attach(st.geometry)
    d_att = d_att.join(st[COLUMNS])
    dist = pst.walking_distances(g, o_att, d_att, DIST_LIMIT_M)
    res = pst.reach_and_distance(dist, d_att, COLUMNS, RADII)
    res.insert(0, "osm_id", orig["osm_id"].to_numpy())
    res.insert(1, "plr_id", orig["plr_id"].to_numpy())
    res.insert(2, "residents", orig["residents"].to_numpy())
    res.insert(3, "origin_connection_m", o_att["conn"].round(1).to_numpy())
    res.round(1).to_csv(pdir / f"python_reach_{name}.csv", index=False)
    meta["origin_connection_m_median"] = round(float(o_att["conn"].median()), 1)
    meta["destination_connection_m_median"] = round(float(d_att["conn"].median()), 1)

    # Resident-weighted summary per Planungsraum.
    w = res["residents"]
    rows = []
    for plr, g_ in res.groupby("plr_id"):
        ww = g_["residents"]
        row = {"plr_id": plr, "plr_name": lor.set_index("plr_id")["plr_name"].get(plr), "residents": round(ww.sum(), 0)}
        for c in COLUMNS:
            for r in RADII:
                row[f"reach_{c}_{r}_mean"] = round(float(np.average(g_[f"reach_{c}_{r}"], weights=ww)), 2)
            row[f"share_no_{c}_within_800"] = round(float(ww[g_[f"reach_{c}_800"] == 0].sum() / ww.sum()), 3)
        rows.append(row)
    pd.DataFrame(rows).to_csv(pdir / f"python_reach_{name}_by_planungsraum.csv", index=False)

    # Check against Phase 0 (full walking network incl. sidewalks, nearest stop point).
    p0 = gpd.read_parquet(der / "building_walk_dist.parquet")[["osm_id", "dist_m_S- or U-Bahn"]]
    cmp_ = res[["osm_id", "dist_su"]].merge(p0, on="osm_id")
    ok = np.isfinite(cmp_["dist_su"]) & np.isfinite(cmp_["dist_m_S- or U-Bahn"]) & (cmp_["dist_m_S- or U-Bahn"] <= DIST_LIMIT_M)
    meta["check_vs_phase0_su"] = {
        "buildings_compared": int(ok.sum()),
        "spearman": round(float(spearmanr(cmp_.loc[ok, "dist_su"], cmp_.loc[ok, "dist_m_S- or U-Bahn"]).statistic), 3),
        "median_segment_map_m": round(float(cmp_.loc[ok, "dist_su"].median()), 1),
        "median_phase0_m": round(float(cmp_.loc[ok, "dist_m_S- or U-Bahn"].median()), 1),
    }
    meta["resident_weighted_share_without_su_within_800m"] = round(float(w[res["reach_su_800"] == 0].sum() / w.sum()), 3)
    meta["resident_weighted_share_without_frequent_stop_within_400m"] = round(float(w[res["reach_anyf_400"] == 0].sum() / w.sum()), 3)
    (pdir / f"python_reach_{name}_summary.json").write_text(json.dumps(meta, indent=2, default=str, ensure_ascii=False))
    print(json.dumps(meta, indent=2, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
