# Methods and decisions

This file records every methodological choice in the walk-to-transit pipeline
and why it was made. Parameter values live in `config.yaml`; this file explains
them. Numbers quoted here come from files in `output/`.

## Data

| Input | Source | Licence | Version |
|---|---|---|---|
| Walk network, buildings | OpenStreetMap, BBBike Berlin extract (bbox 12.76-13.98 E, 52.23-52.82 N) | ODbL 1.0 | recorded in `output/run_metadata.json` (`downloads.pbf`) |
| Stops, routes | VBB GTFS feed | see VBB open data terms (CC BY 4.0 at the time of writing; verify on download) | `output/run_metadata.json` (`gtfs_feed`: feed_info / calendar validity) |
| Reporting units | LOR 2021 Planungsräume (with Bezirksregion and district), Geoportal Berlin WFS `lor_2021` | dl-de/by-2-0 (verify) | layer field `stand`; download time in `run_metadata.json` |
| Residents | Einwohnerregisterstatistik 31.12.2025, Amt für Statistik Berlin-Brandenburg, Statistischer Bericht A I 16 hj 2/25, table T2 | CC BY (verify on download) | file name and download time in `run_metadata.json` |

**Data versions of the current results** (from `output/run_metadata.json`):
GTFS feed downloaded 2026-10-07 from `https://www.vbb.de/vbbgtfs`, service
calendar 2026-10-06 to 2026-12-12 (the feed has no `feed_info.txt`, so the
calendar window is the only version marker). OSM: BBBike Berlin extract,
server timestamp 2026-10-03, downloaded 2026-10-07. LOR Planungsräume and
the population report downloaded 2026-10-07. All files' sha256 are in the
metadata.

## Pipeline

1. **Reporting units.** One geometry source for all levels: the 542 LOR 2021
   Planungsräume. Each carries its Bezirksregion (143) and district (12), so
   a building is assigned to a Planungsraum by location and its Bezirksregion
   and district follow from the code. This guarantees the levels nest exactly.
   The city outline is the union of the Planungsräume. (The earlier district
   file `data/bezirksgrenzen.geojson` is no longer used; its outline differs
   from the LOR union by a few hundredths of a km².) Planungsräume are the
   closest official unit to a Kiez. Everything is projected to EPSG:32633
   (UTM 33N), metres.
2. **Walk network.** `pyrosm.OSM.get_network(network_type="walking", nodes=True)`,
   one row per segment between consecutive OSM nodes. Segment length is the
   projected length in EPSG:32633.
   - **Undirected.** Every segment is walkable both ways. See "Bug: directed
     walk graph" below.
   - Parallel segments between the same two nodes keep the shortest length.
   - Only the largest connected component is kept; nodes outside it are
     counted in `run_metadata.json` (`network.nodes_outside_largest_component`).
3. **Buildings.** Every OSM building polygon becomes one representative point
   (`representative_point`, guaranteed to lie inside the polygon), assigned to
   the Planungsraum that contains it, and snapped to the nearest network node.
   Buildings more than `max_building_snap_m` (250 m) from the network are
   excluded and counted.
3a. **Residents (dasymetric allocation).** Residents are known only per
   Planungsraum (register count, table T2). They are split among the
   buildings of the Planungsraum in proportion to estimated residential floor
   area:
   - A building is a residential candidate unless its OSM `building` tag is
     clearly non-residential (garage, shed, allotment house, office, school,
     industrial, ... full list in `population.NON_RESIDENTIAL`). For untyped
     `building=yes`, `building:use` decides where mapped. Candidates must
     have a footprint of at least `min_residential_footprint_m2` (40 m²),
     which removes most untagged sheds and garages.
   - Weight = footprint area x storeys (`building:levels`). Storeys are mapped
     for only part of the buildings, unevenly by district; missing values
     are filled with the median of known values in the same Planungsraum,
     then the city-wide median. Shares are in `run_metadata.json`
     (`residents`).
   - Residents of a Planungsraum with no candidate building cannot be placed;
     they are listed in `output/population_allocation_check.csv`.
   Known weaknesses: mixed-use buildings (shops below flats) count fully as
   residential; office buildings tagged `building=yes` without
   `building:use` get residents. Both shift residents within a Planungsraum,
   never between Planungsräume, because each Planungsraum's total is fixed.
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
5. **City limit.** Main run: only stops inside Berlin count
   (`stop_buffer_m: 0`), because the study is about the city as lived and
   governed, and comparisons between LOR units should not depend on
   Brandenburg's network. Sensitivity run: stops up to
   `stop_buffer_sensitivity_m` (1 km) outside Berlin also count; its results
   are in `output/*_stopbuffer_1000m.csv` and a README table. Allowing more
   stops can only shorten walks, so the main run gives the longer (more
   conservative) walk for units on the city edge. OSM data is still read for
   the city plus `network_buffer_m` (3 km), so a walk to a Berlin stop may
   use a path just outside the city, as people do. This is why the OSM source
   is the BBBike Berlin extract (bbox reaching well into Brandenburg) rather
   than Geofabrik's, which is cut at the boundary. Stops more than
   `max_stop_snap_m` (250 m) from a network node are dropped. Counts per mode
   are in `output/stops_by_mode.csv`.
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
8. **Aggregation.** For each reporting level (district, Bezirksregion,
   Planungsraum), mode and speed: median, 25th and 75th percentile, mean, and
   the share beyond 15 and 30 min, computed twice:
   - `weighting = residents` (main): each building counts with its allocated
     residents, i.e. statistics describe residents.
   - `weighting = buildings`: each building counts once, as in earlier
     versions, kept for comparison.
   **No building is dropped for being far away.** Units with fewer than
   `min_unit_residents` (100) residents are flagged `low_population`; their
   statistics rest on very few people and are excluded from the README
   summary of Planungsräume.
   A city-wide "Berlin" row is included at every level.
