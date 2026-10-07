# Berlin walk-to-transit accessibility

> **Kurzfassung (DE):** Wie weit gehen Berlinerinnen und Berliner zu Fuß zur nächsten
> Haltestelle von S-Bahn, U-Bahn, Tram, Bus und Regionalbahn? Für jedes OSM-Gebäude
> wird die Fußwegdistanz im OSM-Fußwegenetz zur nächsten GTFS-Haltestelle je
> Verkehrsmittel berechnet und pro Bezirk zusammengefasst (Median, Anteil über 15 und
> 30 Minuten, Gehgeschwindigkeit 1,0 / 1,3 / 1,4 m/s). Die Tabellen unten werden aus
> den CSV-Dateien in `output/` erzeugt. Geplant: Space-Syntax-Analyse (angulare
> Segmentanalyse) und Place-Syntax-Erreichbarkeit als Vergleich.

## Purpose

How far is the nearest stop of each transit mode, on foot, from every building in
Berlin? This is a metric, network-based accessibility measure. The project will
extend it with configurational measures (angular segment analysis, Place Syntax
attraction reach) and compare the two. Status: **Phase 0** (fixing and
restructuring the original analysis), with results per district and per LOR
Planungsraum, weighted by residents. See [`docs/methods.md`](docs/methods.md) for
every methodological choice.

## Data

