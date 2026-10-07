"""End-to-end walk-to-transit pipeline: network, buildings, stops, distances, tables."""
from __future__ import annotations

import json
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pyrosm import OSM
from shapely.validation import make_valid

from . import gtfs_modes
from .config import Config
from .network import WalkNetwork, build_network, load_walk_edges, multi_source_distance, snap


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_districts(path: Path, name_col: str, crs: str) -> gpd.GeoDataFrame:
    d = gpd.read_file(path)
    if d.crs is None:
        d = d.set_crs(4326)
    d = d.rename(columns={name_col: "district"})[["district", "geometry"]].to_crs(crs)
    d["geometry"] = d.geometry.map(make_valid)
    return d.sort_values("district").reset_index(drop=True)


def load_buildings(osm: OSM, districts: gpd.GeoDataFrame, net: WalkNetwork) -> tuple[gpd.GeoDataFrame, dict]:
    """One representative point per OSM building polygon inside a district, snapped to the network."""
    poly = osm.get_buildings()
    stats = {"osm_buildings": len(poly)}
    poly = poly[poly.geometry.notna() & ~poly.geometry.is_empty]
    poly = poly[poly.geom_type.isin(["Polygon", "MultiPolygon"])].to_crs(net.crs)
    poly["geometry"] = poly.geometry.map(make_valid)
    pts = gpd.GeoDataFrame(
        {"osm_id": poly["id"].to_numpy()}, geometry=poly.geometry.representative_point().to_numpy(), crs=net.crs
    )
    # Assign by point location (not by clipping the polygon), so each building
    # is counted once, in the district that contains its representative point.
    pts = gpd.sjoin(pts, districts, predicate="within", how="inner").drop(columns="index_right")
    pts = pts.reset_index(drop=True)
    pts["node"], pts["snap_m"] = snap(net, pts.geometry)
    stats["building_points_in_districts"] = len(pts)
    return pts, stats


def load_stops(tables: dict, routes: pd.DataFrame, districts: gpd.GeoDataFrame, net: WalkNetwork, buffer_m: float):
    sm = gtfs_modes.stop_modes(tables, routes)
    sm = sm[np.isfinite(sm["stop_lat"]) & np.isfinite(sm["stop_lon"])]
    g = gpd.GeoDataFrame(sm, geometry=gpd.points_from_xy(sm["stop_lon"], sm["stop_lat"], crs=4326)).to_crs(net.crs)
    city = districts.union_all()
    g = g[g.within(city.buffer(buffer_m))].copy()
    g["inside_berlin"] = g.within(city)
    g = g.reset_index(drop=True)
    g["node"], g["snap_m"] = snap(net, g.geometry)
    return g


def stop_summary(stops: gpd.GeoDataFrame, max_snap_m: float) -> pd.DataFrame:
    s = stops.assign(used=stops["snap_m"] <= max_snap_m)
    out = s.groupby("mode").agg(
        stops_total=("stop_id", "size"),
        stops_inside_berlin=("inside_berlin", "sum"),
        stops_in_buffer_zone=("inside_berlin", lambda x: int((~x).sum())),
        stops_dropped_snap=("used", lambda x: int((~x).sum())),
        stops_used=("used", "sum"),
        snap_m_median=("snap_m", "median"),
    )
    out["snap_m_median"] = out["snap_m_median"].round(1)
    return out.reset_index()


def aggregate(dist: pd.DataFrame, modes: list[str], speeds: list[float], thresholds: list[int]) -> pd.DataFrame:
    """Per district, mode and walking speed: median, quartiles and shares beyond thresholds.

    No building is dropped for being far away; the shares make the tail visible.
    """
    rows = []
    groups = [("Berlin", dist)] + list(dist.groupby("district"))
    for district, g in groups:
        for mode in modes:
            d_m = g[f"dist_m_{mode}"].to_numpy()
            reachable = np.isfinite(d_m)
            for v in speeds:
                t = d_m[reachable] / v / 60.0
                row = {
                    "district": district,
                    "mode": mode,
                    "speed_mps": v,
                    "n_buildings": int(len(d_m)),
                    "n_unreachable": int((~reachable).sum()),
                }
                if len(t):
                    q25, q50, q75 = np.percentile(t, [25, 50, 75])
                    row.update(median_min=q50, p25_min=q25, p75_min=q75, mean_min=t.mean())
                    for th in thresholds:
                        row[f"share_over_{th}min"] = float((t > th).mean())
                rows.append(row)
    out = pd.DataFrame(rows)
    num = [c for c in out.columns if c.endswith("_min") or c.startswith("share_")]
    out[num] = out[num].round(4)
    return out


