# Decision log

What was decided, when, and why, in order. The current method is in
[methods.md](methods.md); evidence for the checks is in [validation.md](validation.md).

## Phase 0: fixing and rebuilding the walk-to-transit analysis (2026-10-07)

| Decision | Why |
|---|---|
| Map GTFS route type 109 to S-Bahn; add Regionalbahn (2, 100, 106); never reclassify a 700-series route as rail | v0 counted the S-Bahn as bus and rail-replacement buses named U2, U5... as U-Bahn |
| Make the walk graph undirected | v0 walked only along OSM drawing direction (validation §2) |
| Keep all buildings in the statistics; report shares beyond 15 and 30 min | v0 dropped walks of 30 min or more before the median |
| Walking speed as a parameter: 1.3 m/s main, 1.0 and 1.4 sensitivity | v0 used 1.0 m/s without sensitivity |
| Replace the README results table with generated tables | the v0 table did not come from the code; v0 output kept in `output/legacy/` |
| Move the pipeline from the notebook to `src/` and `scripts/`, relative paths, `config.yaml` | reproducibility from a clean clone |
| OSM from the BBBike Berlin extract instead of Geofabrik | Geofabrik's extract ends at the city boundary; BBBike covers a margin around it (and Geofabrik was unreachable from the build environment) |
| Strict city limit: only stops inside Berlin; 1 km buffer as sensitivity | the study is about the city as lived and governed; comparisons between units should not depend on Brandenburg (owner's decision) |
| LOR Planungsräume as the single geometry source for all levels | comparative analysis between districts and Kieze (owner); levels nest exactly |
| Weight results by residents (register count per Planungsraum, allocated to buildings by floor area) | counting buildings let sheds, garages and allotment huts dominate district medians |
| Combined mode "S- or U-Bahn" | rail access in a Kiez is the nearer of the two |
| Older residents (65+) at 1.0 m/s, shown as counts with proportional circles | location within a Planungsraum is unknown, so a per-Planungsraum median would repeat the all-resident one |
| Frequent-stops scenario (10 min, weekday morning peak) and "Any mode" | include bus and tram at Kiez scale without letting every bus stop count (owner's question) |
| Cache the parsed network and buildings, keyed by input hashes | reruns in about 30 s instead of 13 min |

## Phase 1: angular segment analysis (2026-10-07 to 2026-10-08)

| Decision | Why |
|---|---|
| Use cityseer's own OSM cleaning recipe, with park, plaza and parking areas from the local PBF | an established, documented recipe instead of a custom one; no dependency on a live API |
| Build the segment map from all public ways, not pyrosm's walking network | the walking network omits streets with separately mapped sidewalks; removing sidewalks then deleted those streets (first pilot run had 3,486 segments instead of about 21,000) |
| One citywide run (Berlin + 2 km) instead of 12 district runs | one consistent segment map; border streets computed once; validated against the pilot (validation §4) |
| Remove `highway=track` from the segment map | forest rides and tracks topped integration in outer districts |
| Report only residential streets (home within 50 m), but keep all streets in the network | the owner asked to keep only streets with residential buildings; removing the others from the graph would have distorted the residential streets' own values |
| Unweighted angular measures as the main ones; length-weighted choice as a supplementary column | NAIN and NACH are defined on unweighted measures; weighting helps modestly (validation §6) |
| Sanity check by reference streets per district instead of top-10 lists | top-10 lists of street maxima proved fragile; reference-street lists record their provenance |

## Phase 2: Place Syntax Tool (2026-10-08)

| Decision | Why |
|---|---|
| Pilot district Friedrichshain-Kreuzberg only | all of Berlin is likely too large for PST in QGIS |
| Stations instead of GTFS stop points as destinations | one station has several stop points (platforms, poles) |
| Split segments into straight two-point lines | PST rejects polylines ("contains polyline geometry, which is not supported") |
| Unlink points only where lines meet without a shared end point | the first export also unlinked 20 real junctions |
| Validate with a Python cross-check rather than assume | PST runs by hand; an independent implementation tests both (validation §7) |

## Phase 3: comparison (2026-10-08)

| Decision | Why |
|---|---|
| Building ↔ nearest live street segment | the street a home faces is its configurational context |
| Correlations at building and Planungsraum level | aggregation changes correlations; both are shown |
| Divergence by citywide thirds of walk time to S- or U-Bahn and NAIN at 2000 m | simple, symmetric classes; 2000 m matches the scale of the walk to a station |

## Repository (2026-10-08)

| Decision | Why |
|---|---|
| All commits authored by the project owner; no co-author lines | owner's decision; AI assistance is disclosed in the README instead |
| Documentation split into methods, validation, decisions, findings, results | the methods file had grown into a running log |

## Reproducibility (2026-10-08)

| Decision | Why |
|---|---|
| Run every script with `PYTHONHASHSEED=0`; rerun Phase 1 and 3 with it | network cleaning depended on the per-process hash seed, so a clean clone did not reproduce the segment map (validation §8) |
| Keep the Phase 2 PST files as one consistent snapshot until PST is rerun | the PST check compares two tools on the same network; regenerating only the Python side would compare different networks |
| Test suite runs on GitHub Actions for every push to `main` and every pull request | catches breakage without a local run; the tests need no downloaded data |