| Data | Source | Licence |
|---|---|---|
| Walk network, buildings | [OpenStreetMap](https://www.openstreetmap.org/copyright) via the [BBBike Berlin extract](https://download.bbbike.org/osm/bbbike/Berlin/) (covers a margin around the city) | ODbL 1.0, © OpenStreetMap contributors |
| Stops and routes | [VBB GTFS](https://www.vbb.de/vbb-services/api-open-data/datensaetze/) | VBB open data terms |
| Planungsräume, Bezirksregionen, districts | [LOR 2021](https://gdi.berlin.de/services/wfs/lor_2021), Geoportal Berlin | Berlin Open Data terms (dl-de/by-2-0) |
| Residents per Planungsraum | Einwohnerregisterstatistik 31.12.2025, [Amt für Statistik Berlin-Brandenburg](https://www.statistik-berlin-brandenburg.de/a-i-16-hj/) (Statistischer Bericht A I 16) | see publisher's terms |

Large files are downloaded into `data/raw/` and never committed:

```bash
python scripts/download_data.py      # OSM PBF (~175 MB), VBB GTFS, LOR units, population report
```

If the GTFS URL in `config.yaml` has moved, download the feed by hand from the VBB
page and save it as `data/raw/GTFS.zip`.

## Method (short)

1. OSM walking network (pyrosm), **undirected**, projected to EPSG:32633, largest
   connected component.
2. One representative point per OSM building, assigned to the LOR Planungsraum that
   contains it (and through it to its Bezirksregion and district), snapped to the
   nearest network node.
3. Residents of each Planungsraum (population register) split among its residential
   buildings by footprint x storeys; garages, sheds, allotment huts and other
   non-residential buildings get none.
4. GTFS stops classified by `route_type` (109 = S-Bahn, 400 = U-Bahn, 900 = Tram,
   100/106 = Regionalbahn, 3/700-799 = Bus). **Only stops inside Berlin** count; a
   1 km buffer is reported as a sensitivity run.
5. Multi-source Dijkstra per mode; snap distances of stop and building count towards
   the walk.
6. Per district, Bezirksregion and Planungsraum: median walk time and share of
   **residents** beyond 15 and 30 min, at 1.3 m/s (main) and 1.0 / 1.4 m/s. Building
   counts are kept as a comparison. No building is dropped for being far away.

## Run

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/download_data.py
python scripts/run_accessibility.py      # writes output/*.csv and output/run_metadata.json
                                         # (first run ~15 min to parse OSM; cached afterwards)
python scripts/build_readme_tables.py    # regenerates the Results section below
pytest                                   # unit tests + smoke test on a bundled sample
```

## Results

All numbers in this section are written by `scripts/build_readme_tables.py` from
`output/*.csv`. Do not edit them by hand.

<!-- BEGIN GENERATED: results (scripts/build_readme_tables.py) -->

All tables: walking speed 1.3 m/s, only stops inside Berlin, residents allocated to buildings (see `docs/methods.md`) unless stated otherwise.

#### Median walk time to the nearest stop, per resident (minutes)

| District | S-Bahn | U-Bahn | Tram | Bus | Regionalbahn |
|---|---|---|---|---|---|
| Berlin | 16.7 | 15.9 | 33.1 | 3.6 | 38.4 |
| Charlottenburg-Wilmersdorf | 13.7 | 7.8 | 59.5 | 3.3 | 26.8 |
| Friedrichshain-Kreuzberg | 15.6 | 7.4 | 17.6 | 3.5 | 24.1 |
| Lichtenberg | 14.0 | 26.3 | 6.5 | 3.9 | 25.1 |
| Marzahn-Hellersdorf | 22.0 | 31.7 | 8.7 | 4.3 | 42.4 |
| Mitte | 12.8 | 7.2 | 9.7 | 3.2 | 25.9 |
| Neukölln | 29.0 | 9.4 | 53.6 | 3.4 | 62.0 |
| Pankow | 16.7 | 24.9 | 5.7 | 4.4 | 43.1 |
| Reinickendorf | 16.8 | 25.0 | 48.3 | 3.4 | 98.4 |
| Spandau | 40.4 | 32.6 | 148.3 | 3.5 | 36.9 |
| Steglitz-Zehlendorf | 14.6 | 30.3 | 148.6 | 3.4 | 41.6 |
| Tempelhof-Schöneberg | 16.6 | 10.9 | 91.0 | 3.3 | 37.5 |
| Treptow-Köpenick | 17.8 | 66.3 | 9.6 | 3.8 | 67.4 |

#### Share of residents more than 15 min from the nearest stop

| District | S-Bahn | U-Bahn | Tram | Bus | Regionalbahn |
|---|---|---|---|---|---|
| Berlin | 56.7% | 51.7% | 62.3% | 0.4% | 91.2% |
| Charlottenburg-Wilmersdorf | 42.3% | 19.8% | 100.0% | 0.2% | 81.6% |
| Friedrichshain-Kreuzberg | 52.7% | 6.3% | 54.5% | 0.0% | 82.6% |
| Lichtenberg | 45.8% | 72.3% | 12.6% | 0.3% | 75.2% |
| Marzahn-Hellersdorf | 68.3% | 70.9% | 30.1% | 0.1% | 92.2% |
| Mitte | 34.9% | 6.0% | 26.2% | 0.1% | 86.0% |
| Neukölln | 76.0% | 30.7% | 100.0% | 0.0% | 100.0% |
| Pankow | 57.7% | 67.1% | 15.8% | 0.5% | 98.5% |
| Reinickendorf | 59.9% | 69.5% | 91.9% | 0.6% | 100.0% |
| Spandau | 93.1% | 82.5% | 100.0% | 0.7% | 92.3% |
| Steglitz-Zehlendorf | 47.7% | 76.2% | 100.0% | 0.4% | 94.8% |
| Tempelhof-Schöneberg | 55.0% | 39.6% | 100.0% | 0.1% | 95.8% |
| Treptow-Köpenick | 60.4% | 100.0% | 40.0% | 1.6% | 95.3% |

#### Share of residents more than 30 min from the nearest stop

| District | S-Bahn | U-Bahn | Tram | Bus | Regionalbahn |
|---|---|---|---|---|---|
| Berlin | 19.2% | 33.2% | 51.7% | 0.0% | 66.4% |
| Charlottenburg-Wilmersdorf | 0.9% | 4.7% | 96.2% | 0.0% | 43.8% |
| Friedrichshain-Kreuzberg | 9.6% | 0.5% | 32.4% | 0.0% | 26.7% |
| Lichtenberg | 13.2% | 45.0% | 0.1% | 0.0% | 44.4% |
| Marzahn-Hellersdorf | 33.7% | 51.9% | 9.6% | 0.0% | 77.0% |
| Mitte | 4.5% | 0.2% | 4.5% | 0.0% | 35.4% |
| Neukölln | 48.9% | 6.2% | 97.1% | 0.0% | 99.9% |
| Pankow | 17.5% | 42.8% | 9.9% | 0.0% | 84.2% |
| Reinickendorf | 10.4% | 40.1% | 70.8% | 0.0% | 99.0% |
| Spandau | 68.4% | 54.1% | 100.0% | 0.0% | 63.9% |
| Steglitz-Zehlendorf | 8.5% | 50.6% | 100.0% | 0.0% | 77.8% |
| Tempelhof-Schöneberg | 11.5% | 24.6% | 100.0% | 0.0% | 69.9% |
| Treptow-Köpenick | 15.6% | 94.3% | 21.8% | 0.1% | 79.5% |

#### Effect of resident weighting (building-count median minus resident median, minutes)

Positive values: counting every building once (sheds, garages, allotment huts included) makes walks look longer than residents experience them.

| District | S-Bahn | U-Bahn | Tram | Bus | Regionalbahn |
|---|---|---|---|---|---|
| Berlin | +5.4 | +20.3 | +15.0 | +0.8 | +14.8 |
| Charlottenburg-Wilmersdorf | +1.2 | +4.4 | +9.2 | +0.6 | +7.1 |
| Friedrichshain-Kreuzberg | +2.7 | -0.1 | +7.9 | -0.2 | +2.0 |
| Lichtenberg | +5.5 | +13.2 | +1.9 | +0.9 | +4.5 |
| Marzahn-Hellersdorf | +3.2 | +0.2 | +8.8 | +0.2 | +4.7 |
| Mitte | -0.9 | +0.1 | +1.7 | +0.5 | -0.7 |
| Neukölln | +17.7 | +7.0 | +2.6 | +0.6 | +8.2 |
| Pankow | +8.3 | +27.0 | +6.6 | +1.0 | +11.4 |
| Reinickendorf | +1.3 | +16.6 | +28.0 | +1.2 | +26.1 |
| Spandau | +8.8 | +13.9 | +16.5 | +0.8 | +7.0 |
| Steglitz-Zehlendorf | +3.1 | +7.0 | +13.7 | +0.6 | +2.1 |
| Tempelhof-Schöneberg | +2.1 | +19.6 | +25.1 | +0.6 | +26.4 |
| Treptow-Köpenick | +5.8 | +17.3 | +7.6 | +1.4 | +18.3 |

#### Sensitivity to walking speed (Berlin, median per resident, minutes)

| Mode | 1.0 m/s | 1.3 m/s | 1.4 m/s |
|---|---|---|---|
| S-Bahn | 21.7 | 16.7 | 15.5 |
| U-Bahn | 20.7 | 15.9 | 14.8 |
| Tram | 43.0 | 33.1 | 30.7 |
| Bus | 4.7 | 3.6 | 3.3 |
| Regionalbahn | 50.0 | 38.4 | 35.7 |

#### Sensitivity to the city limit: stops up to 1000 m outside Berlin also counted (change in median per resident, minutes)

| District | S-Bahn | U-Bahn | Tram | Bus | Regionalbahn |
|---|---|---|---|---|---|
| Berlin | 0.0 | 0.0 | 0.0 | 0.0 | -0.1 |
| Charlottenburg-Wilmersdorf | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Friedrichshain-Kreuzberg | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Lichtenberg | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Marzahn-Hellersdorf | -0.5 | 0.0 | 0.0 | 0.0 | 0.0 |
| Mitte | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Neukölln | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Pankow | -0.1 | 0.0 | 0.0 | 0.0 | 0.0 |
| Reinickendorf | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Spandau | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Steglitz-Zehlendorf | 0.0 | 0.0 | -8.7 | 0.0 | -0.2 |
| Tempelhof-Schöneberg | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Treptow-Köpenick | -0.1 | 0.0 | 0.0 | 0.0 | -5.0 |

#### Spread across LOR Planungsräume (median walk per resident, minutes)

Distribution over the 537 Planungsräume with at least 100 residents (5 excluded as low population). Per-unit values are in `output/walk_time_by_planungsraum.csv` and `output/walk_time_by_bezirksregion.csv`.

| Mode | Planungsräume | p10 | median | p90 | max |
|---|---|---|---|---|---|
| S-Bahn | 537 | 8.7 | 16.8 | 43.8 | 159.4 |
| U-Bahn | 537 | 5.8 | 17.1 | 75.2 | 188.3 |
| Tram | 537 | 4.7 | 36.5 | 146.9 | 268.8 |
| Bus | 537 | 2.7 | 3.7 | 5.5 | 12.0 |
| Regionalbahn | 537 | 16.9 | 39.7 | 86.1 | 192.9 |

#### GTFS stops per mode

| mode | stops_inside_berlin | stops_outside_within_sensitivity_buffer | stops_dropped_snap | stops_used | snap_m_median |
|---|---|---|---|---|---|
| S-Bahn | 298 | 16 | 0 | 298 | 21.6 |
| U-Bahn | 384 | 0 | 0 | 384 | 7.9 |
| Tram | 804 | 16 | 0 | 804 | 13.9 |
| Bus | 6237 | 589 | 0 | 6237 | 6.0 |
| Regionalbahn | 63 | 11 | 0 | 63 | 14.6 |

#### Provenance

- GTFS feed: calendar_min_start=20261006, calendar_max_end=20261212
- gtfs: downloaded 2026-10-07T11:02:32Z from https://www.vbb.de/vbbgtfs
- pbf: downloaded 2026-10-07T11:07:00Z from https://download.bbbike.org/osm/bbbike/Berlin/Berlin.osm.pbf
- lor: downloaded 2026-10-07T12:01:08Z from https://gdi.berlin.de/services/wfs/lor_2021?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=lor_2021:a_lor_plr_2021&OUTPUTFORMAT=application/json&SRSNAME=EPSG:25833
- population: downloaded 2026-10-07T12:01:08Z from https://download.statistik-berlin-brandenburg.de/1df9da7ea6dbfa3a/f6ac408f14cd/SB_A01-16-00_2025h02_BE.xlsx
- Buildings: 503625 (excluded for snap distance > 250 m: 413)
- Residents: 3913644 in the register, 3913644.0 allocated to 331880 residential candidate buildings; storeys mapped for 41.8% of them
- Pipeline run: 2026-10-07T12:14:56Z

<!-- END GENERATED: results -->

## Changes from the first version (v0)

The original notebook (`notebooks/fussweg_oepnv.ipynb`, kept unchanged for
reference) had defects that affect every number it produced. Its output is in
`output/legacy/` with a list of them. In short: S-Bahn (route_type 109) was counted
as bus, rail-replacement buses named U2/U5/... as U-Bahn, the walk graph was
one-way along OSM drawing direction, walks of 30 min or more were dropped before the
median, and stops outside the boundary were ignored. The results table in the
earlier README did not come from the code at all and has been removed.

## Limitations

- Residents are placed within a Planungsraum by an OSM-based floor-area estimate.
  Storeys are mapped for only part of the buildings and mixed-use buildings count as
  residential, so the distribution *within* a Planungsraum is approximate; the total
  per Planungsraum is exact (register count).
- Comparing districts, Bezirksregionen and Planungsräume: results depend on unit size
  and shape (modifiable areal unit problem). Compare units within one level.
- Where a district has no stop of a mode (e.g. trams in the west), the value is the
  walk to the nearest stop in another district, not a meaningful service level.
- GTFS platform coordinates are used, not station entrances. For deep U-Bahn
  stations the real walk can differ.
- Nearest stop only: frequency, line count and travel time onwards are ignored.
- Network quality depends on OSM footway mapping, which varies by area.

## Next steps

- Walk times for older residents (65+ share per Planungsraum at 1.0 m/s) and maps per
  Planungsraum.
- **Phase 1:** angular segment analysis (cityseer) at 400 / 800 / 1200 / 2000 m,
  pilot in Friedrichshain-Kreuzberg; NAIN / NACH.
- **Phase 2:** Place Syntax Tool inputs (QGIS GeoPackage) and a Python cross-check of
  attraction reach.
- **Phase 3:** per-building comparison of metric walk time and configurational
  centrality.
- **Phase 4:** shade-weighted reach (with the SunWalk project).

## Other module: travel times to landmarks

`notebooks/reisezeiten_landmarks.ipynb` queries the Google Maps Distance Matrix API
(paid) for travel times from district centroids to four landmarks. It is unchanged
and not part of the pipeline above.

## Licence and author

Code: MIT, see [LICENSE](LICENSE). Data licences as listed above.
Giovani Goltara.
