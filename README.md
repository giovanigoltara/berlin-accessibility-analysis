# Berlin Accessibility Analysis

> **Hinweis:** Dies ist ein experimentelles Projekt. Die Ergebnisse dienen zu Demonstrationszwecken und sollten nicht für produktive Anwendungen verwendet werden.

Entwicklung einer Geodaten-Pipeline zur Analyse von Erreichbarkeit und Reisezeiten in Berlin. Integration von Google Maps API mit Berliner Open Data zur Verarbeitung von Verkehrsdaten, POI-Informationen und administrativen Grenzen über 12 Bezirke. Räumliche Analyse und Visualisierung urbaner Zugänglichkeit zur Unterstützung stadtplanerischer Entscheidungsprozesse.

---

## Projektübersicht

Dieses Projekt analysiert die **Erreichbarkeit von öffentlichen Verkehrsmitteln** und **Reisezeiten zu wichtigen Landmarks** in allen 12 Berliner Bezirken. Es kombiniert OpenStreetMap-Daten, GTFS-Fahrplandaten und die Google Maps Distance Matrix API.

### Hauptkomponenten

| Modul | Beschreibung |
|-------|-------------|
| `notebooks/fussweg_oepnv.ipynb` | Berechnung der Fußwege zu ÖPNV-Haltestellen (S-Bahn, U-Bahn, Tram, Bus) |
| `notebooks/reisezeiten_landmarks.ipynb` | Reisezeiten zu wichtigen Berliner Landmarks via Google Maps API |

---

## Ergebnisse

### Fußwege zu ÖPNV-Haltestellen

Mediane Gehzeit (in Minuten) von Gebäuden zur nächsten Haltestelle:

| Bezirk | S-Bahn | U-Bahn | Tram | Bus |
|--------|--------|--------|------|-----|
| Mitte | 12.65 | 12.45 | 7.82 | 5.94 |
| Friedrichshain-Kreuzberg | 15.23 | 10.87 | 8.52 | 6.27 |
| Pankow | 18.45 | 18.92 | 9.15 | 7.43 |
| Charlottenburg-Wilmersdorf | 14.78 | 11.23 | - | 6.89 |
| Spandau | 21.34 | - | - | 8.56 |
| Steglitz-Zehlendorf | 19.87 | 15.67 | - | 7.92 |
| Tempelhof-Schöneberg | 16.23 | 13.45 | - | 6.78 |
| Neukölln | 17.89 | 12.34 | - | 6.45 |
| Treptow-Köpenick | 20.56 | - | 11.23 | 8.12 |
| Marzahn-Hellersdorf | 22.45 | 23.30 | 10.87 | 9.12 |
| Lichtenberg | 16.78 | 14.56 | 9.45 | 7.23 |
| Reinickendorf | 18.92 | 19.45 | - | 7.89 |

### Reisezeiten zu Landmarks

Reisezeiten (in Minuten) vom Bezirkszentrum zu wichtigen Standorten:

**Ziele:**
- Alexanderplatz
- Flughafen Berlin Brandenburg (BER)
- Berlin Hauptbahnhof
- Charité

---

## Technologie-Stack

### Datenquellen
- **OpenStreetMap (OSM)** - Fußgängernetzwerk via `pyrosm`
- **GTFS Berlin** - Haltestellendaten der BVG/S-Bahn
- **Berliner Open Data** - Bezirksgrenzen und Gebäudedaten
- **Google Maps Distance Matrix API** - Reisezeiten (Auto, Fuß, ÖPNV)

### Python-Bibliotheken
```
geopandas>=0.14.0
pandas>=2.0.0
numpy>=1.24.0
shapely>=2.0.0
networkx>=3.0
osmnx>=1.6.0
pyrosm>=0.6.1
scipy>=1.11.0
googlemaps>=4.10.0
matplotlib>=3.7.0
tqdm>=4.65.0
```

---

## Installation

```bash
# Repository klonen
git clone https://github.com/YOUR_USERNAME/berlin-accessibility-analysis.git
cd berlin-accessibility-analysis

# Virtuelle Umgebung erstellen
python -m venv venv
source venv/bin/activate  # Linux/Mac
# oder: venv\Scripts\activate  # Windows

# Abhängigkeiten installieren
pip install -r requirements.txt
```

---

## Daten

### Automatischer Download

Die OSM-Daten werden beim ersten Durchlauf automatisch heruntergeladen. Für die GTFS-Daten:

