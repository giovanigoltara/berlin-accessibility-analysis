"""Run the full pipeline on pyrosm's bundled Helsinki sample with a synthetic
GTFS feed and two synthetic districts. Checks plumbing, not results."""
import json
import shutil
import zipfile

import geopandas as gpd
import pandas as pd
import pytest
import yaml
from shapely.geometry import box

pyrosm = pytest.importorskip("pyrosm")


def make_gtfs(path, stops):
    routes = pd.DataFrame({"route_id": ["r_s", "r_bus", "r_sev"], "route_type": [109, 700, 700], "route_short_name": ["S1", "100", "U2"]})
    trips = pd.DataFrame({"trip_id": ["t_s", "t_bus", "t_sev"], "route_id": ["r_s", "r_bus", "r_sev"]})
    st = pd.DataFrame({"trip_id": ["t_s", "t_bus", "t_bus", "t_sev"], "stop_id": ["s0", "s1", "s2", "s2"]})
    cal = pd.DataFrame({"service_id": ["x"], "start_date": ["20260101"], "end_date": ["20261231"]})
    with zipfile.ZipFile(path, "w") as z:
        for name, df in {"routes": routes, "trips": trips, "stop_times": st, "stops": stops, "calendar": cal}.items():
            z.writestr(f"{name}.txt", df.to_csv(index=False))


def test_pipeline_runs_on_sample(tmp_path):
    from berlin_access.config import load_config
    from berlin_access.pipeline import run
    import build_readme_tables

    pbf = pyrosm.get_data("helsinki_pbf")
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    shutil.copy(pbf, raw / "sample.osm.pbf")

    nodes, _ = pyrosm.OSM(pbf).get_network(network_type="walking", nodes=True)
    x0, y0, x1, y1 = nodes.total_bounds
    xm = (x0 + x1) / 2
    d = gpd.GeoDataFrame({"name": ["West", "East"]}, geometry=[box(x0, y0, xm, y1), box(xm, y0, x1, y1)], crs=4326)
    d.to_file(tmp_path / "districts.geojson", driver="GeoJSON")

    sample = nodes.sample(3, random_state=1)
    stops = pd.DataFrame({"stop_id": ["s0", "s1", "s2"], "stop_name": ["a", "b", "c"], "stop_lat": sample.geometry.y.values, "stop_lon": sample.geometry.x.values})
    make_gtfs(raw / "gtfs.zip", stops)

    cfg_dict = yaml.safe_load(open(load_config().root / "config.yaml"))
    cfg_dict["paths"] = {"pbf": "data/raw/sample.osm.pbf", "gtfs": "data/raw/gtfs.zip", "districts": "districts.geojson", "derived": "derived", "output": "output"}
    cfg_dict["district_name_column"] = "name"
    cfg_dict["crs"] = "EPSG:3067"
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(cfg_dict))
    cfg = load_config(tmp_path / "config.yaml")

    run(cfg)

    out = tmp_path / "output"
    s = pd.read_csv(out / "walk_time_by_district.csv")
    assert set(s["district"]) == {"Berlin", "East", "West"}
    assert set(s["speed_mps"]) == {1.0, 1.3, 1.4}
    berlin = s[(s["district"] == "Berlin") & (s["speed_mps"] == 1.3)].set_index("mode")
    # every building on the connected network reaches the S-Bahn and Bus stops
    assert berlin.loc["S-Bahn", "n_unreachable"] == 0
    assert berlin.loc["Bus", "n_unreachable"] == 0
    # U-Bahn has only a replacement bus in this feed, so no stops
    assert berlin.loc["U-Bahn", "n_unreachable"] == berlin.loc["U-Bahn", "n_buildings"]
    # slower walking -> longer times, same ordering
    b = s[(s["district"] == "Berlin") & (s["mode"] == "Bus")].set_index("speed_mps")["median_min"]
    assert b[1.0] > b[1.3] > b[1.4]
    assert (out / "median_walk_min_1.3mps.csv").exists()
    assert (out / f"walk_time_by_district_stopbuffer_{cfg_dict['stop_buffer_sensitivity_m']}m.csv").exists()
    meta = json.loads((out / "run_metadata.json").read_text())
    assert meta["buildings"]["buildings_used"] > 0

    (tmp_path / "README.md").write_text(f"x\n{build_readme_tables.BEGIN}\nold\n{build_readme_tables.END}\n")
    text = build_readme_tables.build(cfg)
    assert "Median walk time" in text and "S-Bahn" in text
