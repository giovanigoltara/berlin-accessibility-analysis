"""End-to-end walk-to-transit pipeline: network, buildings, residents, stops, distances, tables."""
from __future__ import annotations

import hashlib
import re
import json
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pyrosm import OSM
from scipy import sparse
from shapely.validation import make_valid

from . import gtfs_modes, population
from .config import Config
from .network import WalkNetwork, build_network, load_walk_edges, multi_source_distance, snap

# Reporting levels: column in the building table -> (output name, name column)
UNIT_LEVELS = {
    "district": ("district", "district"),
    "bzr_id": ("bezirksregion", "bzr_name"),
    "plr_id": ("planungsraum", "plr_name"),
}


def report_modes(cfg: Config) -> list[str]:
    """Transit modes plus combined modes (e.g. nearest S- or U-Bahn), in report order."""
    return list(cfg["modes"]) + list(cfg.raw.get("combined_modes", {}))


def mode_slug(mode: str) -> str:
    """File-name friendly mode name: 'S- or U-Bahn' -> 'S-or-U-Bahn'."""
    return re.sub(r"[^A-Za-z0-9]+", "-", mode).strip("-")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_lor(path: Path, crs: str) -> gpd.GeoDataFrame:
    """LOR 2021 Planungsräume with their Bezirksregion and district."""
    g = gpd.read_file(path).to_crs(crs)
    g["district"] = g["bez"].str.split(" - ", n=1).str[1].str.strip()
    g["geometry"] = g.geometry.map(make_valid)
    return g[["plr_id", "plr_name", "bzr_id", "bzr_name", "district", "geometry"]].sort_values("plr_id").reset_index(drop=True)


def load_buildings(osm: OSM, lor: gpd.GeoDataFrame, net: WalkNetwork) -> tuple[gpd.GeoDataFrame, dict]:
    """One representative point per OSM building polygon inside Berlin, with its
    LOR units, footprint, type and storeys, snapped to the network."""
    poly = osm.get_buildings(extra_attributes=["building:levels", "building:use"])
    stats = {"osm_buildings": len(poly)}
    poly = poly[poly.geometry.notna() & ~poly.geometry.is_empty]
    poly = poly[poly.geom_type.isin(["Polygon", "MultiPolygon"])].to_crs(net.crs)
    poly["geometry"] = poly.geometry.map(make_valid)
    pts = gpd.GeoDataFrame(
        {
            "osm_id": poly["id"].to_numpy(),
            "building": poly["building"].to_numpy(),
            "building_use": poly["building:use"].to_numpy() if "building:use" in poly else None,
            "levels": poly["building:levels"].to_numpy() if "building:levels" in poly else None,
            "footprint_m2": poly.geometry.area.to_numpy(),
        },
        geometry=poly.geometry.representative_point().to_numpy(),
        crs=net.crs,
    )
    # Assign by point location (not by clipping the polygon), so each building
    # is counted once, in the unit that contains its representative point.
    pts = gpd.sjoin(pts, lor.drop(columns=["plr_name", "bzr_name"]), predicate="within", how="inner")
    pts = pts.drop(columns="index_right").reset_index(drop=True)
    pts["node"], pts["snap_m"] = snap(net, pts.geometry)
    stats["building_points_in_berlin"] = len(pts)
    return pts, stats


def load_stops(tables: dict, routes: pd.DataFrame, city, net: WalkNetwork, buffer_m: float):
    sm = gtfs_modes.stop_modes(tables, routes)
    sm = sm[np.isfinite(sm["stop_lat"]) & np.isfinite(sm["stop_lon"])]
    g = gpd.GeoDataFrame(sm, geometry=gpd.points_from_xy(sm["stop_lon"], sm["stop_lat"], crs=4326)).to_crs(net.crs)
    g = g[g.within(city.buffer(buffer_m))].copy()
    g["inside_berlin"] = g.within(city)
    g["m_outside_berlin"] = np.where(g["inside_berlin"], 0.0, g.distance(city))
    g = g.reset_index(drop=True)
    g["node"], g["snap_m"] = snap(net, g.geometry)
    return g


