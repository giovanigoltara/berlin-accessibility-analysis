import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import box

pyrosm = pytest.importorskip("pyrosm")
cityseer = pytest.importorskip("cityseer")

from cityseer.tools import graphs  # noqa: E402

from berlin_access import segments as sg  # noqa: E402

CRS = "EPSG:3067"


def test_segment_pipeline_on_sample():
    osm = pyrosm.OSM(pyrosm.get_data("helsinki_pbf"))
    nodes, edges, stats = sg.read_ways(osm, CRS)
    assert stats["osm_segments"] > 0
    G = sg.build_primal(nodes, edges, CRS)
    assert all("geom" in d and "highways" in d for _, _, d in G.edges(data=True))
    x0, y0, x1, y1 = nodes.total_bounds
    area_wgs = gpd.GeoSeries([box(*nodes.to_crs(4326).total_bounds)], crs=4326).iloc[0]
    G = sg.clean(G, sg.local_areas(osm), area_wgs, 3067)
    assert G.number_of_edges() > 0
    study = box(x0 + (x1 - x0) / 4, y0 + (y1 - y0) / 4, x1 - (x1 - x0) / 4, y1 - (y1 - y0) / 4)
    G = sg.mark_live(G, study)
    D = graphs.nx_to_dual(G)
    n = sg.centralities(D, distances=[400])
    live = n[n["live"]]
    assert 0 < len(live) < len(n)
    for c in ("cc_harmonic_400_ang", "cc_betweenness_400_ang", "cc_harmonic_400", "nain_400", "nach_400"):
        assert c in n.columns
    assert np.isfinite(live["nain_400"]).all() and (live["nain_400"] >= 0).all()
    names = sg.segment_names(G, n)
    assert names.notna().any()
