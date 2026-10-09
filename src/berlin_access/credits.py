"""Attribution lines for maps, as the data licences require (docs/data_licences.md)."""

SOURCES = {
    "osm": "© OpenStreetMap contributors (ODbL)",
    "vbb": "VBB Verkehrsverbund Berlin-Brandenburg GmbH, GTFS (CC BY 4.0)",
    "afs": "Amt für Statistik Berlin-Brandenburg: LOR 2021, Einwohnerregister 31.12.2025 (CC BY 3.0 DE)",
}


def credits(*keys: str) -> str:
    """'Data: ...' line naming the given sources, e.g. credits("osm", "afs")."""
    return "Data: " + "; ".join(SOURCES[k] for k in keys) + "."
