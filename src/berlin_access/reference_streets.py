"""Reference streets for the Phase 1 sanity check, per district.

Main arterials and shopping streets of each district, lower-case as in OSM
`name`. A segment matches if its name contains the string, within its own
district only (several districts have a "Berliner Straße" or "Breite Straße").

Provenance matters for how much the check proves:
- Friedrichshain-Kreuzberg: Frankfurter Allee, Kottbusser Damm, Oranienstraße
  from the project brief; Karl-Marx-Allee, Warschauer, Skalitzer, Gneisenau-,
  Yorckstraße, Mehringdamm named before the pilot; Petersburger, Boxhagener,
  Revaler Straße added after the pilot run.
- Mitte: fixed before the segment-length weighting test.
- All other districts: drafted on 2026-10-08 from general knowledge of
  Berlin, after the citywide run's top-three streets per district had been
  shown in the README. Streets that appeared in those top-three lists are in
  SEEN and are weaker evidence.
"""

REFERENCE_STREETS: dict[str, list[str]] = {
    "Charlottenburg-Wilmersdorf": [
        "kurfürstendamm", "kantstraße", "wilmersdorfer straße", "bismarckstraße", "otto-suhr-allee",
        "hohenzollerndamm", "bundesallee", "uhlandstraße", "kaiserdamm",
    ],
    "Friedrichshain-Kreuzberg": [
        "frankfurter allee", "karl-marx-allee", "warschauer straße", "skalitzer straße", "kottbusser damm",
        "oranienstraße", "gneisenaustraße", "yorckstraße", "mehringdamm", "petersburger straße",
        "boxhagener straße", "revaler straße",
    ],
    "Lichtenberg": [
        "frankfurter allee", "möllendorffstraße", "landsberger allee", "treskowallee", "konrad-wolf-straße",
        "weitlingstraße", "siegfriedstraße", "falkenberger chaussee",
    ],
    "Marzahn-Hellersdorf": [
        "märkische allee", "landsberger allee", "allee der kosmonauten", "hellersdorfer straße",
        "stendaler straße", "alt-biesdorf", "cecilienstraße", "blumberger damm",
    ],
    "Mitte": [
        "friedrichstraße", "unter den linden", "leipziger straße", "torstraße", "karl-liebknecht-straße",
        "invalidenstraße", "brunnenstraße", "müllerstraße", "turmstraße", "alt-moabit",
        "rosenthaler straße", "badstraße",
    ],
    "Neukölln": [
        "karl-marx-straße", "sonnenallee", "hermannstraße", "weserstraße", "buschkrugallee", "britzer damm",
        "johannisthaler chaussee", "alt-rudow",
    ],
    "Pankow": [
        "schönhauser allee", "prenzlauer allee", "greifswalder straße", "kastanienallee", "berliner straße",
        "breite straße", "wisbyer straße", "bornholmer straße", "danziger straße",
    ],
    "Reinickendorf": [
        "residenzstraße", "ollenhauerstraße", "scharnweberstraße", "berliner straße", "oranienburger straße",
        "alt-tegel", "hermsdorfer damm", "wilhelmsruher damm",
    ],
    "Spandau": [
        "carl-schurz-straße", "breite straße", "klosterstraße", "heerstraße", "falkenseer chaussee",
        "seegefelder straße", "schönwalder straße", "pichelsdorfer straße",
    ],
    "Steglitz-Zehlendorf": [
        "schloßstraße", "clayallee", "potsdamer chaussee", "unter den eichen", "teltower damm",
        "hindenburgdamm", "albrechtstraße", "argentinische allee",
    ],
    "Tempelhof-Schöneberg": [
        "hauptstraße", "potsdamer straße", "tempelhofer damm", "mariendorfer damm", "martin-luther-straße",
        "grunewaldstraße", "akazienstraße", "lichtenrader damm",
    ],
    "Treptow-Köpenick": [
        "bahnhofstraße", "alt-köpenick", "schnellerstraße", "adlergestell", "baumschulenstraße",
        "elsenstraße", "dörpfeldstraße", "grünauer straße",
    ],
}

# (district, street) pairs that appeared in a top-three list shown before drafting.
SEEN: set[tuple[str, str]] = {
    ("Neukölln", "sonnenallee"),
    ("Neukölln", "hermannstraße"),
    ("Pankow", "greifswalder straße"),
    ("Reinickendorf", "wilhelmsruher damm"),
    ("Spandau", "heerstraße"),
    ("Tempelhof-Schöneberg", "lichtenrader damm"),
}

# Added after looking at pilot results (Friedrichshain-Kreuzberg).
ADDED_AFTER_RESULTS: set[tuple[str, str]] = {
    ("Friedrichshain-Kreuzberg", "petersburger straße"),
    ("Friedrichshain-Kreuzberg", "boxhagener straße"),
    ("Friedrichshain-Kreuzberg", "revaler straße"),
}
