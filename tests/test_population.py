import numpy as np
import openpyxl
import pandas as pd

from berlin_access.pipeline import aggregate, weighted_quantiles
from berlin_access.population import AGE_COLUMNS, allocate_residents, read_plr_population, residential_weight


def buildings():
    return pd.DataFrame({
        "plr_id": ["A", "A", "A", "A", "B", "C"],
        "building": ["apartments", "yes", "garage", "yes", "house", "shed"],
        "building_use": [None, None, None, "retail", None, None],
        "levels": ["5", None, None, None, None, None],
        "footprint_m2": [400.0, 100.0, 50.0, 300.0, 120.0, 60.0],
    })


def test_residential_weight_excludes_non_homes_and_fills_levels():
    w, stats = residential_weight(buildings(), min_footprint_m2=40)
    assert w[0] == 400 * 5
    assert w[1] == 100 * 5  # storeys filled with the Planungsraum median
    assert w[2] == 0  # garage
    assert w[3] == 0  # untyped, but building:use=retail
    assert w[4] == 120 * 5  # no known storeys in B: city-wide median
    assert w[5] == 0
    assert stats["candidate_buildings"] == 3


def test_allocation_preserves_totals_and_reports_unplaced():
    b = buildings()
    w, _ = residential_weight(b, 40)
    pop = pd.DataFrame({"plr_id": ["A", "B", "C"], "residents": [1000, 50, 20]})
    res, check = allocate_residents(b, pop, w)
    assert np.isclose(res[b.plr_id == "A"].sum(), 1000)
    assert np.isclose(res[0] / res[1], 4.0)
    c = check.set_index("plr_id")
    assert c.loc["C", "unallocated"] == 20  # only a shed in C
    assert c.loc["B", "unallocated"] == 0


def test_weighted_quantiles_and_resident_aggregate():
    assert weighted_quantiles(np.array([1.0, 2.0, 3.0]), np.array([1.0, 1.0, 10.0]), [0.5]) == [3.0]
    d = pd.DataFrame({"plr_id": ["A", "A", "A"], "residents": [0.0, 1.0, 9.0], "dist_m_Bus": [6000.0, 60.0, 600.0]})
    r = aggregate(d, "plr_id", ["Bus"], [1.0], [15], weight_col="residents").set_index("unit_id").loc["A"]
    assert r["n_buildings"] == 2  # zero-resident building ignored
    assert np.isclose(r["median_min"], 10.0)
    assert r["share_over_15min"] == 0.0


def write_t2(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "T2"
    ws.append(["2  Einwohner nach LOR-Planungsräumen und Altersgruppen"])
    ws.append([None, None, None, None, "Mitte"])
    for codes, total, ages in rows:
        ws.append([*codes, total, *ages, None, None])
    wb.save(path)


def test_read_plr_population(tmp_path):
    p = tmp_path / "t.xlsx"
    write_t2(p, [(("01", "10", "01", "01"), 36, [1, 2, 3, 4, 5, 6, 7, 8]), (("01", "10", "01", "02"), 8, [1] * 8)])
    df = read_plr_population(p)
    assert list(df["plr_id"]) == ["01100101", "01100102"]
    assert list(df.columns) == ["plr_id", "residents", *AGE_COLUMNS]
    assert df["residents"].sum() == 44
