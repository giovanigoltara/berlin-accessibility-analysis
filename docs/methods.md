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
   any mode. "S- or U-Bahn" leaves out the Regionalbahn on purpose: its
   frequency is far lower. "Any mode" includes all five; it is meaningful
   mainly in the frequent-stops scenario, because some bus stop is close to
   almost everyone.
8b. **Older residents.** Table T2 gives residents aged 65+ per
   Planungsraum. Their location within a Planungsraum is unknown, so each
   building gets the Planungsraum's 65+ share of its residents. Results are
   reported with `weighting = residents_65plus`; the README and map use
   1.0 m/s, a common value for older adults' comfortable walking pace. A
   consequence: per Planungsraum, the 65+ median at 1.0 m/s equals the
   all-resident median at 1.0 m/s. Differences appear only when aggregating
   to Bezirksregion, district or Berlin, where they reflect where older people
   live. The map therefore pairs the median with the *number* of older
   residents beyond 15 min, drawn as proportional circles.
8c. **Frequent stops (frequency cap).** A stop of a mode counts in this
   scenario if it has at least `window / max_headway_min` departures of that
   mode in the window (12 departures in 07:00-09:00 for a 10-min headway).
   Departures come from `stop_times.txt` for trips whose service runs on the
   reference date (calendar.txt weekday pattern plus calendar_dates.txt
   exceptions). Reference date: Tuesday 10 November 2026, a school-term
   weekday; the October Tuesdays in the school holidays had about 6% fewer
   trips. Departures are counted per GTFS stop point, usually one direction
   of one platform or kerbside pole, summed over all lines of the mode. This
   is a service-level filter, not a timetable-based travel time.
   Counts per mode are in `output/stops_frequency_by_mode.csv`; results in
   `output/walk_time_by_*_frequent_10min.csv`.
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

# Phase 1: angular segment analysis (Space Syntax)

Script: `scripts/run_segments.py`, module `src/berlin_access/segments.py`.
Pilot: Friedrichshain-Kreuzberg. cityseer 5.8.0 (pinned; the cleaning recipe
used is a private function and may change between versions).

## Segment map

1. **Ways.** All public OSM ways (pyrosm `all_public`) for the district plus
   a 2 km buffer, then removed: separately mapped sidewalks
   (`footway=sidewalk`, they duplicate the street centre line), motorways and
   the non-walkable types cityseer's default query excludes, ways with
   `foot=no/private`, areas, indoor ways, levels -2 to -5. Counts per reason
   in `output/segments_<district>_metadata.json`.
   *Why not pyrosm's walking network:* it leaves out every street whose
   sidewalks are mapped separately (`sidewalk=separate`), so that the
   sidewalk stands in for the street. Removing sidewalks from that network
   deletes those streets altogether. In the first pilot run this cut the
   Friedrichshain-Kreuzberg network to a fraction of its streets, which is
   how the problem was found. The Phase 0 walk times are unaffected: they
   route along the sidewalks, which is right for walking distance.
2. **Primal graph.** One edge per OSM segment, with the attributes cityseer's
   OSM loader writes (names, ref, highway class, tunnel/bridge), so the
   class-aware cleaning steps work.
