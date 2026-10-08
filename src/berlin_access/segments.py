"""Phase 1: angular segment analysis (Space Syntax) with cityseer.

The segment map is built from the same OSM extract as the accessibility
pipeline and cleaned with cityseer's own OSM recipe (`io._auto_clean_network`,
the one `io.osm_graph_from_poly` applies). That recipe asks the Overpass API
for park, plaza and parking areas; here those areas come from the local PBF
instead, so the result does not depend on a live API. Everything else in the
recipe is unchanged. cityseer is pinned (requirements.txt) because the recipe
is a private function. See docs/methods.md, "Phase 1".
"""
from __future__ import annotations

from contextlib import contextmanager

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from cityseer.metrics import networks
from cityseer.tools import graphs
from cityseer.tools import io as cs_io
from pyproj import CRS
from pyrosm import OSM
from shapely.geometry import LineString

DISTANCES = [400, 800, 1200, 2000]

# Removed, as in cityseer's default Overpass query: separately mapped sidewalks
# (they duplicate the street centre line), areas, indoor ways, deep levels.
EXCLUDED_LEVELS = {"-2", "-3", "-4", "-5"}

# Areas cityseer's recipe fetches from Overpass, keyed by its own tag queries.
AREA_FILTERS = {
    "parks": {"landuse": ["cemetery", "forest"], "leisure": ["park", "garden", "sports_centre"]},
    "plazas": {"highway": ["pedestrian"]},
    "parking": {"amenity": ["parking"]},
}


# Highway values cityseer's default Overpass query excludes, plus motorways and
# busways (not walkable) and forestry/agricultural tracks: in the first citywide
# run, sparse straight track grids in the Grunewald, Spandau and Köpenick
# forests dominated the integration rankings.
EXCLUDED_HIGHWAYS = {
    "bus_guideway", "busway", "escape", "raceway", "proposed", "planned", "abandoned", "platform",
    "emergency_bay", "rest_area", "disused", "corridor", "ladder", "bus_stop", "elevator", "services",
    "motorway", "motorway_link", "construction", "track",
}

# Version of the way selection; part of the cache name so a change forces a rebuild.
WAY_SELECTION_VERSION = 2


def read_ways(osm: OSM, crs: str) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, dict]:
    """Street centre lines and paths for the segment map.

    Starts from all public ways, not pyrosm's walking network: the walking
    filter drops streets whose sidewalks are mapped separately (so the
    sidewalk represents the street), and the sidewalks themselves are removed
    here, which would delete those streets entirely.
    """
    nodes, edges = osm.get_network(
        network_type="all_public", nodes=True,
        extra_attributes=["area", "indoor", "level", "ref", "layer", "foot"],
    )
    stats = {"osm_segments": len(edges)}

    def col(name):
        return edges[name].astype("string").str.lower() if name in edges else pd.Series(pd.NA, index=edges.index)

    reasons = {
        "sidewalk": col("footway") == "sidewalk",
        "excluded_highway": col("highway").isin(EXCLUDED_HIGHWAYS),
        "foot_no": col("foot").isin({"no", "private"}),
        "area": col("area") == "yes",
        "indoor": col("indoor") == "yes",
        "deep_level": col("level").isin(EXCLUDED_LEVELS),
    }
    drop = pd.Series(False, index=edges.index)
    for k, m in reasons.items():
        m = m.fillna(False).astype(bool)
        stats[f"dropped_{k}"] = int((m & ~drop).sum())
        drop |= m
    edges = edges[~drop]
    return nodes.to_crs(crs), edges.to_crs(crs), stats


def build_primal(nodes: gpd.GeoDataFrame, edges: gpd.GeoDataFrame, crs: str) -> nx.MultiGraph:
    """cityseer primal graph with the edge attributes its OSM loader writes."""
    G = nx.MultiGraph()
    G.graph["crs"] = CRS(crs)
    xy = dict(zip(nodes["id"].astype(str), zip(nodes.geometry.x, nodes.geometry.y)))
    used = set(edges["u"].astype(str)) | set(edges["v"].astype(str))
    for k in used:
        if k in xy:
            G.add_node(k, x=float(xy[k][0]), y=float(xy[k][1]))

    def tag_list(v):
        return [str(v).lower()] if isinstance(v, str) and v else []

    for r in edges.itertuples(index=False):
        a, b = str(r.u), str(r.v)
        if a == b or a not in G or b not in G:
            continue
        geom = LineString([(G.nodes[a]["x"], G.nodes[a]["y"]), (G.nodes[b]["x"], G.nodes[b]["y"])])
        G.add_edge(
            a, b, geom=geom,
            names=tag_list(getattr(r, "name", None)),
            routes=tag_list(getattr(r, "ref", None)),
            highways=tag_list(getattr(r, "highway", None)),
            levels=[0],
            is_tunnel=isinstance(getattr(r, "tunnel", None), str),
            is_bridge=isinstance(getattr(r, "bridge", None), str),
        )
    return G


