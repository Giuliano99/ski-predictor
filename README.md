# Ski Predictor

Ski Predictor ist ein Tippspiel für Ski Rennen. Aktuell enthält das Repository einen statischen Website MVP mit Demo Daten.

## Projektstruktur

```text
ski-predictor/
├── apps/
│   └── web/                 Öffentliche Website
├── services/
│   ├── api/                 Spätere Anwendungsschnittstelle
│   └── results-importer/    Späterer Ergebnisimport
├── packages/
│   └── domain/              Gemeinsame Fachlogik und Datentypen
└── docs/                    Architektur und Produktentscheidungen
```

Die Struktur trennt auslieferbare Anwendungen, Hintergrunddienste und gemeinsam genutzten Code. Noch nicht umgesetzte Bereiche enthalten lediglich eine kurze Beschreibung ihres späteren Zwecks.

## MVP lokal starten

```powershell
cd apps/web
python -m http.server 4173
```

Danach ist die Website unter `http://localhost:4173` erreichbar.

## Aktueller Umfang

* Übersicht des nächsten Rennens
* Tippabgabe für ein Podium mit Validierung
* Demo Rangliste
* Karten für kommende Rennen
* Responsive Darstellung

Anmeldung, Datenbank und automatischer Ergebnisimport sind bewusst noch nicht implementiert.

Weitere Informationen stehen in [docs/architecture.md](docs/architecture.md).
