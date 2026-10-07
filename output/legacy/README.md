# Legacy v0 output (do not use)

`fussweg_oepnv_ergebnisse_v0.csv` is the table produced by the original
`notebooks/fussweg_oepnv.ipynb`. It is kept only so the effect of the Phase 0
fixes can be compared. Known defects:

1. route_type 109 (S-Bahn) was mapped to Bus. The "S-Bahn" column contains
   route types 2 and 100 (regional rail) only.
2. A short name starting with "U" turned rail-replacement buses
   (route_type 700) into U-Bahn.
3. The walk graph was directed along OSM drawing direction (see
   `output/directionality_check_Helsinki.csv` and `docs/methods.md`).
4. Walks of 30 min or more were dropped before taking the median. Combined
   with defect 1, this is the most likely reason Steglitz-Zehlendorf shows
   0.25 min for "S-Bahn": only the few buildings right next to a regional rail
   stop survived the filter (inference, not re-run).
5. Stops were clipped at the city boundary.
6. Walking speed was 1.0 m/s.

The README table in the original repository did not match this file either.
