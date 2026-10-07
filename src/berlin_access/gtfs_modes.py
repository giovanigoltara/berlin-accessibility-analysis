"""Map VBB GTFS routes to the transit modes used in the analysis.

The VBB feed uses the extended GTFS route types
(https://developers.google.com/transit/gtfs/reference/extended-route-types).
The earlier notebook mapped 109 (Suburban Railway = S-Bahn) to "Bus" and let a
name prefix "U" turn rail-replacement buses (type 700, named U2, U5...) into
U-Bahn. Both are fixed here: route_type decides, names are only a fallback for
route types this table does not know, and a 700-series route is always a bus.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pandas as pd

ROUTE_TYPE_MODE: dict[int, str | None] = {
    0: "Tram",
    900: "Tram",
    1: "U-Bahn",
    400: "U-Bahn",
    401: "U-Bahn",
    109: "S-Bahn",
    2: "Regionalbahn",
    100: "Regionalbahn",
    106: "Regionalbahn",
    3: "Bus",
    1000: None,  # water transport (ferries), not analysed
}

# Expected short-name patterns per mode, used for the consistency check and
# as a fallback for unknown route types. "M" is deliberately absent: in Berlin
# M-lines are both MetroTram (M10) and MetroBus (M29).
NAME_PATTERNS: dict[str, re.Pattern] = {
    "S-Bahn": re.compile(r"^S\d"),
    "U-Bahn": re.compile(r"^U\d"),
    "Regionalbahn": re.compile(r"^(RE|RB|FEX|IC|ICE|EC|\d)"),
}


def is_bus_series(rt: int) -> bool:
    return 700 <= rt < 800


def map_route_type_to_mode(rt) -> str | None:
    """Mode from route_type alone. Returns None for unknown or excluded types."""
    if pd.isna(rt):
        return None
    try:
        rt = int(rt)
    except (TypeError, ValueError):
        return None
    if is_bus_series(rt):
        return "Bus"
    return ROUTE_TYPE_MODE.get(rt)


def mode_from_name(short_name) -> str | None:
    if not isinstance(short_name, str):
        return None
    sn = short_name.strip().upper()
    for mode in ("S-Bahn", "U-Bahn"):
        if NAME_PATTERNS[mode].match(sn):
            return mode
    if re.match(r"^(RE|RB)\d", sn):
        return "Regionalbahn"
    return None


def classify_routes(routes: pd.DataFrame) -> pd.DataFrame:
    """Add `mode` and `mode_source` columns to a GTFS routes table.

    The name fallback is only used when the route type is unknown to
    ROUTE_TYPE_MODE (not when it is known and maps to None, e.g. ferries),
    and never for a 700-series bus.
    """
    out = routes.copy()
    rt = pd.to_numeric(out["route_type"], errors="coerce")
    out["mode"] = rt.map(map_route_type_to_mode)
    out["mode_source"] = "route_type"
    known = rt.isin(list(ROUTE_TYPE_MODE)) | rt.between(700, 799)
    fallback = ~known
    if fallback.any():
        out.loc[fallback, "mode"] = out.loc[fallback, "route_short_name"].map(mode_from_name)
        out.loc[fallback, "mode_source"] = "name_fallback"
    out.loc[out["mode"].isna(), "mode_source"] = "excluded"
    return out


def route_type_check(routes: pd.DataFrame, n_samples: int = 8) -> pd.DataFrame:
    """One row per route_type: mode, route count, sample names and the share of
    names that match the expected pattern for that mode (rail modes only)."""
    rows = []
    for (rt, mode), g in routes.groupby(["route_type", "mode"], dropna=False):
        names = g["route_short_name"].dropna().astype(str)
        pat = NAME_PATTERNS.get(mode) if isinstance(mode, str) else None
        share = names.str.upper().str.match(pat).mean() if pat is not None and len(names) else float("nan")
        rows.append(
            {
                "route_type": rt,
                "mode": mode,
                "n_routes": len(g),
                "share_names_matching_mode": round(share, 3) if pd.notna(share) else None,
                "sample_short_names": ", ".join(sorted(names.unique(), key=_natural)[:n_samples]),
            }
        )
    return pd.DataFrame(rows).sort_values("route_type").reset_index(drop=True)


def _natural(s: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def read_gtfs_tables(gtfs_zip: Path) -> dict[str, pd.DataFrame]:
    """Read the GTFS tables the pipeline needs, with only the needed columns."""
    with zipfile.ZipFile(gtfs_zip) as z:
        names = set(z.namelist())

        def read(name, usecols=None, dtype=str):
            with z.open(name) as f:
                return pd.read_csv(f, usecols=usecols, dtype=dtype)

        tables = {
            "routes": read("routes.txt", ["route_id", "route_type", "route_short_name"]),
            "trips": read("trips.txt", lambda c: c in {"trip_id", "route_id", "service_id"}),
            "stops": read("stops.txt", ["stop_id", "stop_name", "stop_lat", "stop_lon"]),
            "stop_times": read("stop_times.txt", lambda c: c in {"trip_id", "stop_id", "departure_time"}),
        }
        tables["feed_info"] = read("feed_info.txt") if "feed_info.txt" in names else pd.DataFrame()
        tables["calendar"] = read("calendar.txt") if "calendar.txt" in names else pd.DataFrame()
        tables["calendar_dates"] = read("calendar_dates.txt") if "calendar_dates.txt" in names else pd.DataFrame()
    tables["routes"]["route_type"] = pd.to_numeric(tables["routes"]["route_type"])
    for c in ("stop_lat", "stop_lon"):
        tables["stops"][c] = pd.to_numeric(tables["stops"][c], errors="coerce")
    return tables


def feed_validity(tables: dict[str, pd.DataFrame]) -> dict:
    """Feed version and validity window, from feed_info.txt or calendar.txt."""
    info = {}
    fi = tables.get("feed_info")
    if fi is not None and len(fi):
        for c in ("feed_publisher_name", "feed_version", "feed_start_date", "feed_end_date"):
            if c in fi.columns:
                info[c] = str(fi[c].iloc[0])
    cal = tables.get("calendar")
    if cal is not None and len(cal):
        info["calendar_min_start"] = str(cal["start_date"].min())
        info["calendar_max_end"] = str(cal["end_date"].max())
    return info


def stop_modes(tables: dict[str, pd.DataFrame], routes: pd.DataFrame) -> pd.DataFrame:
    """One row per (stop_id, mode) for every stop served by at least one trip of that mode."""
    trip_mode = tables["trips"].merge(routes[["route_id", "mode"]], on="route_id", how="left")
    trip_mode = trip_mode.dropna(subset=["mode"]).set_index("trip_id")["mode"]
    st = tables["stop_times"]
    st = st.assign(mode=st["trip_id"].map(trip_mode)).dropna(subset=["mode"])
    pairs = st.groupby(["stop_id", "mode"], as_index=False).size().rename(columns={"size": "n_stop_events"})
    return pairs.merge(tables["stops"], on="stop_id", how="inner")


def active_services(tables: dict[str, pd.DataFrame], date: str) -> set[str]:
    """service_ids running on `date` (YYYYMMDD): calendar.txt weekday pattern
    within its validity window, plus additions and minus removals from
    calendar_dates.txt."""
    day = pd.Timestamp(date).day_name().lower()
    cal, cd = tables["calendar"], tables["calendar_dates"]
    active = set()
    if len(cal):
        active = set(cal.loc[(cal[day] == "1") & (cal["start_date"] <= date) & (cal["end_date"] >= date), "service_id"])
    if len(cd):
        on_day = cd[cd["date"] == date]
        active |= set(on_day.loc[on_day["exception_type"] == "1", "service_id"])
        active -= set(on_day.loc[on_day["exception_type"] == "2", "service_id"])
    return active


def _seconds(hhmmss: pd.Series) -> pd.Series:
    """GTFS times (may exceed 24:00:00) to seconds after midnight."""
    parts = hhmmss.str.split(":", expand=True).astype(float)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def stop_departures(
    tables: dict[str, pd.DataFrame], routes: pd.DataFrame, date: str, start: str, end: str
) -> pd.DataFrame:
    """Departures per (stop_id, mode) on `date` between `start` and `end` (HH:MM).

    Counted per GTFS stop point. VBB stop points are platforms or kerbside
    poles, usually one per direction, so the count is roughly one direction's
    departures.
    """
    services = active_services(tables, date)
    trips = tables["trips"][tables["trips"]["service_id"].isin(services)]
    trips = trips.merge(routes[["route_id", "mode"]], on="route_id").dropna(subset=["mode"])
    st = tables["stop_times"]
    st = st[st["trip_id"].isin(trips["trip_id"]) & st["departure_time"].notna()]
    t = _seconds(st["departure_time"])
    t0, t1 = (_seconds(pd.Series([x + ":00"])).iloc[0] for x in (start, end))
    st = st[(t >= t0) & (t < t1)]
    st = st.assign(mode=st["trip_id"].map(trips.set_index("trip_id")["mode"]))
    return st.groupby(["stop_id", "mode"], as_index=False).size().rename(columns={"size": "departures"})
