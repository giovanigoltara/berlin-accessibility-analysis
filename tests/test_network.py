import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point

from berlin_access.network import build_network, multi_source_distance
from berlin_access.pipeline import aggregate

CRS = "EPSG:32633"


def line_network():
    # 0 --100-- 1 --100-- 2 --100-- 3, plus a longer parallel way 0-1, plus an isolated pair 10-11.
    # Ways are drawn in mixed directions to catch one-way traversal.
    pts = {0: (0, 0), 1: (100, 0), 2: (200, 0), 3: (300, 0), 10: (5000, 0), 11: (5050, 0)}
    nodes = gpd.GeoDataFrame({"id": list(pts)}, geometry=[Point(p) for p in pts.values()], crs=CRS)
    uv = [(1, 0), (1, 2), (3, 2), (0, 1), (10, 11)]
    geoms = [LineString([pts[u], pts[v]]) for u, v in uv]
    geoms[3] = LineString([(0, 0), (50, 80), (100, 0)])  # parallel, longer
    edges = gpd.GeoDataFrame({"u": [u for u, _ in uv], "v": [v for _, v in uv]}, geometry=geoms, crs=CRS)
    return build_network(nodes, edges, CRS)


def test_undirected_and_largest_component():
    net, stats = line_network()
    assert stats["graph_nodes"] == 4
    assert stats["nodes_outside_largest_component"] == 2
    i = {nid: k for k, nid in enumerate(net.node_ids)}
    # Source at node 3: reaching node 0 needs traversal against the drawing direction of 3->2 and 1->0? both ways must work
    d = multi_source_distance(net, np.array([i[3]]), np.array([0.0]))
    assert np.isclose(d[i[0]], 300, atol=0.05)
    d = multi_source_distance(net, np.array([i[0]]), np.array([0.0]))
    assert np.isclose(d[i[3]], 300, atol=0.05)  # parallel longer way does not get summed in


def test_snap_offset_and_nearest_source():
    net, _ = line_network()
    i = {nid: k for k, nid in enumerate(net.node_ids)}
    d = multi_source_distance(net, np.array([i[0], i[3]]), np.array([40.0, 0.0]))
    assert np.isclose(d[i[1]], 140, atol=0.05)
    assert np.isclose(d[i[2]], 100, atol=0.05)
    assert np.all(np.isinf(multi_source_distance(net, np.array([], dtype=int), np.array([]))))


def test_aggregate_keeps_long_walks():
    dist = pd.DataFrame({"district": ["A"] * 4, "dist_m_Bus": [60.0, 120.0, 1800.0, np.inf]})
    s = aggregate(dist, "district", ["Bus"], [1.0], [15, 30]).set_index("unit_id")
    a = s.loc["A"]
    assert a["n_buildings"] == 4 and a["n_unreachable"] == 1
    assert np.isclose(a["median_min"], 2.0)
    assert np.isclose(a["share_over_15min"], 1 / 3, atol=1e-3)
    assert a["share_over_30min"] == 0.0
