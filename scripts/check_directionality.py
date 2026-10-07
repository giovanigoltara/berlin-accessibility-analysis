"""Show the effect of the v0 notebook's directed walk graph.

The v0 notebook built an osmnx MultiDiGraph from pyrosm edges, which are
listed once per segment in OSM drawing direction. This script compares
multi-source shortest paths on that directed graph with the undirected graph
used now. By default it uses pyrosm's bundled Helsinki sample so it runs
without any download; pass --pbf to run it on the Berlin extract.

Writes output/directionality_check_<name>.csv.
"""
import argparse
from pathlib import Path

import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from pyrosm import OSM, get_data

import _bootstrap  # noqa: F401

from berlin_access.config import load_config

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pbf", default=None)
    ap.add_argument("--n-sources", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    pbf = args.pbf or get_data("helsinki_pbf")
    name = Path(pbf).name.split(".")[0].replace("-latest", "")

    nodes, edges = OSM(pbf).get_network(network_type="walking", nodes=True)
    pairs = set(zip(edges["u"], edges["v"]))
    reverse_share = sum((v, u) in pairs for u, v in pairs) / len(pairs)

    nodes = nodes.set_index("id")
    nodes["x"], nodes["y"] = nodes.geometry.x, nodes.geometry.y
    edges["key"] = edges.groupby(["u", "v"]).cumcount()
    G = ox.graph_from_gdfs(nodes, edges.set_index(["u", "v", "key"]))  # as in v0
    G = G.subgraph(max(nx.weakly_connected_components(G), key=len)).copy()

    rng = np.random.default_rng(args.seed)
    sources = list(rng.choice(np.array(list(G.nodes)), args.n_sources, replace=False))

    def dist(H):
        H = H.copy()
        H.add_node(-1)
        for s in sources:
            H.add_edge(-1, s, length=0.0)
        d = nx.single_source_dijkstra_path_length(H, -1, weight="length")
        d.pop(-1)
        return d

    d_dir, d_und = dist(G), dist(G.to_undirected())
    common = np.array([k for k in d_dir])
    extra = np.array([d_dir[k] - d_und[k] for k in common])
    longer = extra > 1e-6
    res = pd.DataFrame([{
        "pbf": Path(pbf).name,
        "n_sources": args.n_sources,
        "seed": args.seed,
        "edge_pairs_with_reverse_listed": round(reverse_share, 4),
        "graph_nodes": G.number_of_nodes(),
        "reachable_directed": len(d_dir),
        "reachable_undirected": len(d_und),
        "share_unreachable_directed": round(1 - len(d_dir) / len(d_und), 4),
        "share_reachable_longer_directed": round(longer.mean(), 4),
        "median_extra_m_where_longer": round(float(np.median(extra[longer])), 1) if longer.any() else 0.0,
    }])
    out = load_config().path("output") / f"directionality_check_{name}.csv"
    res.to_csv(out, index=False)
    print(res.T.to_string(header=False))
    print(f"-> {out}")
