"""Phase 2: inputs for the Place Syntax Tool (PST) and a Python cross-check.

PST (QGIS plugin, v3.3.2 read from github.com/SMoG-Chalmers/PST) builds its
graph from "Axial/Segment lines", connects every origin and destination point
to the closest line and counts that connection in the distance. The
cross-check here follows the same rules on the same segment lines, for
walking distance:

- attraction reach: number of destinations (weighted by a 0/1 column) within
  a walking-distance radius of each origin;
- attraction distance: walking distance to the nearest destination.

Destinations are stations, not GTFS stop points: VBB stop points are single
platforms or poles, so one station would otherwise count several times.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.csgraph import dijkstra
from shapely import STRtree, line_locate_point

# Short column names: PST lets the user name outputs with 2 characters and
# appends radius info; keep source columns short as well.
MODE_COLS = {"S-Bahn": "sb", "U-Bahn": "ub", "Tram": "tr", "Bus": "bu", "Regionalbahn": "rb"}


def station_key(stop_id: str) -> str:
    """IFOPT stop place: the first three parts of the stop id
    (de:11000:900007104::2 -> de:11000:900007104)."""
    return ":".join(str(stop_id).split(":")[:3])


def stations(stop_modes: pd.DataFrame, departures: pd.DataFrame | None, min_departures: float) -> pd.DataFrame:
    """One row per station with 0/1 columns per mode (`sb`, `ub`, ...), `su`
    (S- or U-Bahn), frequent flags (`<mode>f`, `anyf`) and a lon/lat at the mean
    of its served stop points."""
    sm = stop_modes.copy()
    sm["station_id"] = sm["stop_id"].map(station_key)
    if departures is not None and len(departures):
        sm = sm.merge(departures, on=["stop_id", "mode"], how="left").fillna({"departures": 0})
    else:
        sm["departures"] = 0
    pos = sm.drop_duplicates("stop_id").groupby("station_id").agg(
        name=("stop_name", "first"), stop_lon=("stop_lon", "mean"), stop_lat=("stop_lat", "mean"),
        stop_points=("stop_id", "nunique"))
    flags = pd.DataFrame(index=pos.index)
    for mode, c in MODE_COLS.items():
        m = sm[sm["mode"] == mode]
        flags[c] = flags.index.isin(m["station_id"]).astype(int)
        frequent = m[m["departures"] >= min_departures]["station_id"]
        flags[c + "f"] = flags.index.isin(frequent).astype(int)
    flags["su"] = ((flags["sb"] + flags["ub"]) > 0).astype(int)
    flags["anyf"] = (flags[[c + "f" for c in MODE_COLS.values()]].sum(axis=1) > 0).astype(int)
    return pos.join(flags).reset_index()


class SegmentGraph:
    """Undirected graph of segment lines joined at shared end points (as PST does)."""

    def __init__(self, lines: gpd.GeoDataFrame, precision: float = 0.01):
        self.lines = lines.reset_index(drop=True)
        coords = np.array([[ln.coords[0][:2], ln.coords[-1][:2]] for ln in self.lines.geometry])
        keys = np.round(coords.reshape(-1, 2) / precision).astype(np.int64)
        _, inv = np.unique(keys, axis=0, return_inverse=True)
        self.ends = inv.reshape(-1, 2)  # node index of each line's start and end
        self.length = self.lines.geometry.length.to_numpy()
        n = int(inv.max()) + 1
        a, b, w = self.ends[:, 0], self.ends[:, 1], np.maximum(self.length, 0.01)
        keep = a != b
        # parallel lines between the same nodes: keep the shortest
        self.adj = _min_duplicates(a[keep], b[keep], w[keep], n)
        self.n = n
        self.tree = STRtree(self.lines.geometry.to_numpy())

    def attach(self, points: gpd.GeoSeries) -> pd.DataFrame:
        """Closest line per point, connection length and distances along the
        line to its start and end node."""
        idx = self.tree.nearest(points.to_numpy())
        geoms = self.lines.geometry.to_numpy()[idx]
        along = line_locate_point(geoms, points.to_numpy())
        conn = points.distance(gpd.GeoSeries(geoms, index=points.index, crs=points.crs), align=False).to_numpy()
        return pd.DataFrame({"line": idx, "conn": conn, "to_start": along, "to_end": self.length[idx] - along},
                            index=points.index)


def _min_duplicates(a, b, w, n) -> sparse.csr_matrix:
    df = pd.DataFrame({"a": np.minimum(a, b), "b": np.maximum(a, b), "w": w}).groupby(["a", "b"], as_index=False)["w"].min()
    return sparse.coo_matrix(
        (np.r_[df["w"], df["w"]], (np.r_[df["a"], df["b"]], np.r_[df["b"], df["a"]])), shape=(n, n)
    ).tocsr()


def walking_distances(g: SegmentGraph, origins: pd.DataFrame, dests: pd.DataFrame, limit: float) -> np.ndarray:
    """Walking distance (m) from every origin to every destination, both given
    as `attach()` tables; np.inf beyond `limit`. Includes both connections."""
    d_start = g.ends[dests["line"].to_numpy(), 0]
    d_end = g.ends[dests["line"].to_numpy(), 1]
    sources = np.unique(np.r_[d_start, d_end])
    D = dijkstra(g.adj, directed=False, indices=sources, limit=limit).astype(np.float32)
    row = {s: i for i, s in enumerate(sources)}
    # destination -> node distances, via its line's start or end
    ds = D[[row[s] for s in d_start]] + dests["to_start"].to_numpy(np.float32)[:, None]
    de = D[[row[s] for s in d_end]] + dests["to_end"].to_numpy(np.float32)[:, None]
    dest_node = np.minimum(ds, de)  # (n_dest, n_nodes)
    o_line = origins["line"].to_numpy()
    o_start, o_end = g.ends[o_line, 0], g.ends[o_line, 1]
    out = np.minimum(dest_node[:, o_start] + origins["to_start"].to_numpy(np.float32),
                     dest_node[:, o_end] + origins["to_end"].to_numpy(np.float32)).T  # (n_orig, n_dest)
    # same line: walk directly along it
    same = o_line[:, None] == dests["line"].to_numpy()[None, :]
    if same.any():
        direct = np.abs(origins["to_start"].to_numpy(np.float32)[:, None] - dests["to_start"].to_numpy(np.float32)[None, :])
        out = np.where(same, np.minimum(out, direct), out)
    out += origins["conn"].to_numpy(np.float32)[:, None] + dests["conn"].to_numpy(np.float32)[None, :]
    out[out > limit] = np.inf
    return out


def reach_and_distance(dist: np.ndarray, dests: pd.DataFrame, columns: list[str], radii: list[int]) -> pd.DataFrame:
    """Attraction reach (count of destinations with column == 1 within each
    radius) and attraction distance (nearest such destination) per origin."""
    out = {}
    for c in columns:
        w = dests[c].to_numpy() > 0
        d = dist[:, w]
        for r in radii:
            out[f"reach_{c}_{r}"] = (d <= r).sum(axis=1)
        out[f"dist_{c}"] = d.min(axis=1) if d.shape[1] else np.full(dist.shape[0], np.inf)
    return pd.DataFrame(out)


def unlink_points(lines: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Points where two segment lines cross without sharing an end point
    (bridges, tunnels). In this segment map such lines are not connected; PST
    can be told the same with an unlink layer."""
    geoms = lines.geometry.to_numpy()
    tree = STRtree(geoms)
    left, right = tree.query(geoms, predicate="crosses")
    keep = left < right
    pts = []
    for i, j in zip(left[keep], right[keep]):
        inter = geoms[i].intersection(geoms[j])
        for p in getattr(inter, "geoms", [inter]):
            if p.geom_type == "Point":
                pts.append(p)
    return gpd.GeoDataFrame({"unlink_id": np.arange(len(pts))}, geometry=pts, crs=lines.crs)
