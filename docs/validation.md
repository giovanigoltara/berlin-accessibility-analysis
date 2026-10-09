# Validation

Checks of the method and what they showed. Every number comes from the file
named next to it. Method: [methods.md](methods.md); history: [decisions.md](decisions.md).

| # | Check | Result in one line |
|---|---|---|
| 1 | [GTFS mode mapping](#1-gtfs-mode-mapping) | Every route type matches its line names |
| 2 | [Directed walk graph in v0](#2-directed-walk-graph-in-v0) | v0 walks were one-way; large effect on a sample |
| 3 | [Network detours](#3-network-detours) | Detour factors 1.22-1.54, typical for cities |
| 4 | [Edge effects of the 2 km buffer](#4-edge-effects-of-the-2-km-buffer) | Pilot and citywide run agree (Spearman >= 0.991) |
| 5 | [Reference streets](#5-reference-streets) | Main streets rank at the 76th-94th percentile on choice |
| 6 | [Segment-length weighting (Mitte)](#6-segment-length-weighting-mitte) | Helps at 800 m; does not change the 2000 m top list |
| 7 | [Place Syntax Tool against Python](#7-place-syntax-tool-against-python) | Identical reach and distance for all 9,564 homes |
| 8 | [Reproducibility from a clean clone](#8-reproducibility-from-a-clean-clone) | Same inputs, same Phase 0; network cleaning needed a fixed hash seed |

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
rank correlation at least 0.991 for every measure and radius. The residual
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
  65 (Skalitzer Straße) to 97 (Karl-Marx-Allee).
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
PST 3.3.2 run by the project owner in QGIS 4 (macOS) on
`output/pst/pst_inputs_friedrichshain-kreuzberg.gpkg`, results in
`output/pst/pst_results_friedrichshain-kreuzberg.gpkg`, compared with
`scripts/compare_pst_results.py` → `output/pst/pst_vs_python_friedrichshain-kreuzberg.csv`.
The current files come from the second run (2026-10-09) on the segment map of
the seeded citywide run (§8); the first run (2026-10-08, QGIS 4.2.3) on the
earlier, unseeded network agreed equally well and is in the git history.
- **Attraction Distance** (walking, 800 m, S- or U-Bahn stations, `ADww800st`):
  same "within 800 m or not" status for all 9,564 residential buildings (1,545
  with none). For the 8,019 in reach, all distances within 1 m (median
  absolute difference 0.025 m, maximum 0.08 m, Spearman 1.0).
- **Attraction Reach** (walking, 800 m, S- or U-Bahn stations, `ARw800st`):
  identical count for all 9,564 buildings; 1,545 / 4,231 / 3,080 / 634 / 74
  buildings with 0 / 1 / 2 / 3 / 4 stations within 800 m.
- The segment map and the Phase 0 walking network agree on the median walk to
  the nearest S- or U-Bahn station (551.7 vs 551.1 m,
  `output/pst/python_reach_friedrichshain-kreuzberg_summary.json`; Spearman
  0.894, lower because Phase 0 measures to the nearest platform along
  sidewalks).
- QGIS 4 marks PST 3.3.2 as incompatible after an update, because the plugin
  declares `qgisMaximumVersion=3.99`; see `docs/pst_howto.md` §1.

## 8. Reproducibility from a clean clone
Fresh clone of `main`, new virtual environment from `requirements.txt`,
`scripts/download_data.py` into an empty `data/raw/`, then every step of the
README Quick start in order (2026-10-08).
- **Inputs.** OSM extract, GTFS feed and population report are byte-identical
  to those of the published run (SHA-256 in `output/run_metadata.json` and
  `output/reproducibility/run_metadata_clean_clone.json`). The LOR file
  differs only in the `timeStamp` the WFS server writes into each response;
  its features are identical.
- **Phase 0.** All walk-time tables, maps and checks came out byte-identical.
- **Phase 1.** Network cleaning was not reproducible: from the same
  1,282,972 primal edges, the published run kept 168,869 edges and the clean
  clone 168,885 (`output/reproducibility/segments_berlin_metadata_unseeded_run{1,2}.json`).
  Cause: Python randomises string hashing per process, which changes the
  iteration order of sets of OSM ids, and cityseer's cleaning depends on that
  order. Cleaning a small test area around Alexanderplatz gave a different
  network for each seed and an identical one when the seed was repeated.
  Every script now restarts itself with `PYTHONHASHSEED=0`
  (`scripts/_bootstrap.py`); the seed is recorded in
  `output/segments_berlin_metadata.json`. The published Phase 1 and 3 results
  come from this seeded run (168,910 edges).
  A second seeded citywide run, in a separate clone without cached data,
  reproduced the cleaned network and every Phase 1 output file byte for
  byte (after sorting the rows of the summary file, whose order followed
  cityseer's unstable column order and is now fixed).
- **How much it mattered.** Between the two unseeded runs, 97.2% of
  residential segments match one to one and the Spearman correlation is at
  least 0.993 for every measure and radius
  (`output/reproducibility/segments_berlin_unseeded_run1_vs_run2.csv`). The
  district medians in the segment summary change in the second or third
  decimal, the reference-street medians by up to 8 percentile points; rankings by single segments (top-three streets) change more,
  as noted in §5. In Phase 3, the divergence classes changed by up to four
  Planungsräume per class (49 and 51 in commit `792eb1b`, 53 and 52 now).
- **Runtime** on the build machine: about 18 min for Phase 0 (first run,
  including OSM parsing) and 65 min for the citywide Phase 1 run; all other
  steps take under a minute each.
