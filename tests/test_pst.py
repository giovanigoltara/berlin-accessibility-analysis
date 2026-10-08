import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point

from berlin_access import pst

CRS = "EPSG:32633"


def lines():
    # a(0,0) -100- b(100,0) -100- c(100,100)
    return gpd.GeoDataFrame(geometry=[LineString([(0, 0), (100, 0)]), LineString([(100, 0), (100, 100)])], crs=CRS)


def test_station_key_and_flags():
    assert pst.station_key("de:11000:900007104::2") == "de:11000:900007104"
    assert pst.station_key("de:12070:900215110:1:50") == "de:12070:900215110"
    sm = pd.DataFrame({
        "stop_id": ["de:1:9::1", "de:1:9::2", "de:1:9::3", "de:1:8::1"],
        "mode": ["S-Bahn", "S-Bahn", "Bus", "Bus"],
        "stop_name": ["X", "X", "X", "Y"], "stop_lat": [52.0, 52.0, 52.0, 52.1], "stop_lon": [13.0, 13.002, 13.001, 13.1],
    })
    dep = pd.DataFrame({"stop_id": ["de:1:9::1", "de:1:9::3"], "mode": ["S-Bahn", "Bus"], "departures": [12, 3]})
    st = pst.stations(sm, dep, min_departures=12).set_index("station_id")
    assert len(st) == 2  # two platforms of X count once
    assert st.loc["de:1:9", "sb"] == 1 and st.loc["de:1:9", "bu"] == 1 and st.loc["de:1:9", "su"] == 1
    assert st.loc["de:1:9", "sbf"] == 1 and st.loc["de:1:9", "buf"] == 0 and st.loc["de:1:9", "anyf"] == 1
    assert st.loc["de:1:8", "sb"] == 0 and st.loc["de:1:8", "anyf"] == 0
    assert np.isclose(st.loc["de:1:9", "stop_lon"], 13.001)


def test_walking_distance_with_connections():
    g = pst.SegmentGraph(lines())
    origins = g.attach(gpd.GeoSeries([Point(20, 5)], crs=CRS))         # on line 0, 20 m from a, 5 m off
    dests = g.attach(gpd.GeoSeries([Point(103, 60), Point(70, -2)], crs=CRS))  # line 1 at 60 m; line 0 at 70 m
    dests["sb"] = [1, 0]
    d = pst.walking_distances(g, origins, dests, limit=1000)
    # to dest 0: 5 + (100-20) + 60 + 3 = 148; to dest 1 on the same line: 5 + 50 + 2 = 57
    assert np.allclose(d[0], [148, 57], atol=0.01)
    r = pst.reach_and_distance(d, dests, ["sb"], [100, 200])
    assert r.loc[0, "reach_sb_100"] == 0 and r.loc[0, "reach_sb_200"] == 1
    assert np.isclose(r.loc[0, "dist_sb"], 148, atol=0.01)
    assert np.isinf(pst.walking_distances(g, origins, dests, limit=100)[0, 0])


def test_unlink_points_only_for_unconnected_crossings():
    g = gpd.GeoDataFrame(geometry=[
        LineString([(0, 0), (100, 0)]),          # street
        LineString([(50, -50), (50, 50)]),       # bridge over it, no shared point
        LineString([(100, 0), (100, 100)]),      # joins the street at its end point
    ], crs=CRS)
    u = pst.unlink_points(g)
    assert len(u) == 1 and u.geometry.iloc[0].equals(Point(50, 0))
