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
| Walk network, buildings | [OpenStreetMap](https://www.openstreetmap.org/copyright) via the [Geofabrik Berlin extract](https://download.geofabrik.de/europe/germany/berlin.html) | ODbL 1.0, © OpenStreetMap contributors |
| Stops and routes | [VBB GTFS](https://www.vbb.de/vbb-services/api-open-data/datensaetze/) | VBB open data terms |
| District boundaries | Berlin Open Data (`data/bezirksgrenzen.geojson`, in repo) | Berlin Open Data terms |

Large files are downloaded into `data/raw/` and never committed:

```bash
python scripts/download_data.py      # OSM PBF (~100 MB) + VBB GTFS zip
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

_Results have not been generated yet. Run `python scripts/run_accessibility.py` and then `python scripts/build_readme_tables.py`. The table in earlier versions of this README did not come from the code and has been removed; the buggy v0 output is kept in `output/legacy/` for reference only._

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

- Buildings are unweighted: a shed counts like an apartment block.
- GTFS platform coordinates are used, not station entrances. For deep U-Bahn
  stations the real walk can differ.
- The Berlin OSM extract ends near the city boundary, so the 1 km stop buffer is only
  partly effective (see `output/stops_by_mode.csv` and `docs/methods.md`).
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
