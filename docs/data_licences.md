# Data licences and attribution

Checked 2026-10-09. For each source: the licence, the attribution it requires,
and where the licence statement was found. All sources allow reuse with
attribution; OpenStreetMap additionally requires derived databases to be
shared under the same licence.

## Sources

| Data | Licence | Attribution to give | Evidence |
|---|---|---|---|
| OpenStreetMap (walk network, buildings, street names), via the BBBike Berlin extract | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) | © OpenStreetMap contributors | [openstreetmap.org/copyright](https://www.openstreetmap.org/copyright); BBBike redistributes OSM data unchanged |
| VBB GTFS timetable (stops, routes, departures) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | VBB Verkehrsverbund Berlin-Brandenburg GmbH | VBB's open data page states "Diese Datensätze werden bereitgestellt unter der Lizenz Creative Commons Attribution 4.0 International (CC BY 4.0)"; daten.berlin.de lists the dataset "VBB-Fahrplandaten via GTFS" as cc-by. Both seen as search excerpts only: vbb.de is not reachable from the build environment, and the feed contains no licence file. To be confirmed on [the VBB dataset page](https://unternehmen.vbb.de/digitale-services/datensaetze/) |
| LOR 2021 (Planungsräume, Bezirksregionen, districts), WFS `lor_2021` | [CC BY 3.0 DE](https://creativecommons.org/licenses/by/3.0/de/) | Amt für Statistik Berlin-Brandenburg | The service's own capabilities document (`https://gdi.berlin.de/services/wfs/lor_2021?SERVICE=WFS&REQUEST=GetCapabilities`), field `Fees`: "Der Datenbestand wird unter der Lizenz CC-BY-3.0-Namensnennung veröffentlicht (vgl. https://creativecommons.org/licenses/by/3.0/de/). Als Urheber ist dabei zu nennen: Amt für Statistik Berlin-Brandenburg" |
| Residents per Planungsraum: Statistischer Bericht A I 16 – hj 2/25, Einwohnerregisterstatistik Berlin 31.12.2025 | [CC BY 3.0 DE](https://creativecommons.org/licenses/by/3.0/de/) | Amt für Statistik Berlin-Brandenburg, Potsdam, 2026 | Impressum sheet of the downloaded file (`SB_A01-16-00_2025h02_BE.xlsx`): "Dieses Werk ist unter einer Creative Commons Lizenz vom Typ Namensnennung 3.0 Deutschland zugänglich" |

An earlier version of the README gave the LOR licence as dl-de/by-2-0; the
service itself states CC BY 3.0 DE.

## Changes made to the data

CC BY asks that changes be indicated. All sources were processed, none is
redistributed unchanged:
- OSM ways and buildings: filtered, projected to EPSG:32633, built into a
  walking graph and a cleaned street-segment map (`docs/methods.md` §2, §3).
- GTFS: stops classified by mode, departures counted for one weekday.
- LOR: geometries reprojected and joined to the population table.
- Population: register counts per Planungsraum allocated to buildings by
  estimated floor area.

## Licences of this repository

- **Code** (`src/`, `scripts/`, `tests/`): MIT, see [LICENSE](../LICENSE).
- **Data files in `output/`** (tables, GeoPackages, maps): made available under
  the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/),
  because they are derived from OpenStreetMap. Attribution: © OpenStreetMap
  contributors; VBB Verkehrsverbund Berlin-Brandenburg GmbH; Amt für Statistik
  Berlin-Brandenburg. The CC BY sources impose only attribution, so they can
  be combined under ODbL.
- **Maps** (`output/maps/`) carry the attribution line for the sources they use
  (`src/berlin_access/credits.py`).

## Software

| Software | Licence | Use |
|---|---|---|
| [cityseer](https://cityseer.benchmarkurbanism.com/) 5.8.0 | AGPL-3.0 (package metadata) | Phase 1 segment analysis; imported, not redistributed |
| pyrosm, osmnx | MIT | reading OSM data |
| geopandas | BSD-3-Clause | spatial data handling |
| [Place Syntax Tool](https://github.com/SMoG-Chalmers/PST) 3.3.2 | see the PST repository | Phase 2, run by hand in QGIS |

## Removed

`output/reisezeiten_landmarks.csv` (travel times from the Google Maps Distance
Matrix API, written by `notebooks/reisezeiten_landmarks.ipynb`) was removed
from the repository on 2026-10-09: Google Maps Platform terms restrict
storing and redistributing API results. It remains in the git history of
earlier commits.