def local_areas(osm: OSM) -> dict[str, gpd.GeoDataFrame]:
    """Park, plaza and parking polygons from the PBF, shaped like osmnx features
    (index levels element/id) so cityseer's `_extract_gdf` accepts them."""
    out = {}
    for key, flt in AREA_FILTERS.items():
        g = osm.get_data_by_custom_criteria(custom_filter=flt, filter_type="keep", keep_nodes=False,
                                            keep_ways=True, keep_relations=True)
        if g is None or g.empty:
            g = gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs=4326)
            g.index = pd.MultiIndex.from_arrays([[], []], names=["element", "id"])
        else:
            g = g[g.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
            # OSM areas can be self-intersecting; cityseer unions them, which needs valid input.
            g["geometry"] = g.geometry.make_valid()
            g = g.explode(index_parts=False)
            g = g[g.geom_type == "Polygon"]
            g.index = pd.MultiIndex.from_arrays([g["osm_type"].astype(str), g["id"]], names=["element", "id"])
            g = g[["geometry"]]
        out[key] = g
    return out


@contextmanager
def _areas_from(areas: dict[str, gpd.GeoDataFrame]):
    """Route cityseer's Overpass area queries to the local polygons."""
    original = cs_io.ox.features_from_polygon

    def fake(_poly, tags):
        if "amenity" in tags:
            return areas["parking"]
        if "highway" in tags:
            return areas["plazas"]
        return areas["parks"]

    cs_io.ox.features_from_polygon = fake
    try:
        yield
    finally:
        cs_io.ox.features_from_polygon = original


def clean(G: nx.MultiGraph, areas: dict, area_wgs, crs_epsg: int) -> nx.MultiGraph:
    G = graphs.nx_remove_filler_nodes(G)
    with _areas_from(areas):
        G = cs_io._auto_clean_network(G, area_wgs, crs_epsg, final_clean_distances=(4, 8), remove_disconnected=100)
    return G


def mark_live(G: nx.MultiGraph, study_area) -> nx.MultiGraph:
    from shapely import contains_xy

    keys = list(G.nodes)
    xs = np.array([G.nodes[k]["x"] for k in keys])
    ys = np.array([G.nodes[k]["y"] for k in keys])
    inside = contains_xy(study_area, xs, ys)
    for k, live in zip(keys, inside):
        G.nodes[k]["live"] = bool(live)
    return G


def segment_names(G_primal: nx.MultiGraph, nodes_gdf: gpd.GeoDataFrame) -> pd.Series:
    def name(row):
        try:
            d = G_primal[row.primal_edge_node_a][row.primal_edge_node_b][row.primal_edge_idx]
        except KeyError:
            return None
        n = d.get("names") or []
        return "; ".join(sorted(set(n))) or None

    return nodes_gdf.apply(name, axis=1)


def centralities(G_dual: nx.MultiGraph, distances=DISTANCES) -> gpd.GeoDataFrame:
    """Angular (simplest-path) and metric (shortest-path) centralities per segment,
    plus NAIN and NACH (Hillier, Yang and Turner 2012)."""
    nodes_gdf, _edges_gdf, ns = cs_io.network_structure_from_nx(G_dual)
    # c is the angular change in degrees; c / 90 is angular depth with a
    # 90-degree turn = 1, the Depthmap / Hillier convention. td = total depth.
    nodes_gdf = networks.centrality_simplest(
        ns, nodes_gdf, distances=distances,
        closeness={"density": "1", "farness": "1 + c / 90", "harmonic": "1 / (1 + c / 90)", "td": "c / 90"},
        betweenness={"betweenness": "1"},
        postprocess={},
    )
    # Segment-length-weighted angular choice: each route counts with origin
    # length x destination length, so many short segments (path fragments)
    # do not outweigh long streets. Computed on a copy because cityseer would
    # otherwise overwrite the unweighted columns of the same name.
    weighted = networks.centrality_simplest(
        ns, nodes_gdf[["ns_node_idx", "x", "y", "live", "weight", "primal_edge"]].copy(), distances=distances,
        closeness={}, betweenness={"betweenness": "1"}, postprocess={}, segment_weighted=True,
    )
    for d in distances:
        nodes_gdf[f"cc_betweenness_{d}_ang_lw"] = weighted[f"cc_betweenness_{d}_ang"]
    nodes_gdf = networks.centrality_shortest(
        ns, nodes_gdf, distances=distances,
        closeness={"density": "1", "farness": "c", "harmonic": "1 / c"},
        betweenness={"betweenness": "1"},
        postprocess={},
    )
    for d in distances:
        # cityseer's density excludes the origin segment; Depthmap's node count
        # includes it, hence + 1 (negligible at these radii).
        nc = nodes_gdf[f"cc_density_{d}_ang"] + 1
        td = nodes_gdf[f"cc_td_{d}_ang"]
        ch = nodes_gdf[f"cc_betweenness_{d}_ang"]
        nodes_gdf[f"nain_{d}"] = nc**1.2 / (td + 2)
        nodes_gdf[f"nach_{d}"] = np.log(ch + 1) / np.log(td + 3)
    return nodes_gdf


def residential_frontage(segments: gpd.GeoDataFrame, buildings: gpd.GeoDataFrame, buffer_m: float) -> pd.DataFrame:
    """Residential buildings and residents within `buffer_m` of each segment.

    `buildings` are building points with a `residents` column (Phase 0
    allocation); only buildings with residents count. A segment with at least
    one such building nearby is a residential street.
    """
    homes = buildings[buildings["residents"] > 0][["residents", "geometry"]].to_crs(segments.crs)
    zones = gpd.GeoDataFrame({"seg": segments.index.to_numpy()},
                             geometry=segments.geometry.buffer(buffer_m).to_numpy(), crs=segments.crs)
    hits = gpd.sjoin(homes, zones, predicate="within", how="inner")
    agg = hits.groupby("seg").agg(res_buildings=("residents", "size"), residents_nearby=("residents", "sum"))
    out = pd.DataFrame(index=segments.index).join(agg).fillna(0)
    out["res_buildings"] = out["res_buildings"].astype(int)
    out["residential"] = out["res_buildings"] > 0
    return out