8a. **Combined modes.** `combined_modes` in `config.yaml` defines modes
   reported like the others, e.g. "S- or U-Bahn" = the walk to whichever of
   the two is nearer. The nearest stop of a union of stop sets is exactly the
   shorter of the per-mode distances, so it is computed per building as the
   minimum of the member distances (no extra routing), then aggregated like
   any mode. Regionalbahn is left out on purpose: its frequency is far lower
   and it would make the measure less comparable across the city.
9. **Comparing levels.** District, Bezirksregion and Planungsraum results come
   from the same per-building data, so differences between levels are purely
   due to aggregation. Part of any difference is the modifiable areal unit
   problem: results depend on the size and shape of the units. Compare units
   within one level; read differences between levels with that in mind.
10. **Outputs.**
   - `output/walk_time_by_{district,bezirksregion,planungsraum}.csv`: long
     tables, all statistics, both weightings, with `low_population` flag.
   - `output/walk_time_by_*_stopbuffer_1000m.csv`: city-limit sensitivity.
   - `output/median_walk_min_<speed>mps.csv`: wide district medians per resident.
   - `output/population_allocation_check.csv`: register vs allocated residents
     per Planungsraum.
   - `output/stops_by_mode.csv`, `output/gtfs_route_type_check.csv`.
   - `output/run_metadata.json`: inputs, counts, feed validity, config.
   - `data/derived/building_walk_dist.parquet`: per building distances and
     residents (git-ignored), input for Phase 3.
   - `data/derived/network.npz`, `buildings_base.parquet`: cache of the parsed
     network and buildings, keyed by input hashes (`base_key.json`).
   - README results are generated by `scripts/build_readme_tables.py`.

## Maps

`scripts/make_maps.py` draws the resident-weighted median walk per
Planungsraum (main speed, main city limit) for each mode.

- **One shared, classed scale** for all modes, so maps compare directly:
  5 or less, 5 to 10, 10 to 15, 15 to 30, more than 30 min. 15 min is the
  common "15-minute city" threshold; 30 min marks a walk few people make to
  reach a stop. Classes rather than a continuous scale because readers
  compare areas, not exact values, which are in the CSV.
- **Colours:** five steps of one blue hue, light = short walk. Five, not
  more, because six or more steps of one hue were too close in lightness to
  tell apart (checked with a palette validator: monotone lightness, minimum
  step gap, lightest step at least 2:1 against the background).
- Units with fewer than 100 residents are hatched gray, not coloured.
- District boundaries are drawn on top to orient the reader.
- Where a mode does not run (trams in the west), the darkest class means
  "no service nearby", not a measured everyday walk.

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
is run with `--pbf data/raw/Berlin.bbbike.osm.pbf`. Expect the v0 walk times
to be too long and partly missing for this reason alone.

## Other differences from v0

- Median instead of the mean in the first v0 table (v0 had both; the saved
  CSV used the median).
- Buildings were clipped to districts as polygons in v0; now one point per
  building, assigned by location.
- Districts are now taken from the LOR Planungsräume, not a separate district file.
- Stop and building snap distances now count towards the walk.

## Reading the results

- **Building counts versus residents.** Before resident weighting, district
  medians counted every OSM building once, so areas with many small
  buildings (detached houses, garages, allotment huts) outweighed dense
  blocks of flats. The README table "Effect of resident weighting" shows the
  difference per district; it is positive in almost every cell, i.e. the
  building count overstated walks.
- **The graph is not the cause of long walks.** `scripts/check_detour.py`
  writes `output/detour_check.csv`, comparing network distance with
  straight-line distance to the nearest stop (per building, unweighted, main
  run's stop set). Across Berlin the median network/straight-line ratio per
  mode is between 1.22 and 1.54, typical urban detour factors.
- **Neukölln and the S-Bahn.** Even per resident, Neukölln's S-Bahn median is
  long. In the detour check the median building is 2838 m in a straight line
  from the nearest S-Bahn stop but 976 m from the nearest U-Bahn stop: the
  Ring S-Bahn serves the dense north, the U7 the populous south
  (Britz, Gropiusstadt, Rudow). This is geography, not an error.
- **Modes absent from an area.** Where a unit has no stop of a mode (trams in
  the western districts, S-Bahn in Kladow), the value is the walk to the
  nearest stop elsewhere. It is a distance, not a meaningful service level,
  and it dominates means; use medians and shares.
- **Planungsräume without residents.** 03400831 Pankower Tor has no row in
  the population table and gets 0 residents. Units under 100 residents are
  flagged `low_population` (see `output/population_allocation_check.csv`).

## Open questions

- Age-specific accessibility: table T2 has residents by age group per
  Planungsraum. Combining the 65+ share with the 1.0 m/s speed would give a
  walk time for older residents at their own pace.
- Residential floor area from an authoritative source (ALKIS building
  storeys, or the Umweltatlas block-level population density) instead of OSM
  tags.
- Whether to analyse platform-level GTFS stops (current) or station
  entrances from OSM. Platform coordinates of deep U-Bahn stations can be
  far from street-level entrances, so U-Bahn walk times are approximate.