3. **Cleaning.** cityseer's own OSM recipe (`io._auto_clean_network`, used by
   `io.osm_graph_from_poly`), unchanged, with its default final clean
   distances (4, 8 m). In order:
   - deduplicate overlapping edges (20 m, 20°);
   - remove footways inside parks, cemeteries and forests, and service roads
     in parks and parking areas (these areas come from the local PBF instead
     of the Overpass API; everything else is cityseer's code);
   - remove components with fewer than 100 nodes;
   - **merge parallel carriageways** into one centre line, by road class:
     trunk 40 m, primary 32 m, secondary 28 m, tertiary 24 m;
   - consolidate complex intersections into one node, by road class (32, 28,
     24, 20 m);
   - snap gapped path endings (20 m) and link dead ends to nearby roads;
   - **remove dangling slivers** (despine 40 m, then 25 m);
   - small-scale cleaning of paths and minor streets (4 m, 8 m), merge
     parallel edges by midline, straighten kinks, drop short self-loops.
   The result approximates a segment (road-centre-line) map, which is what
   angular segment analysis assumes.
4. **Dual graph.** `graphs.nx_to_dual`: each street segment becomes a node,
   adjacency between segments becomes an edge, the turn angle between them is
   the angular cost.

## Scaling to all districts: one citywide run

All 12 districts are analysed as **one network** (Berlin + 2 km buffer)
rather than 12 district runs. With a 2 km buffer a segment's values should
not depend on which run computed it, but separate runs would clean the
network 12 times (slightly differently where buffers overlap) and compute
border streets twice. Each live segment is assigned to the district that
contains its midpoint (nearest district for the few whose midpoint lies just
outside the city). Ranks, percentiles and top-10 lists are computed within
each district. The Friedrichshain-Kreuzberg pilot (district + 2 km) is kept
and compared segment by segment with the citywide run
(`scripts/compare_segment_runs.py`), which tests whether 2 km of buffer is
enough.

## Edge effects

The network includes everything within 2 km of the district (the largest
radius). Segments are `live` only if one of their end nodes lies inside the
district; non-live segments carry paths but get no results and are drawn
gray on the maps. Results are reported only for live segments.

## Measures (radii 400, 800, 1200, 2000 m, metric radius along the path)

- **Angular (simplest path)**, `centrality_simplest`: the cost `c` is the
  angular change in degrees; angular depth = `c / 90`, i.e. a 90° turn = 1,
  the Depthmap / Hillier convention (verified on a synthetic L-shaped graph:
  one 90° turn gives depth 1).
  - integration: harmonic closeness `1 / (1 + c/90)` (`cc_harmonic_<r>_ang`),
    farness `1 + c/90`, and total angular depth TD = sum of `c/90`
    (`cc_td_<r>_ang`);
  - choice: angular betweenness (`cc_betweenness_<r>_ang`); each unordered
    pair of segments counted once, origin and destination excluded
    (verified on a 3-segment chain).
- **Metric (shortest path)**, `centrality_shortest`, for contrast: harmonic
  closeness `1/c` with c in metres, farness, betweenness (`cc_*_<r>`, no
  `_ang` suffix).
- **NAIN and NACH** (Hillier, Yang and Turner 2012):
  NAIN = NC^1.2 / (TD + 2), NACH = log(CH + 1) / log(TD + 3), with NC = node
  count (cityseer's density, which excludes the origin, + 1 to include it as
  Depthmap does), TD = total angular depth, CH = angular choice. Differences
  from Depthmap: choice counts each pair once; cityseer's segment graph
  comes from its cleaning, not from a hand-drawn axial or segment map.

## Outputs

- `output/segments_<district>.gpkg`: every segment, all measures, `live` flag,
  street name (git-ignored because of size; regenerate with the script).
- `output/segments_<district>_summary.csv`: distribution of each measure over
  live segments.
- `output/segments_<district>_top10.csv`: top 10 segments by NACH, choice and
  NAIN per radius, for the sanity check against known main streets.
- `output/maps/segments_<district>_nach_{800,2000}.png`: NACH in quintile
  classes (darker and thicker = higher). Quintiles, not fixed breaks,
  because NACH is a relative measure; same validated blue ramp as the
  Phase 0 maps.

## Pilot results and sanity check (Friedrichshain-Kreuzberg)

From `output/segments_friedrichshain-kreuzberg_metadata.json`: 253,181 OSM
segments read for the district plus 2 km; after removals and cleaning the
segment map has 21,342 segments, 4,900 of them in the district (live).

`output/segments_friedrichshain-kreuzberg_main_streets.csv` gives the median
percentile of known main streets among all district segments. The list:
Frankfurter Allee, Kottbusser Damm and Oranienstraße from the project brief;
Karl-Marx-Allee, Warschauer, Skalitzer, Gneisenau-, Yorckstraße and
Mehringdamm named before the first run; Petersburger, Boxhagener and Revaler
Straße added after it (so they are weaker evidence). At 2000 m their median
NACH percentile is between 69 (Skalitzer Straße) and 97 (Karl-Marx-Allee).
At 800 m the ranks are lower, as expected for a local radius.

**NACH artifact.** At 2000 m the highest NACH values are on the Stralau
peninsula: Tunnelstraße ranks first on NACH at 800, 1200 and 2000 m but is in
none of the angular-choice top 10 lists at those radii
(`output/segments_friedrichshain-kreuzberg_top10.csv`). NACH =
log(CH+1) / log(TD+3) rises when total depth TD is small, so a street that
every route into a small, enclosed network must use scores high. Hillier et
al. introduced NACH to compare whole cities; within one district, angular
choice and NAIN are the more robust readings. Kept as computed, flagged here.

## Citywide results and checks

From `output/segments_berlin_metadata.json` and
`output/segments_berlin_by_district.csv`: 1,638,835 OSM segments read for
Berlin + 2 km; 185,185 segments after cleaning, of which those inside Berlin
are reported per district.

**Edge effects.** `output/segments_friedrichshain-kreuzberg_vs_berlin.csv`:
94.6% of the pilot's segments match a citywide segment (midpoint and length
within 1 m). Over all measures and radii, Spearman rank correlation is
between 0.991 and 0.9997 and the median relative difference at most 3.2%.
The 2 km buffer is sufficient; the residual differences come from cleaning
two slightly different networks.

**Known problem: forest tracks.** In several outer districts the top NAIN
streets (`output/segments_berlin_top10.csv`) are forest rides and tracks,
e.g. Teltower Weg and E-Gestell (Charlottenburg-Wilmersdorf), Birkengestell
(Treptow-Köpenick), Oberjägerweg (Spandau). cityseer's recipe removes
footways inside parks and forests but keeps `highway=track` and similar
ways. What remains in a forest is a sparse, straight grid with low angular
depth, which raises integration. This is a property of the input network,
not of the measures. Not yet fixed; options under consideration: remove
`highway=track` from the segment map, and/or keep forest segments in the
network but exclude them from reporting.
