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
restructuring the original analysis). See [`docs/methods.md`](docs/methods.md) for
every methodological choice.

## Data

| Data | Source | Licence |
|---|---|---|
| Walk network, buildings | [OpenStreetMap](https://www.openstreetmap.org/copyright) via the [BBBike Berlin extract](https://download.bbbike.org/osm/bbbike/Berlin/) (covers a margin around the city) | ODbL 1.0, © OpenStreetMap contributors |
| Stops and routes | [VBB GTFS](https://www.vbb.de/vbb-services/api-open-data/datensaetze/) | VBB open data terms |
| District boundaries | Berlin Open Data (`data/bezirksgrenzen.geojson`, in repo) | Berlin Open Data terms |

Large files are downloaded into `data/raw/` and never committed:

```bash
python scripts/download_data.py      # OSM PBF (~175 MB) + VBB GTFS zip
```

If the GTFS URL in `config.yaml` has moved, download the feed by hand from the VBB
page and save it as `data/raw/GTFS.zip`.

## Method (short)

1. OSM walking network (pyrosm), **undirected**, projected to EPSG:32633, largest
   connected component.
2. One representative point per OSM building, assigned to the district that contains
   it, snapped to the nearest network node.
3. GTFS stops classified by `route_type` (109 = S-Bahn, 400 = U-Bahn, 900 = Tram,
   100/106/2 = Regionalbahn, 3/700-799 = Bus), kept up to 1 km outside the city.
4. Multi-source Dijkstra per mode; snap distances of stop and building count towards
   the walk.
5. Per district: median walk time and share of buildings beyond 15 and 30 min, at
   1.3 m/s (main) and 1.0 / 1.4 m/s (sensitivity). No building is dropped for being
   far away.

## Run

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/download_data.py
python scripts/run_accessibility.py      # writes output/*.csv and output/run_metadata.json
python scripts/build_readme_tables.py    # regenerates the Results section below
pytest                                   # unit tests + smoke test on a bundled sample
```

## Results

All numbers in this section are written by `scripts/build_readme_tables.py` from
`output/*.csv`. Do not edit them by hand.

<!-- BEGIN GENERATED: results (scripts/build_readme_tables.py) -->

#### Median walk time to the nearest stop (minutes, 1.3 m/s)

| District | S-Bahn | U-Bahn | Tram | Bus | Regionalbahn |
|---|---|---|---|---|---|
| Berlin | 21.8 | 36.2 | 47.9 | 4.4 | 52.6 |
| Charlottenburg-Wilmersdorf | 14.9 | 12.2 | 68.6 | 3.9 | 33.9 |
| Friedrichshain-Kreuzberg | 18.2 | 7.3 | 25.5 | 3.3 | 26.1 |
| Lichtenberg | 19.5 | 39.4 | 8.4 | 4.8 | 29.6 |
| Marzahn-Hellersdorf | 23.2 | 31.9 | 17.5 | 4.6 | 47.1 |
| Mitte | 11.9 | 7.2 | 11.4 | 3.8 | 25.2 |
| Neukölln | 46.6 | 16.4 | 56.2 | 3.9 | 70.2 |
| Pankow | 24.9 | 52.0 | 12.4 | 5.3 | 54.5 |
| Reinickendorf | 18.2 | 41.5 | 76.3 | 4.6 | 124.5 |
| Spandau | 49.2 | 46.5 | 164.8 | 4.3 | 43.9 |
| Steglitz-Zehlendorf | 17.4 | 37.3 | 148.0 | 4.0 | 43.0 |
| Tempelhof-Schöneberg | 18.7 | 30.6 | 116.1 | 3.9 | 64.0 |
| Treptow-Köpenick | 23.2 | 83.6 | 17.2 | 5.1 | 75.3 |

#### Share of buildings more than 15 min from the nearest stop (1.3 m/s)

| District | S-Bahn | U-Bahn | Tram | Bus | Regionalbahn |
|---|---|---|---|---|---|
| Berlin | 70.6% | 76.1% | 75.4% | 1.5% | 94.6% |
| Charlottenburg-Wilmersdorf | 49.4% | 43.0% | 99.9% | 1.3% | 89.0% |
| Friedrichshain-Kreuzberg | 61.0% | 6.8% | 66.0% | 0.0% | 88.1% |
| Lichtenberg | 68.2% | 85.0% | 24.1% | 3.5% | 88.2% |
| Marzahn-Hellersdorf | 77.4% | 86.5% | 57.2% | 0.1% | 93.7% |
| Mitte | 33.5% | 10.2% | 37.5% | 0.8% | 76.6% |
| Neukölln | 89.3% | 55.1% | 100.0% | 0.1% | 100.0% |
| Pankow | 78.1% | 90.5% | 42.2% | 3.4% | 96.0% |
| Reinickendorf | 64.5% | 84.8% | 98.4% | 0.8% | 100.0% |
| Spandau | 95.9% | 91.8% | 100.0% | 1.0% | 94.3% |
| Steglitz-Zehlendorf | 60.2% | 81.0% | 99.9% | 0.7% | 94.3% |
| Tempelhof-Schöneberg | 62.6% | 69.8% | 100.0% | 0.2% | 96.8% |
| Treptow-Köpenick | 74.5% | 100.0% | 54.3% | 3.8% | 97.9% |

#### Share of buildings more than 30 min from the nearest stop (1.3 m/s)

| District | S-Bahn | U-Bahn | Tram | Bus | Regionalbahn |
|---|---|---|---|---|---|
| Berlin | 31.6% | 57.1% | 61.1% | 0.0% | 78.8% |
| Charlottenburg-Wilmersdorf | 3.8% | 13.2% | 93.9% | 0.0% | 58.1% |
| Friedrichshain-Kreuzberg | 12.3% | 1.0% | 42.8% | 0.0% | 33.3% |
| Lichtenberg | 17.4% | 61.6% | 1.7% | 0.0% | 49.4% |
| Marzahn-Hellersdorf | 31.7% | 54.3% | 21.5% | 0.0% | 74.1% |
| Mitte | 9.2% | 0.7% | 4.8% | 0.0% | 35.2% |
| Neukölln | 76.9% | 13.8% | 93.1% | 0.0% | 100.0% |
| Pankow | 38.1% | 78.3% | 19.6% | 0.1% | 86.9% |
| Reinickendorf | 19.8% | 65.1% | 90.5% | 0.0% | 99.7% |
| Spandau | 80.7% | 75.2% | 100.0% | 0.0% | 75.2% |
| Steglitz-Zehlendorf | 10.7% | 62.3% | 99.9% | 0.1% | 76.6% |
| Tempelhof-Schöneberg | 16.7% | 50.6% | 100.0% | 0.0% | 84.0% |
| Treptow-Köpenick | 29.7% | 97.8% | 26.9% | 0.2% | 89.8% |

#### Sensitivity to walking speed (Berlin-wide median, minutes)

| Mode | 1.0 m/s | 1.3 m/s | 1.4 m/s |
|---|---|---|---|
| S-Bahn | 28.4 | 21.8 | 20.3 |
| U-Bahn | 47.0 | 36.2 | 33.6 |
| Tram | 62.3 | 47.9 | 44.5 |
| Bus | 5.7 | 4.4 | 4.0 |
| Regionalbahn | 68.4 | 52.6 | 48.8 |

#### GTFS stops used per mode

| mode | stops_total | stops_inside_berlin | stops_in_buffer_zone | stops_dropped_snap | stops_used | snap_m_median |
|---|---|---|---|---|---|---|
| S-Bahn | 314 | 298 | 16 | 0 | 314 | 21.6 |
| U-Bahn | 384 | 384 | 0 | 0 | 384 | 7.9 |
| Tram | 820 | 804 | 16 | 0 | 820 | 13.9 |
| Bus | 6826 | 6237 | 589 | 0 | 6826 | 6.0 |
| Regionalbahn | 74 | 63 | 11 | 0 | 74 | 14.6 |

#### Provenance

- GTFS feed: calendar_min_start=20261006, calendar_max_end=20261212
- gtfs: downloaded 2026-10-07T11:02:32Z from https://www.vbb.de/vbbgtfs
- pbf: downloaded 2026-10-07T11:07:00Z from https://download.bbbike.org/osm/bbbike/Berlin/Berlin.osm.pbf
- Buildings used: 503622 (excluded for snap distance > 250 m: 413)
- Pipeline run: 2026-10-07T11:31:07Z

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

- Buildings are unweighted: a shed counts like an apartment block. District medians
  are therefore pulled towards areas with many small buildings (see
  `docs/methods.md`, "Reading the results"). Treat them as building-based, not
  population-based.
- Where a district has no stop of a mode (e.g. trams in the west), the value is the
  walk to the nearest stop in another district, not a meaningful service level.
- GTFS platform coordinates are used, not station entrances. For deep U-Bahn
  stations the real walk can differ.
- Nearest stop only: frequency, line count and travel time onwards are ignored.
- Network quality depends on OSM footway mapping, which varies by area.

## Next steps

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
