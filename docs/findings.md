# Findings

What the results show, stated descriptively. Each number comes from the file
named in brackets. These are associations in one city at one point in time;
they do not establish causes. Method: [methods.md](methods.md); checks:
[validation.md](validation.md); all tables: [results.md](results.md).

## 1. Walking to transit (Phase 0)

Per resident, walking at 1.3 m/s, stops inside Berlin only
(`output/walk_time_by_district.csv`, `output/walk_time_by_planungsraum.csv`):

- **Rail.** The median walk to the nearest S- or U-Bahn stop is 10.5 min.
  33.1% of residents walk more than 15 min and 10.2% more than 30 min.
- **Bus.** Almost everyone lives near a bus stop: median 3.6 min, 0.4% beyond
  15 min.
- **Large differences between districts.** The median walk to S- or U-Bahn is
  6.6 min in Mitte, 7.0 min in Charlottenburg-Wilmersdorf and 7.1 min in
  Friedrichshain-Kreuzberg, but 17.6 min in Treptow-Köpenick and 31.9 min in
  Spandau, where 81.3% of residents walk more than 15 min.
- **Kiez level.** In 188 of the 537 Planungsräume with at least 100 residents,
  the median resident walks more than 15 min to S- or U-Bahn; together these
  Planungsräume have 1,295,373 residents.
- **Older residents.** At a slower 1.0 m/s, 50.4% of the 747,667 residents
  aged 65+ are more than 15 min from an S- or U-Bahn stop.
- **Frequency matters less than expected at peak.** Counting only stops with
  a departure at least every 10 min (weekday 07:00-09:00), the median walk to
  any such stop is 4.1 min and 1.7% of residents walk more than 15 min
  (`output/walk_time_by_district_frequent_10min.csv`). A peak-hour threshold
  hardly separates areas; evening or weekend service would be a sharper test.
- **Counting buildings misleads.** Without resident weighting, sheds, garages
  and allotment huts dominate district medians and overstate walks (table
  "Effect of resident weighting" in [results.md](results.md)).

## 2. Street-network configuration (Phase 1)

- In every district the main streets named in advance rank high on angular
  choice at 2000 m: their median percentile is between 76 and 94
  (`output/segments_berlin_main_streets.csv`). Exceptions are pedestrian
  shopping streets such as Wilmersdorfer Straße and Alt-Tegel: angular choice
  describes through-routes, not footfall.
- NACH can be dominated by small enclosed networks with one access street
  (Stralau peninsula), so within a district choice and NAIN are the more
  robust readings (validation §5).

## 3. Place Syntax Tool (Phase 2)

- PST and the independent Python cross-check give the same attraction
  distance (within 1 m) and the same attraction reach for all 9,564
  residential buildings of the Friedrichshain-Kreuzberg pilot
  (`output/pst/pst_vs_python_friedrichshain-kreuzberg.csv`).
- In the pilot, 1,552 of 9,564 residential buildings have no S- or U-Bahn
  station within an 800 m walk.

## 4. Metric access versus configuration (Phase 3)

Spearman rank correlation between the walk time to transit and the measures
of each building's nearest street (`output/phase3/correlations.csv`; negative
= more central streets go with shorter walks):

| Berlin | NAIN 800 | NAIN 2000 | NACH 800 | NACH 2000 | metric closeness 800 |
|---|---|---|---|---|---|
| Walk to S/U, buildings | 0.042 | 0.043 | -0.108 | -0.107 | -0.321 |
| Walk to S/U, Planungsräume | -0.095 | -0.078 | -0.377 | -0.385 | -0.211 |
| Walk to frequent stop, buildings | -0.004 | -0.141 | -0.144 | -0.154 | -0.428 |
| Walk to frequent stop, Planungsräume | -0.043 | -0.133 | -0.264 | -0.221 | -0.329 |

- **Angular integration (NAIN) is nearly unrelated to rail access.** Across
  Berlin, how integrated a home's street is says almost nothing about how far
  it is from S- or U-Bahn (|rho| at most 0.1). The sign even differs between
  districts: in Marzahn-Hellersdorf more integrated streets go with *longer*
  walks (rho 0.61 at building level for NAIN 2000).
- **Metric closeness relates most consistently.** Homes on streets with more
  street network within 800 m tend to be closer to transit (rho -0.32 for
  S- or U-Bahn, -0.43 for frequent stops, building level). Network density,
  rather than angular configuration, goes with transit access.
- **Choice relates at the neighbourhood scale.** NACH correlates weakly per
  building (-0.11) but more clearly per Planungsraum (-0.38): neighbourhoods
  with through-routes tend to have rail nearby, while individual homes
  within them vary. The difference between the two levels is itself a
  reminder that results depend on the unit of analysis.
- **Pilot, station counts.** In Friedrichshain-Kreuzberg the number of S- or
  U-Bahn stations within 800 m correlates with metric closeness (rho 0.419)
  but not with NAIN at 2000 m (rho -0.024)
  (`output/phase3/reach_vs_centrality_friedrichshain-kreuzberg.csv`).
- **Where the two diverge** (`output/phase3/divergence_by_planungsraum.csv`,
  map `output/maps/phase3_divergence.png`): 49 Planungsräume (357,260
  residents) are close to rail but on configurationally segregated streets;
  most are in Neukölln (11), Charlottenburg-Wilmersdorf (8) and
  Tempelhof-Schöneberg (8). 51 Planungsräume (386,364 residents) are on
  integrated streets but far from rail, most of them in Pankow (16) and
  Treptow-Köpenick (6). The second group marks places where the street
  network would support walking to a station that is not there; the first,
  places where a station is near but the streets leading to it are
  configurationally peripheral.

## 5. What this does not show

- Correlation is not causation, and walk distance is not ridership.
- Residents within a Planungsraum are placed by an OSM floor-area estimate.
- Angular measures come from an automatically cleaned network; results near
  complex junctions (e.g. around Fischerinsel / Mühlendamm) may reflect
  cleaning choices.
- One city, one timetable (autumn 2026), one population snapshot (end of 2025).