def run(cfg: Config) -> None:
    out_dir = cfg.path("output")
    der_dir = cfg.path("derived")
    out_dir.mkdir(parents=True, exist_ok=True)
    der_dir.mkdir(parents=True, exist_ok=True)
    crs = cfg["crs"]
    modes = cfg["modes"]
    speeds = sorted(set(cfg["walk_speeds_mps"]) | {cfg["walk_speed_main_mps"]})
    meta: dict = {"config": cfg.raw}

    pbf, gtfs = cfg.path("pbf"), cfg.path("gtfs")
    for p in (pbf, gtfs):
        if not p.exists():
            raise FileNotFoundError(f"{p} missing. Run scripts/download_data.py first (see README).")
    meta["inputs"] = {
        "pbf": {"file": pbf.name, "bytes": pbf.stat().st_size, "mtime_utc": _mtime(pbf)},
        "gtfs": {"file": gtfs.name, "bytes": gtfs.stat().st_size, "mtime_utc": _mtime(gtfs)},
    }
    dl_log = pbf.parent / "download_log.json"
    if dl_log.exists():
        meta["downloads"] = json.loads(dl_log.read_text())

    districts = load_districts(cfg.path("districts"), cfg["district_name_column"], crs)
    log(f"districts: {len(districts)}")

    log("reading walk network")
    read_area = districts.union_all().buffer(cfg["network_buffer_m"])
    read_area = gpd.GeoSeries([read_area], crs=crs).to_crs(4326).iloc[0]
    osm = OSM(str(pbf), bounding_box=read_area, keep_metadata=False)
    nodes, edges = load_walk_edges(osm, crs)
    net, nstats = build_network(nodes, edges, crs)
    del nodes, edges
    meta["network"] = nstats
    log(f"network: {nstats}")

    log("reading buildings")
    bld, bstats = load_buildings(osm, districts, net)
    max_b = cfg["max_building_snap_m"]
    bstats["buildings_snap_over_max"] = int((bld["snap_m"] > max_b).sum())
    bld = bld[bld["snap_m"] <= max_b].reset_index(drop=True)
    bstats["buildings_used"] = len(bld)
    bstats["building_snap_m_median"] = round(float(bld["snap_m"].median()), 1)
    meta["buildings"] = bstats
    log(f"buildings: {bstats}")

    log("reading GTFS")
    tables = gtfs_modes.read_gtfs_tables(gtfs)
    meta["gtfs_feed"] = gtfs_modes.feed_validity(tables)
    routes = gtfs_modes.classify_routes(tables["routes"])
    check = gtfs_modes.route_type_check(routes)
    check.to_csv(out_dir / "gtfs_route_type_check.csv", index=False)
    print(check.to_string(index=False))
    meta["routes_by_mode_source"] = routes["mode_source"].value_counts().to_dict()

    stops = load_stops(tables, routes, districts, net, cfg["stop_buffer_m"])
    ssum = stop_summary(stops, cfg["max_stop_snap_m"])
    ssum.to_csv(out_dir / "stops_by_mode.csv", index=False)
    print(ssum.to_string(index=False))
    stops = stops[stops["snap_m"] <= cfg["max_stop_snap_m"]]

    dist = pd.DataFrame({"osm_id": bld["osm_id"], "district": bld["district"], "snap_m": bld["snap_m"]})
    for mode in modes:
        s = stops[stops["mode"] == mode]
        log(f"dijkstra {mode}: {len(s)} stops")
        d_node = multi_source_distance(net, s["node"].to_numpy(), s["snap_m"].to_numpy())
        dist[f"dist_m_{mode}"] = d_node[bld["node"].to_numpy()] + bld["snap_m"].to_numpy()

    gpd.GeoDataFrame(dist, geometry=bld.geometry, crs=crs).to_parquet(der_dir / "building_walk_dist.parquet")

    summary = aggregate(dist, modes, speeds, cfg["share_thresholds_min"])
    summary.to_csv(out_dir / "walk_time_by_district.csv", index=False)
    for v in speeds:
        wide = summary[summary["speed_mps"] == v].pivot(index="district", columns="mode", values="median_min")
        wide = wide.reindex(columns=modes).round(2)
        wide.to_csv(out_dir / f"median_walk_min_{v:.1f}mps.csv")

    meta["generated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (out_dir / "run_metadata.json").write_text(json.dumps(meta, indent=2, default=str, ensure_ascii=False))
    log("done")


def _mtime(p: Path) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(p.stat().st_mtime))