1. **GTFS Berlin** herunterladen von [VBB Open Data](https://www.vbb.de/unsere-themen/vbbdigital/api-entwicklerinfos/datensaetze)
2. Entpacken in `data/gtfs/`

### Bezirksgrenzen

Berliner Bezirksgrenzen sind im Repository enthalten (`data/bezirksgrenzen.geojson`).

### Google Maps API

Für das Landmark-Modul wird ein Google Maps API-Key benötigt:

1. [Google Cloud Console](https://console.cloud.google.com/) öffnen
2. Distance Matrix API aktivieren
3. API-Key erstellen
4. Als Umgebungsvariable setzen:
   ```bash
   export GOOGLE_MAPS_API_KEY="your_api_key"
   ```

---

## Verwendung

### Fußwege zu ÖPNV berechnen

```bash
jupyter notebook notebooks/fussweg_oepnv.ipynb
```

Dieser Notebook:
1. Lädt das OSM-Fußgängernetzwerk für Berlin
2. Extrahiert ~500.000 Gebäudepunkte
3. Mappt GTFS-Haltestellen auf das Netzwerk
4. Berechnet kürzeste Wege mit Dijkstra-Algorithmus
5. Aggregiert Medianwerte pro Bezirk und Verkehrsmittel

### Reisezeiten zu Landmarks berechnen

```bash
jupyter notebook notebooks/reisezeiten_landmarks.ipynb
```

Dieser Notebook:
1. Berechnet Bezirkszentroide
2. Fragt Google Maps API für alle Kombinationen ab
3. Erstellt Vergleichstabellen (Auto, Fuß, ÖPNV)

**Hinweis:** API-Kosten ~$0.72 pro Durchlauf (144 Abfragen).

---

## Projektstruktur

```
berlin-accessibility-analysis/
├── README.md
├── requirements.txt
├── .gitignore
├── notebooks/
│   ├── fussweg_oepnv.ipynb          # ÖPNV-Erreichbarkeitsanalyse
│   └── reisezeiten_landmarks.ipynb   # Landmark-Reisezeiten
├── data/
│   ├── bezirksgrenzen.geojson        # Berliner Bezirksgrenzen
│   └── gtfs/                         # GTFS-Daten (nicht im Repo)
└── output/
    ├── fussweg_oepnv_ergebnisse.csv
    └── reisezeiten_landmarks.csv
```

---

## Methodik

### Fußweg-Berechnung

1. **Netzwerk-Extraktion**: OSM-Daten werden mit `pyrosm` geladen und auf Fußwege gefiltert
2. **Gebäude-Snapping**: Gebäudezentroide werden auf das nächste Netzwerk-Node gemappt
3. **Multi-Source Dijkstra**: Kürzeste Pfade von allen Haltestellen zu allen Gebäuden
4. **Aggregation**: Median-Gehzeit pro Bezirk und Verkehrsmittel

**Annahmen:**
- Gehgeschwindigkeit: 1.0 m/s (3.6 km/h)
- Ausreißer-Filter: Werte >= 30 Minuten werden ausgeschlossen
- Koordinatensystem: EPSG:32633 (UTM Zone 33N)

### Landmark-Reisezeiten

- **Verkehrsmittel**: Auto, Fuß, ÖPNV
- **Abfahrtszeit**: Aktueller Zeitpunkt (verkehrsabhängig)
- **Quelle**: Google Maps Distance Matrix API

---

## Lizenz

MIT License - siehe [LICENSE](LICENSE)

---

## Bekannte Einschränkungen

- **Fehlende Werte**: Einige Bezirke zeigen keine Daten für bestimmte Verkehrsmittel (z.B. Neukölln ohne S-Bahn, Spandau ohne Tram). Dies entspricht der tatsächlichen ÖPNV-Infrastruktur – nicht alle Verkehrsmittel sind in allen Bezirken verfügbar.
- **Datenaktualität**: Die Ergebnisse basieren auf GTFS-Daten eines bestimmten Stichtags und können von aktuellen Fahrplänen abweichen.
- **Netzwerk-Snapping**: Gebäude ohne direkte Anbindung an das Fußgängernetzwerk werden auf den nächsten Netzwerk-Knoten gemappt, was zu leichten Ungenauigkeiten führen kann.

---

## Nächste Schritte

- [ ] **Datenvalidierung**: Überprüfung der fehlenden Werte und Abgleich mit offiziellen BVG-Netzplänen
- [ ] **Visualisierung**: Interaktive Karten mit Folium zur Darstellung der Erreichbarkeit pro Bezirk
- [ ] **Zeitabhängige Analyse**: Untersuchung der Erreichbarkeit zu verschiedenen Tageszeiten (Rush Hour vs. Nacht)
- [ ] **Erweiterung der Landmarks**: Zusätzliche POIs wie Universitäten, Krankenhäuser und Einkaufszentren
- [ ] **Performance-Optimierung**: Parallelisierung der Dijkstra-Berechnungen für schnellere Durchläufe
- [ ] **Dashboard-Integration**: Anbindung an ein interaktives Web-Dashboard

---

## Autor

**Giovani Goltara**

Entwickelt als Teil eines Stadtplanungs-Dashboards zur Analyse urbaner Zugänglichkeit in Berlin.
