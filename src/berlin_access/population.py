"""Residents per LOR Planungsraum and their allocation to buildings.

Population comes from the Einwohnerregisterstatistik (Amt für Statistik
Berlin-Brandenburg, Statistischer Bericht A I 16, table T2: residents by LOR
Planungsraum and age group). Residents are only known per Planungsraum, so
they are distributed to the buildings inside it in proportion to an estimate
of residential floor area (dasymetric allocation). See docs/methods.md.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

AGE_COLUMNS = ["age_0_6", "age_6_15", "age_15_18", "age_18_27", "age_27_45", "age_45_55", "age_55_65", "age_65_plus"]

# OSM building values that are not homes. Everything else (including the very
# common untyped building=yes) is a residential candidate.
NON_RESIDENTIAL = {
    "garage", "garages", "carport", "shed", "hut", "cabin", "roof", "greenhouse", "glasshouse",
    "industrial", "warehouse", "manufacture", "factory", "commercial", "retail", "supermarket",
    "kiosk", "office", "service", "transformer_tower", "substation", "power", "storage_tank",
    "silo", "parking", "church", "chapel", "cathedral", "mosque", "synagogue", "temple",
    "religious", "school", "university", "college", "kindergarten", "hospital", "public",
    "civic", "government", "train_station", "transportation", "hangar", "stadium",
    "sports_hall", "sports_centre", "grandstand", "pavilion", "farm_auxiliary", "barn",
    "stable", "cowshed", "bunker", "ruins", "construction", "toilets", "boathouse",
    "tent", "container", "allotment_house", "gatehouse", "bridge", "tower", "water_tower",
    "hotel", "museum", "fire_station", "military", "data_center",
}


def read_plr_population(xlsx: Path) -> pd.DataFrame:
    """Table T2 of the report: one row per Planungsraum with total and age groups."""
    ws = openpyxl.load_workbook(xlsx, read_only=True)["T2"]
    rows = []
    for r in ws.iter_rows(values_only=True):
        codes = r[:4]
        if all(isinstance(c, str) and c.isdigit() for c in codes):
            rows.append(["".join(codes), *r[4:13]])
    df = pd.DataFrame(rows, columns=["plr_id", "residents", *AGE_COLUMNS])
    df[["residents", *AGE_COLUMNS]] = df[["residents", *AGE_COLUMNS]].apply(pd.to_numeric).fillna(0).astype(int)
    if df.empty or not (df[AGE_COLUMNS].sum(axis=1) == df["residents"]).all():
        raise ValueError("unexpected T2 layout: no rows, or age groups do not sum to the total")
    return df


def residential_weight(bld: pd.DataFrame, min_footprint_m2: float) -> tuple[pd.Series, dict]:
    """Relative residential floor area per building.

    weight = footprint area x number of storeys, for buildings whose OSM type
    (or building:use, for untyped buildings) is not clearly non-residential and whose footprint is at least
    `min_footprint_m2`. Missing storey counts are filled with the median of
    known counts in the same Planungsraum, then the city-wide median.
    """
    tag = bld["building"].fillna("yes").str.lower()
    # For untyped buildings, building:use (where mapped) says what they are used for.
    use = bld["building_use"].fillna("").astype(str).str.lower() if "building_use" in bld else ""
    tag = tag.where((tag != "yes") | (use == ""), use)
    candidate = ~tag.isin(NON_RESIDENTIAL) & (bld["footprint_m2"] >= min_footprint_m2)
    levels = pd.to_numeric(bld["levels"], errors="coerce").where(lambda x: (x >= 1) & (x <= 60))
    known = levels.where(candidate)
    plr_median = known.groupby(bld["plr_id"]).transform("median")
    city_median = known.median()
    filled = levels.fillna(plr_median).fillna(city_median if pd.notna(city_median) else 1.0)
    w = (bld["footprint_m2"] * filled).where(candidate, 0.0)
    stats = {
        "candidate_buildings": int(candidate.sum()),
        "non_residential_by_tag": int((tag.isin(NON_RESIDENTIAL)).sum()),
        "below_min_footprint": int((~tag.isin(NON_RESIDENTIAL) & (bld["footprint_m2"] < min_footprint_m2)).sum()),
        "levels_known_share_of_candidates": round(float(levels[candidate].notna().mean()), 4),
        "city_median_levels": None if pd.isna(city_median) else float(city_median),
    }
    return w, stats


def allocate_residents(bld: pd.DataFrame, pop: pd.DataFrame, weight: pd.Series) -> tuple[pd.Series, pd.DataFrame]:
    """Residents per building: each Planungsraum's residents split by weight.

    Returns the per-building residents and a per-Planungsraum check table
    (residents that could not be placed because the unit has no candidate building).
    """
    wsum = weight.groupby(bld["plr_id"]).transform("sum")
    p = bld["plr_id"].map(pop.set_index("plr_id")["residents"]).fillna(0)
    res = (p * weight / wsum.replace(0, np.nan)).fillna(0.0)
    check = pop[["plr_id", "residents"]].merge(
        pd.DataFrame({"plr_id": bld["plr_id"], "w": weight, "allocated": res, "n": 1})
        .groupby("plr_id", as_index=False)
        .agg(buildings=("n", "sum"), weight_sum=("w", "sum"), allocated=("allocated", "sum")),
        on="plr_id",
        how="left",
    ).fillna({"buildings": 0, "weight_sum": 0, "allocated": 0})
    check["unallocated"] = (check["residents"] - check["allocated"]).round(1)
    return res, check