def stop_summary(stops: gpd.GeoDataFrame, max_snap_m: float, buffer_m: float) -> pd.DataFrame:
    """Stop counts per mode. `stops_used` is for the main run (stops within
    `buffer_m` of Berlin and close enough to the network)."""
    s = stops.assign(
        snap_ok=stops["snap_m"] <= max_snap_m,
        used=(stops["snap_m"] <= max_snap_m) & (stops["m_outside_berlin"] <= buffer_m),
    )
    out = s.groupby("mode").agg(
        stops_inside_berlin=("inside_berlin", "sum"),
        stops_outside_within_sensitivity_buffer=("inside_berlin", lambda x: int((~x).sum())),
        stops_dropped_snap=("snap_ok", lambda x: int((~x).sum())),
        stops_used=("used", "sum"),
        snap_m_median=("snap_m", "median"),
    )
    out["snap_m_median"] = out["snap_m_median"].round(1)
    return out.reset_index()


def weighted_quantiles(x: np.ndarray, w: np.ndarray, qs) -> list[float]:
    """Quantiles of x where each value counts with weight w (inverse of the weighted CDF)."""
    order = np.argsort(x)
    x, w = x[order], w[order]
    cw = np.cumsum(w)
    return [float(x[min(np.searchsorted(cw, q * cw[-1], side="left"), len(x) - 1)]) for q in qs]


def aggregate(
    dist: pd.DataFrame,
    unit_col: str,
    modes: list[str],
    speeds: list[float],
    thresholds: list[int],
    weight_col: str | None = None,
) -> pd.DataFrame:
    """Per unit, mode and walking speed: median, quartiles, mean and shares beyond thresholds.

    With `weight_col` every building counts with that weight (residents),
    otherwise each building counts once. No building is dropped for being far
    away; the shares make the tail visible. A city-wide "Berlin" row is added.
    """
    rows = []
    groups = [("Berlin", dist)] + list(dist.groupby(unit_col))
    for unit, g in groups:
        w_all = g[weight_col].to_numpy(dtype=float) if weight_col else np.ones(len(g))
        for mode in modes:
            d_m = g[f"dist_m_{mode}"].to_numpy()
            ok = np.isfinite(d_m) & (w_all > 0)
            w = w_all[ok]
            for v in speeds:
                t = d_m[ok] / v / 60.0
                row = {
                    "unit_id": unit,
                    "mode": mode,
                    "speed_mps": v,
                    "n_buildings": int((w_all > 0).sum()),
                    "residents": round(float(w_all.sum()), 1) if weight_col else None,
                    "n_unreachable": int(((~np.isfinite(d_m)) & (w_all > 0)).sum()),
                }
                if len(t) and w.sum() > 0:
                    q25, q50, q75 = weighted_quantiles(t, w, [0.25, 0.5, 0.75])
                    row.update(median_min=q50, p25_min=q25, p75_min=q75, mean_min=float(np.average(t, weights=w)))
                    for th in thresholds:
                        row[f"share_over_{th}min"] = float(w[t > th].sum() / w.sum())
                rows.append(row)
    out = pd.DataFrame(rows)
    num = [c for c in out.columns if c.endswith("_min") or c.startswith("share_")]
    out[num] = out[num].round(4)
    return out


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def load_or_build_base(cfg: Config, lor: gpd.GeoDataFrame, city) -> tuple[WalkNetwork, gpd.GeoDataFrame, dict]:
    """Network and buildings, cached in data/derived/ because parsing the PBF
    takes most of the run time. The cache is keyed by the input file hashes
    and the parameters that change it."""
    der = cfg.path("derived")
    pbf, lor_path = cfg.path("pbf"), cfg.path("lor")
    key = {
        "pbf_sha256": _sha256(pbf),
        "lor_sha256": _sha256(lor_path),
        "network_buffer_m": cfg["network_buffer_m"],
        "crs": cfg["crs"],
        "version": 2,
    }
    key_file, net_file, bld_file = der / "base_key.json", der / "network.npz", der / "buildings_base.parquet"
    if key_file.exists() and net_file.exists() and bld_file.exists() and json.loads(key_file.read_text()) == key:
        log("using cached network and buildings")
        z = np.load(net_file, allow_pickle=False)
        adj = sparse.csr_matrix((z["data"], z["indices"], z["indptr"]), shape=tuple(z["shape"]))
        net = WalkNetwork(node_ids=z["node_ids"], xy=z["xy"], adj=adj, crs=cfg["crs"])
        stats = json.loads(str(z["stats"]))
        return net, gpd.read_parquet(bld_file), stats

    log("reading walk network")
    read_area = gpd.GeoSeries([city.buffer(cfg["network_buffer_m"])], crs=cfg["crs"]).to_crs(4326).iloc[0]
    osm = OSM(str(pbf), bounding_box=read_area, keep_metadata=False)
    nodes, edges = load_walk_edges(osm, cfg["crs"])
    net, nstats = build_network(nodes, edges, cfg["crs"])
    del nodes, edges
    log(f"network: {nstats}")
    log("reading buildings")
    bld, bstats = load_buildings(osm, lor, net)
    stats = {"network": nstats, "buildings": bstats}
    np.savez(
        net_file, data=net.adj.data, indices=net.adj.indices, indptr=net.adj.indptr, shape=np.array(net.adj.shape),
        node_ids=net.node_ids, xy=net.xy, stats=json.dumps(stats),
    )
    bld.to_parquet(bld_file)
    key_file.write_text(json.dumps(key, indent=2))
    return net, bld, stats


