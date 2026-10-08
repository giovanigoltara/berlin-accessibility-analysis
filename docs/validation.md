# Validation

Checks of the method and what they showed. Every number comes from the file
named next to it. Method: [methods.md](methods.md); history: [decisions.md](decisions.md).

| # | Check | Result in one line |
|---|---|---|
| 1 | [GTFS mode mapping](#1-gtfs-mode-mapping) | Every route type matches its line names |
| 2 | [Directed walk graph in v0](#2-directed-walk-graph-in-v0) | v0 walks were one-way; large effect on a sample |
| 3 | [Network detours](#3-network-detours) | Detour factors 1.22-1.54, typical for cities |
| 4 | [Edge effects of the 2 km buffer](#4-edge-effects-of-the-2-km-buffer) | Pilot and citywide run agree (Spearman >= 0.9905) |
| 5 | [Reference streets](#5-reference-streets) | Main streets rank at the 76th-94th percentile on choice |
| 6 | [Segment-length weighting (Mitte)](#6-segment-length-weighting-mitte) | Helps at 800 m; does not change the 2000 m top list |
| 7 | [Place Syntax Tool against Python](#7-place-syntax-tool-against-python) | Identical reach and distance for all 9,564 homes |

---

## 1. GTFS mode mapping
`output/gtfs_route_type_check.csv`, written on every run: per route type the
mode, route count, sample names and share of names matching the mode. All
routes of type 109 are named S-something and all of type 400 are U1-U9;
rail-replacement buses (type 700) named S1, U2 etc. stay buses.

## 2. Directed walk graph in v0
pyrosm lists each segment once, in OSM drawing direction. The v0 notebook
built an `osmnx` `MultiDiGraph` from these rows, so walking was only possible
along the drawing direction; its connected-component step used
`to_undirected()`, which hid the problem. `scripts/check_directionality.py`
on pyrosm's bundled Helsinki sample (10 random sources, seed 0;
`output/directionality_check_Helsinki.csv`): 0.03% of segment pairs listed in
both directions; 20.9% of nodes unreachable on the directed graph; 94.3% of
reachable nodes get a longer shortest path (median 201.5 m longer). Not yet
measured on the Berlin extract.

## 3. Network detours
`scripts/check_detour.py` → `output/detour_check.csv`: network versus
straight-line distance to the nearest stop, per building, main stop set.
Median network/straight-line ratio per mode across Berlin: 1.22 to 1.54. Long
walks are therefore not a graph artefact. Example: in Neukölln the median
building is 2838 m in a straight line from the nearest S-Bahn stop but 976 m
from the nearest U-Bahn stop; the Ring S-Bahn serves the dense north, the U7
the populous south.

## 4. Edge effects of the 2 km buffer
`scripts/compare_segment_runs.py` → `output/segments_friedrichshain-kreuzberg_vs_berlin.csv`:
the Friedrichshain-Kreuzberg pilot (district + 2 km) against the citywide run
(Berlin + 2 km), segments matched by midpoint and length within 1 m. Spearman
rank correlation at least 0.9905 for every measure and radius. The residual
differences come from cleaning two slightly different networks; 2 km of
buffer is enough.

## 5. Reference streets
`src/berlin_access/reference_streets.py` lists main arterials and shopping
streets per district with their provenance; `output/segments_berlin_main_streets.csv`
gives each street's median percentile among its district's residential
segments. Only streets named before that district's results were seen are
used in the summary (97 of 106 entries).
- Median percentile of reference streets on angular choice at 2000 m: 76
  (Charlottenburg-Wilmersdorf) to 94 (Spandau).
- Weakest: Wilmersdorfer Straße (53rd) and Alt-Tegel (52nd), both largely
  pedestrian shopping zones.
- Pilot detail (Friedrichshain-Kreuzberg, citywide run): NACH at 2000 m from
  64 (Skalitzer Straße) to 97 (Karl-Marx-Allee).
- **NACH artefact**: Tunnelstraße on the Stralau peninsula ranks first on NACH
  at 800, 1200 and 2000 m but is in none of the angular-choice top-10 lists
  (`output/segments_friedrichshain-kreuzberg_top10.csv`). NACH rises when total
  depth is small, so the only street into a small enclosed network scores
  high. Within a district, choice and NAIN are the more robust readings.
- Top-10 lists of street maxima proved fragile (driven by single segments);
  median percentiles of reference streets are the check used.

## 6. Segment-length weighting (Mitte)
`scripts/test_segment_weighting.py --district Mitte` →
`output/segments_mitte_weighting_{summary,test,top10}.csv`. Reference streets
fixed in advance.
- Unweighted, the reference streets rank at the 80th (Badstraße) to 99th
  (Karl-Liebknecht-Straße) percentile on choice at 2000 m.
- Weighting mainly helps at 800 m: Badstraße 59 → 80, Rosenthaler Straße
  58 → 76, Leipziger Straße 59 → 74, Alt-Moabit 55 → 68.
- Weighted and unweighted choice are closely related (Spearman 0.955 at 800 m,
  0.986 at 2000 m).
- The 2000 m top list (Annenstraße, Fischerinsel, Neue Roßstraße, Alte
  Jakobstraße) is the same with and without weighting: one continuous,
  low-angle route over the Roßstraßenbrücke
  (`output/maps/diagnostic_mitte_fischerinsel_choice_2000.png`). The
  Mühlendamm bridge is present in OSM as a primary road; a cleaning effect on
  the Mühlendamm/Gertraudenstraße carriageways is not ruled out.

## 7. Place Syntax Tool against Python
PST 3.3.2 run by the project owner in QGIS 4.2.3 (macOS) on
`output/pst/pst_inputs_friedrichshain-kreuzberg.gpkg`, results in
`output/pst/pst_results_friedrichshain-kreuzberg.gpkg`, compared with
`scripts/compare_pst_results.py` → `output/pst/pst_vs_python_friedrichshain-kreuzberg.csv`.
- **Attraction Distance** (walking, 800 m, S- or U-Bahn stations, `ADww800st`):
  same "within 800 m or not" status for all 9,564 residential buildings (1,552
  with none). For the 8,012 in reach, all distances within 1 m (median
  absolute difference 0.025 m, maximum 0.12 m, Spearman 1.0).
- **Attraction Reach** (walking, 800 m, S- or U-Bahn stations, `ARw800st`):
  identical count for all 9,564 buildings; 1,552 / 4,226 / 3,072 / 638 / 76
  buildings with 0 / 1 / 2 / 3 / 4 stations within 800 m.
- The segment map and the Phase 0 walking network agree on the median walk to
  the nearest S- or U-Bahn station (553.1 vs 551.1 m,
  `output/pst/python_reach_friedrichshain-kreuzberg_summary.json`; Spearman
  0.899, lower because Phase 0 measures to the nearest platform along
  sidewalks).
