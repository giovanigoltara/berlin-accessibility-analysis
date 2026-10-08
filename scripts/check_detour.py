"""Compare network walk distance with straight-line distance to the nearest stop.

A network/straight-line ratio far above typical urban detour factors would
point at a broken graph; a large straight-line distance points at where the
buildings are. Reads data/derived/building_walk_dist.parquet and the GTFS
feed; writes output/detour_check.csv (per district and mode).
"""
import numpy as np
import pandas as pd
import geopandas as gpd
from scipy.spatial import cKDTree

import _bootstrap  # noqa: F401

from berlin_access import gtfs_modes
from berlin_access.config import load_config
from berlin_access.pipeline import load_lor

if __name__ == "__main__":
    cfg = load_config()
    b = gpd.read_parquet(cfg.path("derived") / "building_walk_dist.parquet").to_crs(cfg["crs"])
    t = gtfs_modes.read_gtfs_tables(cfg.path("gtfs"))
    sm = gtfs_modes.stop_modes(t, gtfs_modes.classify_routes(t["routes"]))
    sm = gpd.GeoDataFrame(sm, geometry=gpd.points_from_xy(sm.stop_lon, sm.stop_lat, crs=4326)).to_crs(cfg["crs"])
    # Same stop set as the main run: inside Berlin plus stop_buffer_m.
    city = load_lor(cfg.path("lor"), cfg["crs"]).union_all()
    sm = sm[sm.within(city.buffer(cfg["stop_buffer_m"])) if cfg["stop_buffer_m"] > 0 else sm.within(city)]
    bxy = np.c_[b.geometry.x, b.geometry.y]
    rows = []
    for mode in cfg["modes"]:
        s = sm[sm["mode"] == mode]
        eu, _ = cKDTree(np.c_[s.geometry.x, s.geometry.y]).query(bxy)
        net = b[f"dist_m_{mode}"].to_numpy()
        df = pd.DataFrame({"district": b["district"], "eu": eu, "net": net, "ratio": net / np.maximum(eu, 1.0)})
        for district, g in [("Berlin", df)] + list(df.groupby("district")):
            rows.append({
                "district": district, "mode": mode,
                "median_straight_line_m": round(g["eu"].median(), 0),
                "median_network_m": round(g["net"].median(), 0),
                "median_ratio": round(g["ratio"].median(), 2),
                "p95_ratio": round(g["ratio"].quantile(0.95), 2),
            })
    out = pd.DataFrame(rows)
    out.to_csv(cfg.path("output") / "detour_check.csv", index=False)
    print(out[out["district"].isin(["Berlin", "Neukölln", "Spandau"])].to_string(index=False))
