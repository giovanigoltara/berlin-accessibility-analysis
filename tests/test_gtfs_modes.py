import pandas as pd

from berlin_access.gtfs_modes import classify_routes, map_route_type_to_mode, route_type_check, stop_modes


def routes_fixture():
    # route_type values and names as printed by the v0 notebook's own diagnostic
    rows = [
        ("s1", 109, "S1"), ("s41", 109, "S41"),
        ("u8", 400, "U8"), ("u2", 400, "U2"),
        ("u2_sev", 700, "U2"), ("u7_sev", 700, "U7"),  # rail-replacement buses
        ("m10", 900, "M10"), ("m29", 700, "M29"),
        ("re1", 100, "RE1"), ("rb10", 106, "RB10"), ("fex", 2, "FEX"),
        ("bus_x", 3, "X7"), ("ferry", 1000, "F10"),
        ("unknown_s", 999, "S5"), ("unknown_m", 999, "M4"),
    ]
    return pd.DataFrame(rows, columns=["route_id", "route_type", "route_short_name"])


def test_route_type_mapping():
    assert map_route_type_to_mode(109) == "S-Bahn"
    assert map_route_type_to_mode(400) == map_route_type_to_mode(1) == map_route_type_to_mode(401) == "U-Bahn"
    assert map_route_type_to_mode(0) == map_route_type_to_mode(900) == "Tram"
    for rt in (2, 100, 106):
        assert map_route_type_to_mode(rt) == "Regionalbahn"
    for rt in (3, 700, 715, 799):
        assert map_route_type_to_mode(rt) == "Bus"
    assert map_route_type_to_mode(1000) is None
    assert map_route_type_to_mode(None) is None


def test_replacement_buses_stay_buses():
    r = classify_routes(routes_fixture()).set_index("route_id")
    assert r.loc["u2_sev", "mode"] == "Bus"
    assert r.loc["u7_sev", "mode"] == "Bus"
    assert r.loc["u2", "mode"] == "U-Bahn"
    assert r.loc["s41", "mode"] == "S-Bahn"
    assert r.loc["m29", "mode"] == "Bus"
    assert r.loc["m10", "mode"] == "Tram"


def test_name_fallback_only_for_unknown_types():
    r = classify_routes(routes_fixture()).set_index("route_id")
    assert r.loc["unknown_s", "mode"] == "S-Bahn"
    assert r.loc["unknown_s", "mode_source"] == "name_fallback"
    assert pd.isna(r.loc["unknown_m", "mode"])  # M is ambiguous in Berlin
    assert pd.isna(r.loc["ferry", "mode"])  # known type, deliberately excluded
    assert r.loc["ferry", "mode_source"] == "excluded"


def test_route_type_check_flags_names():
    chk = route_type_check(classify_routes(routes_fixture()))
    s = chk.set_index("route_type")
    assert s.loc[109, "share_names_matching_mode"] == 1.0
    assert s.loc[400, "n_routes"] == 2


def test_stop_modes():
    routes = classify_routes(routes_fixture())
    tables = {
        "trips": pd.DataFrame({"trip_id": ["t1", "t2", "t3"], "route_id": ["s1", "u2_sev", "ferry"]}),
        "stop_times": pd.DataFrame({"trip_id": ["t1", "t1", "t2", "t3"], "stop_id": ["a", "b", "a", "c"]}),
        "stops": pd.DataFrame({"stop_id": ["a", "b", "c"], "stop_name": list("ABC"), "stop_lat": [52.5] * 3, "stop_lon": [13.4] * 3}),
    }
    sm = stop_modes(tables, routes)
    assert set(map(tuple, sm[["stop_id", "mode"]].values)) == {("a", "S-Bahn"), ("b", "S-Bahn"), ("a", "Bus")}
