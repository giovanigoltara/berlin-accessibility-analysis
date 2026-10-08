# Running Place Syntax Tool (PST) on the project data

This guide is for running PST by hand in QGIS. PST needs the QGIS interface,
so it cannot run in the automated pipeline. The dialog names and options
below were read from the PST source code, version 3.3.2
([github.com/SMoG-Chalmers/PST](https://github.com/SMoG-Chalmers/PST),
`pstqgis/src/pst/ui`), not from running it. If your PST version shows
different labels, the official PST documentation from Chalmers / KTH takes
precedence. Points marked *(suggestion)* are my choices, not PST defaults.

Pilot area: **Friedrichshain-Kreuzberg** (district + 2 km of network).
Running PST on all of Berlin (about 170,000 segments and 330,000 residential
buildings) is likely to be slow; try the pilot first.

## 1. Requirements

- QGIS 3.x (PST 3.3.2 declares QGIS 3.0 to 3.99 and Qt6 support). The PST
  install notes cover Windows and Mac.
- PST plugin. Its own install notes (`pstqgis/doc/readme.txt` in the source)
  describe installing from a ZIP file:
  1. Download the plugin ZIP from the PST releases on GitHub:
     https://github.com/SMoG-Chalmers/PST/releases. Take the release marked
     *Latest* (v3.3.2 at the time of writing), open its *Assets* list and
     download the plugin ZIP (a name starting with `pstqgis`; if there are
     separate files per operating system, take yours). Do **not** take the
     "Source code" archives: they lack the compiled library and will not
     install as a plugin. Do not unzip the file. (The SMoG page linked in the
     plugin's metadata, smog.chalmers.se/PST.html, no longer exists.)
  2. *Plugins › Manage and Install Plugins › Install from ZIP*, click `...`,
     select the ZIP, *Install Plugin* (QGIS may warn about untrusted sources).
  3. In the same dialog, tab *Installed*, make sure PST is ticked.
  4. The analyses are now under **Vector › PST**.
  5. Mac only: the first run may say `"libpstalgo.dylib" cannot be opened
     because the developer cannot be verified`. Open *System Settings ›
     Privacy & Security*, click *Allow anyway* for libpstalgo.dylib, and
     restart QGIS.

## 1b. Getting the input file onto your computer

The input file is in the GitHub repository, on branch
`claude/vibrant-darwin-phsgo4`: open the repository on github.com, switch to
that branch (branch menu top left), go to `output/pst/`, click
`pst_inputs_friedrichshain-kreuzberg.gpkg`, then the download button
("Download raw file").

## 2. Input data

File: `output/pst/pst_inputs_friedrichshain-kreuzberg.gpkg`
(regenerate with `python scripts/run_pst_inputs.py --district Friedrichshain-Kreuzberg`).
All layers are in EPSG:32633 (UTM 33N, metres), so distances in PST are metres.

| Layer | Geometry | Content |
|---|---|---|
| `segments` | lines | Cleaned street segment map from Phase 1 (citywide run), cropped to the district + 2 km. Lines meet at shared end points. Columns: `seg_id`, `street`, `district`, `in_study`, `residential`, `length_m`. |
| `origins` | points | Residential buildings in the district (one point inside each building with allocated residents). Columns: `osm_id`, `plr_id` (Planungsraum), `residents`, `res65` (residents 65+). |
| `destinations` | points | Stations inside Berlin within the district + 2 km (one point per station, mean of its platforms). 0/1 columns: `sb` S-Bahn, `ub` U-Bahn, `tr` tram, `bu` bus, `rb` regional rail, `su` S- or U-Bahn; `sbf` ... `rbf` the same with a departure at least every 10 min 07:00-09:00 on Tue 10 Nov 2026; `anyf` any frequent mode. |
| `study_area` | polygon | The district boundary, for display and selection. |
| `unlinks` | points | Every point where two segment lines cross without sharing an end point (bridges, tunnels). Use as *Unlink points* in PST. |

Load all four layers into QGIS (*Layer › Add Layer › Add Vector Layer*, choose
the GeoPackage, select all layers).

## 3. Attraction Reach (how many stations within walking distance)

*Vector › PST › Attraction Reach*. The wizard pages, in order:

1. **Input Tables**
   - Origins: *Points/Polygons* → `origins`.
   - Network: *Axial/Segment lines* → `segments`. Tick **Unlink points** and
     choose `unlinks`. In this segment map, lines are connected only where
     they share an end point; a bridge crosses the street below without one.
     I have not verified whether PST connects such crossings for segment
     maps; the unlink layer makes sure it does not, and is harmless if PST
     would not have connected them anyway.
   - Destinations: *Data objects* → `destinations`.
2. **Entry Points**: only relevant for polygon origins/destinations; our
   layers are points, so keep the defaults.
3. **Calculation Options**: leave *Enable distance weight mode* **off** for a
   plain count. (If switched on, PST weights each attraction by distance
   with f(x) = 1-x^C, a curve, or (x+1)^-C; then the Radius page is skipped.)
4. **Radius**: tick **Walking distance** and enter **800** meters. Run again
   with **400**.
5. **Attractions**: choose *Weigh attractions by data* and tick the columns
   to count, e.g. `su` (S- or U-Bahn stations) and `anyf` (frequent stops of
   any mode). Each 0/1 column then counts the stations that have it.
   *Attraction name (for output column)*: a 2-character name, e.g. `st`.
6. **Ready** › run.

PST writes the results as new columns on the `origins` layer. Column names
are built from codes: `AR` (attraction reach), the radius (`w800` = walking
800 m) and the attraction name or data column; check the exact names in the
attribute table.

### Angular variant *(suggestion)*

To combine walking distance with a limit on turning, repeat step 4 with
**Walking distance 800** and **Angular 180** degrees both ticked; PST then
counts stations reachable within 800 m *and* at most 180° of accumulated
turning. This variant has no Python cross-check yet.

## 4. Attraction Distance (walking distance to the nearest station)

*Vector › PST › Attraction Distance*:

1. **Input Tables**: as above, including *Unlink points* → `unlinks`.
2. **Entry Points**: defaults.
3. **Calculation Options**: tick **Walking distance (meters)**.
4. **Radius**: **Walking distance 2000** meters (the Python cross-check
   stops at 2 km).
5. **Destinations**: *Find minimum distance to:* **Destination element with
   specific attractions**, tick `su` (and in a second run `anyf`).
   *Destination name (for output column)*: e.g. `su`.
6. **Destination Attributes**: optional; skip.
7. Run.

## 5. Save the results and send them back

1. In the *Layers* panel, right-click `origins` › *Export › Save Features
   As...*. Format: GeoPackage. File name:
   `pst_results_friedrichshain-kreuzberg.gpkg`. Layer name: `origins`. OK.
2. Upload it to the repository: on github.com, branch
   `claude/vibrant-darwin-phsgo4`, folder `output/pst/`, *Add file › Upload
   files*, drop the file, *Commit changes* (to the same branch).
3. The comparison can then be run (it reads the PST column names from the
   file; they only need to be mapped once):

```bash
python scripts/compare_pst_results.py \
    --pst output/pst/pst_results_friedrichshain-kreuzberg.gpkg --layer origins \
    --map ARw800su=reach_su_800 --map ARw400su=reach_su_400 \
    --map ARw800anyf=reach_anyf_800 --map ADwsu=dist_su
```

(Replace the PST column names with the ones in the attribute table.)
Python columns in `output/pst/python_reach_friedrichshain-kreuzberg.csv`:
`reach_<col>_400`, `reach_<col>_800` and `dist_<col>` for `<col>` in
`sb, ub, tr, bu, rb, su, anyf`. The result goes to
`output/pst/pst_vs_python_friedrichshain-kreuzberg.csv`: share of buildings
with the same value, median absolute difference, and Spearman correlation.

## 6. What to expect

The Python cross-check follows the same rules as PST: each point is joined
to its closest line and that connection counts in the distance; walking
distance runs along the lines. Small differences are still possible:

- PST may join a point to a line differently when two lines are almost
  equally close.
- Distances exactly at the radius can fall on either side because of
  rounding.
- If you ran "Create Segment Map" on the segments first, the network is not
  the same.

Large differences (most buildings disagreeing) would point to a different
network or setting and are worth a look before using either result.
