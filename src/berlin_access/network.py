"""Pedestrian network as an undirected sparse graph.

pyrosm's `get_network(nodes=True)` returns every way segment once, in OSM
digitisation direction. Building an osmnx MultiDiGraph from those rows (as the
earlier notebook did) makes walking one-way along the drawing direction of each
way. Here every segment is walkable in both directions.
"""
from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
from pyrosm import OSM
from scipy import sparse
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree


@dataclass
class WalkNetwork:
    node_ids: np.ndarray  # OSM node id per graph index
    xy: np.ndarray  # (n, 2) projected coordinates
    adj: sparse.csr_matrix  # symmetric, edge weight = length in metres
    crs: str

    @property
    def n(self) -> int:
        return len(self.node_ids)


def load_walk_edges(osm: OSM, crs: str) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    nodes, edges = osm.get_network(network_type="walking", nodes=True)
    nodes = nodes[["id", "geometry"]].to_crs(crs)
    edges = edges[["u", "v", "highway", "geometry"]].to_crs(crs)
    return nodes, edges


def build_network(nodes: gpd.GeoDataFrame, edges: gpd.GeoDataFrame, crs: str) -> tuple[WalkNetwork, dict]:
    """Undirected graph restricted to its largest connected component."""
    stats = {"osm_nodes": len(nodes), "osm_edges": len(edges)}
    xy_all = np.column_stack([nodes.geometry.x.to_numpy(), nodes.geometry.y.to_numpy()])
    ok = np.isfinite(xy_all).all(axis=1)
    nodes_ok = nodes.loc[ok]
    idx = pd.Series(np.arange(len(nodes_ok)), index=nodes_ok["id"].to_numpy())

    e = pd.DataFrame(
        {
            "a": edges["u"].map(idx),
            "b": edges["v"].map(idx),
            "w": edges.geometry.length.to_numpy(),  # projected length in metres
        }
    ).dropna()
    e = e[e["a"] != e["b"]].astype({"a": np.int64, "b": np.int64})
    # Parallel ways between the same pair of nodes: keep the shortest. Without
    # this, sparse matrix construction would sum duplicate entries.
    lo = np.minimum(e["a"], e["b"])
    hi = np.maximum(e["a"], e["b"])
    e = pd.DataFrame({"a": lo, "b": hi, "w": e["w"]}).groupby(["a", "b"], as_index=False)["w"].min()
    e["w"] = e["w"].clip(lower=0.01)  # explicit zeros would be dropped by scipy

    n = len(nodes_ok)
    adj = sparse.coo_matrix(
        (np.r_[e["w"], e["w"]], (np.r_[e["a"], e["b"]], np.r_[e["b"], e["a"]])), shape=(n, n)
    ).tocsr()

    _, labels = connected_components(adj, directed=False)
    largest = np.bincount(labels).argmax()
    keep = np.flatnonzero(labels == largest)
    adj = adj[keep][:, keep].tocsr()
    xy = xy_all[ok][keep]
    node_ids = nodes_ok["id"].to_numpy()[keep]

    stats.update(
        graph_nodes=int(len(keep)),
        graph_edges=int(adj.nnz // 2),
        nodes_outside_largest_component=int(n - len(keep)),
        graph_total_length_km=round(float(adj.sum() / 2 / 1000), 1),
    )
    return WalkNetwork(node_ids=node_ids, xy=xy, adj=adj, crs=crs), stats


def snap(net: WalkNetwork, points: gpd.GeoSeries) -> tuple[np.ndarray, np.ndarray]:
    """Nearest graph node index and straight-line snap distance (m) per point."""
    tree = cKDTree(net.xy)
    pxy = np.column_stack([points.x.to_numpy(), points.y.to_numpy()])
    dist, ii = tree.query(pxy, k=1)
    return ii, dist


def multi_source_distance(net: WalkNetwork, source_idx: np.ndarray, source_offset_m: np.ndarray) -> np.ndarray:
    """Network distance (m) from every node to the nearest source.

    A virtual super-source is linked to every source node with a one-way edge
    whose weight is that source's snap distance, so the access leg from the
    stop to the network counts towards the walk.
    """
    if len(source_idx) == 0:
        return np.full(net.n, np.inf)
    # Same node reached by several stops: keep the smallest offset.
    s = pd.DataFrame({"i": source_idx, "w": source_offset_m}).groupby("i")["w"].min()
    n = net.n
    super_row = sparse.csr_matrix(
        (np.maximum(s.to_numpy(), 0.01), (np.zeros(len(s), dtype=np.int64), s.index.to_numpy())), shape=(1, n + 1)
    )
    adj = sparse.vstack(
        [sparse.hstack([net.adj, sparse.csr_matrix((n, 1))]), super_row], format="csr"
    )
    d = dijkstra(adj, directed=True, indices=n)
    return d[:n]