def run(cfg: Config) -> None:
    out_dir = cfg.path("output")
    der_dir = cfg.path("derived")
    out_dir.mkdir(parents=True, exist_ok=True)
    der_dir.mkdir(parents=True, exist_ok=True)
    crs = cfg["crs"]
    modes = cfg["modes"]
    speeds = sorted(set(cfg["walk_speeds_mps"]) | {cfg["walk_speed_main_mps"]})
    thresholds = cfg["share_thresholds_min"]
    meta: dict = {"config": cfg.raw}

    inputs = {k: cfg.path(k) for k in ("pbf", "gtfs", "lor", "population")}
    for p in inputs.values():
        if not p.exists():
            raise FileNotFoundError(f"{p} missing. Run scripts/download_data.py first (see README).")
    meta["inputs"] = {k: {"file": p.name, "bytes": p.stat().st_size} for k, p in inputs.items()}
    dl_log = cfg.path("pbf").parent / "download_log.json"
    if dl_log.exists():
        meta["downloads"] = json.loads(dl_log.read_text())

    lor = load_lor(cfg.path("lor"), crs)
    city = lor.union_all()
    log(f"LOR Planungsräume: {len(lor)}, districts: {lor['district'].nunique()}")

    net, bld, base_stats = load_or_build_base(cfg, lor, city)
    meta.update(base_stats)
    bstats = meta["buildings"]

    max_b = cfg["max_building_snap_m"]
    bstats["buildings_snap_over_max"] = int((bld["snap_m"] > max_b).sum())
    bld = bld[bld["snap_m"] <= max_b].reset_index(drop=True)
    bstats["buildings_used"] = len(bld)
    bstats["building_snap_m_median"] = round(float(bld["snap_m"].median()), 1)
    log(f"buildings: {bstats}")

    log("allocating residents")
    pop = population.read_plr_population(cfg.path("population"))
    unknown = sorted(set(pop["plr_id"]) - set(lor["plr_id"]))
    if unknown:
        raise ValueError(f"population table has Planungsraum ids not in LOR: {unknown[:10]}")
    # The report lists Planungsräume without registered residents in its key
    # table but not in T2 (e.g. 03400831 Pankower Tor): they get 0 residents.
    absent = sorted(set(lor["plr_id"]) - set(pop["plr_id"]))
    pop = pd.concat([pop, pd.DataFrame({"plr_id": absent, "residents": 0})], ignore_index=True).fillna(0)
    weight, wstats = population.residential_weight(bld, cfg["min_residential_footprint_m2"])
    bld["residents"], pop_check = population.allocate_residents(bld, pop, weight)
    pop_check = pop_check.merge(lor[["plr_id", "plr_name", "district"]], on="plr_id", how="left")
    pop_check.to_csv(out_dir / "population_allocation_check.csv", index=False)
    meta["residents"] = {
        **wstats,
        "register_total": int(pop["residents"].sum()),
        "planungsraeume_absent_from_population_table": absent,
        "allocated_total": round(float(bld["residents"].sum()), 1),
        "planungsraeume_with_unallocated_residents": int((pop_check["unallocated"] > 0.5).sum()),
        "unallocated_total": round(float(pop_check["unallocated"].clip(lower=0).sum()), 1),
    }
    log(f"residents: {meta['residents']}")

    log("reading GTFS")
    tables = gtfs_modes.read_gtfs_tables(cfg.path("gtfs"))
    meta["gtfs_feed"] = gtfs_modes.feed_validity(tables)
    routes = gtfs_modes.classify_routes(tables["routes"])
    check = gtfs_modes.route_type_check(routes)
    check.to_csv(out_dir / "gtfs_route_type_check.csv", index=False)
    print(check.to_string(index=False))
    meta["routes_by_mode_source"] = routes["mode_source"].value_counts().to_dict()

    buf_main = cfg["stop_buffer_m"]
    buf_sens = cfg.raw.get("stop_buffer_sensitivity_m")
    stops = load_stops(tables, routes, city, net, max(buf_main, buf_sens or 0))
    ssum = stop_summary(stops, cfg["max_stop_snap_m"], buf_main)
    ssum.to_csv(out_dir / "stops_by_mode.csv", index=False)
    print(ssum.to_string(index=False))
    stops = stops[stops["snap_m"] <= cfg["max_stop_snap_m"]]

    # Main run, plus a sensitivity run with a different stop buffer.
    scenarios = {"": buf_main}
    if buf_sens is not None and buf_sens != buf_main:
        scenarios[f"_stopbuffer_{buf_sens}m"] = buf_sens

    dist = bld[["osm_id", "district", "bzr_id", "plr_id", "building", "footprint_m2", "snap_m", "residents"]].copy()
    for suffix, buf in scenarios.items():
        for mode in modes:
            s = stops[(stops["mode"] == mode) & (stops["m_outside_berlin"] <= buf)]
            log(f"dijkstra {mode}, stop buffer {buf} m: {len(s)} stops")
            d_node = multi_source_distance(net, s["node"].to_numpy(), s["snap_m"].to_numpy())
            dist[f"dist_m_{mode}{suffix}"] = d_node[bld["node"].to_numpy()] + bld["snap_m"].to_numpy()
        # Nearest stop of any of several modes = the shortest of their distances.
        for name, members in cfg.raw.get("combined_modes", {}).items():
            dist[f"dist_m_{name}{suffix}"] = dist[[f"dist_m_{m}{suffix}" for m in members]].min(axis=1)
    modes = report_modes(cfg)

    gpd.GeoDataFrame(dist, geometry=bld.geometry, crs=crs).to_parquet(der_dir / "building_walk_dist.parquet")

    names = {
        "district": pd.Series(lor["district"].unique(), index=lor["district"].unique()),
        "bzr_id": lor.drop_duplicates("bzr_id").set_index("bzr_id")["bzr_name"],
        "plr_id": lor.set_index("plr_id")["plr_name"],
    }
    parents = {"bzr_id": lor.drop_duplicates("bzr_id").set_index("bzr_id")["district"], "plr_id": lor.set_index("plr_id")["district"]}
    min_res = cfg["min_unit_residents"]
    log("aggregating")
    for suffix in scenarios:
        cols = {f"dist_m_{m}{suffix}": f"dist_m_{m}" for m in modes}
        d = dist[["district", "bzr_id", "plr_id", "residents", *cols]].rename(columns=cols)
        for unit_col, (level, _) in UNIT_LEVELS.items():
            parts = []
            for weighting, wcol in (("residents", "residents"), ("buildings", None)):
                a = aggregate(d, unit_col, modes, speeds, thresholds, weight_col=wcol)
                a.insert(1, "weighting", weighting)
                parts.append(a)
            a = pd.concat(parts, ignore_index=True)
            a.insert(1, "unit_name", a["unit_id"].map(names[unit_col]).fillna(a["unit_id"]))
            if unit_col in parents:
                a.insert(2, "district", a["unit_id"].map(parents[unit_col]))
            res = a[a["weighting"] == "residents"].drop_duplicates("unit_id").set_index("unit_id")["residents"]
            a["low_population"] = a["unit_id"].map(res) < min_res
            a.to_csv(out_dir / f"walk_time_by_{level}{suffix}.csv", index=False)
            if suffix or level != "district":
                continue
            main = a[a["weighting"] == "residents"]
            for v in speeds:
                wide = main[main["speed_mps"] == v].pivot(index="unit_id", columns="mode", values="median_min")
                wide.reindex(columns=modes).round(2).rename_axis("district").to_csv(out_dir / f"median_walk_min_{v:.1f}mps.csv")

    meta["generated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (out_dir / "run_metadata.json").write_text(json.dumps(meta, indent=2, default=str, ensure_ascii=False))
    log("done")
