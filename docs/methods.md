# Methods and decisions

This file records every methodological choice in the walk-to-transit pipeline
and why it was made. Parameter values live in `config.yaml`; this file explains
them. Numbers quoted here come from files in `output/`.

## Data

| Input | Source | Licence | Version |
|---|---|---|---|
| Walk network, buildings | OpenStreetMap, Geofabrik Berlin extract | ODbL 1.0 | recorded in `output/run_metadata.json` (`downloads.pbf`) |
| Stops, routes | VBB GTFS feed | see VBB open data terms (CC BY 4.0 at the time of writing; verify on download) | `output/run_metadata.json` (`gtfs_feed`: feed_info / calendar validity) |
| District boundaries | Berlin Open Data, `data/bezirksgrenzen.geojson` | dl-de/by-2-0 (verify) | in repo |

**Feed date: not yet recorded.** The full Berlin run has not been executed in
the environment where this pipeline was written (the data hosts were not
reachable). The first run writes the GTFS validity window to
`output/run_metadata.json`; copy it here.

## Pipeline

1. **Districts.** `spatial_alias` is the district name. Reprojected to
   EPSG:32633 (UTM 33N) so distances are in metres with negligible distortion
   over Berlin.
2. **Walk network.** `pyrosm.OSM.get_network(network_type="walking", nodes=True)`,
   one row per segment between consecutive OSM nodes. Segment length is the
   projected length in EPSG:32633.
   - **Undirected.** Every segment is walkable both ways. See "Bug: directed
     walk graph" below.
   - Parallel segments between the same two nodes keep the shortest length.
   - Only the largest connected component is kept; nodes outside it are
     counted in `run_metadata.json` (`network.nodes_outside_largest_component`).
3. **Buildings.** Every OSM building polygon becomes one representative point
   (`representative_point`, guaranteed to lie inside the polygon). A building
   belongs to the district that contains its point. Points are snapped to the
   nearest network node. Buildings more than `max_building_snap_m` (250 m)
   from the network are excluded and counted. Buildings are not weighted by
   floor area or residents; a garage counts like an apartment block. This is a
   known limitation.
4. **Stops and modes.** A stop has a mode if at least one trip of that mode
   serves it (stop_times -> trips -> routes). A stop can have several modes.
   Mode comes from `route_type`:

   | route_type | mode |
   |---|---|
   | 109 | S-Bahn |
   | 1, 400, 401 | U-Bahn |
   | 0, 900 | Tram |
   | 2, 100, 106 | Regionalbahn |
   | 3, 700-799 | Bus |
   | 1000 | excluded (ferry) |

   Names are used only for route types missing from this table, and only for
   `S<digit>`, `U<digit>`, `RE<digit>`, `RB<digit>`. `M` lines are not
   inferred from the name because Berlin has both MetroTram and MetroBus.
   A 700-series route is always a bus, so rail-replacement buses named U2,
   U5 etc. stay buses. The check per route type (route counts, sample names,
   share of names matching the mode) is written to
   `output/gtfs_route_type_check.csv` on every run.
5. **Stop buffer.** Stops up to `stop_buffer_m` (1 km) outside the city
   boundary are kept, so buildings near the edge can use a stop just across
   it. **Caveat:** the Geofabrik Berlin extract ends roughly at the city
   boundary, so the walk network outside Berlin is truncated. Stops beyond
   the network are snapped to its edge; any stop more than
   `max_stop_snap_m` (250 m) from a network node is dropped. The counts per
   mode (inside Berlin, buffer zone, dropped) are in `output/stops_by_mode.csv`.
   A complete edge treatment needs the Brandenburg extract clipped to a
   buffer; not done yet.
6. **Distances.** For each mode, one multi-source Dijkstra
   (`scipy.sparse.csgraph.dijkstra`) from a virtual source linked to every
   stop node of that mode. The link weight is the stop's snap distance, and
   each building's snap distance is added at the end, so both access legs
   count. Result: network distance in metres from each building to the
   nearest stop of each mode.
7. **Walking speed.** Time = distance / speed. Main run 1.3 m/s; sensitivity
   at 1.0 and 1.4 m/s. 1.3 m/s is close to commonly reported mean free
   walking speeds of adults; 1.0 m/s approximates slower walkers (older
   adults, children); 1.4 m/s is a common planning value. Because time is a
   linear function of distance, the speed does not change which stop is
   nearest, only the scale.
8. **Aggregation.** Per district, mode and speed: median, 25th and 75th
   percentile, mean, and the share of buildings more than 15 and 30 min away.
   **No building is dropped for being far away.** The v0 notebook discarded
   walks of 30 min or more before taking the median, which biased medians
   down and hid where coverage is poor. A city-wide "Berlin" row is included.
9. **Outputs.**
   - `output/walk_time_by_district.csv`: long table, all statistics.
   - `output/median_walk_min_<speed>mps.csv`: wide median table per speed.
   - `output/stops_by_mode.csv`, `output/gtfs_route_type_check.csv`.
   - `output/run_metadata.json`: inputs, counts, feed validity, config.
   - `data/derived/building_walk_dist.parquet`: per building distances
     (git-ignored), input for Phase 3.
   - README results are generated by `scripts/build_readme_tables.py`.

## Bug: directed walk graph (found during Phase 0)

pyrosm lists each segment once, in OSM drawing direction. The v0 notebook
passed these rows to `osmnx.graph_from_gdfs`, which builds a `MultiDiGraph`,
so walking was only possible along the drawing direction of each way. Its
connected-component step used `to_undirected()`, which hid the problem.

`scripts/check_directionality.py` measures the effect on pyrosm's bundled
Helsinki sample (10 random sources, seed 0), see
`output/directionality_check_Helsinki.csv`: only 0.03% of segment pairs are
listed in both directions; 20.9% of nodes are unreachable on the directed
graph, and 94.3% of the reachable nodes get a longer shortest path (median
201.5 m longer). The size of the effect on Berlin is unknown until the script
is run with `--pbf data/raw/berlin-latest.osm.pbf`. Expect the v0 walk times
to be too long and partly missing for this reason alone.

## Other differences from v0

- Median instead of the mean in the first v0 table (v0 had both; the saved
  CSV used the median).
- Buildings were clipped to districts as polygons in v0; now one point per
  building, assigned by location.
- Stops were clipped at the boundary in v0; now a 1 km buffer (see caveat).
- Stop and building snap distances now count towards the walk.

## Open questions

- Weighting buildings by residents or floor area (needs a population or
  building-use source).
- Whether to analyse platform-level GTFS stops (current) or station
  entrances from OSM. Platform coordinates of deep U-Bahn stations can be
  far from street-level entrances, so U-Bahn walk times are approximate.
