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
├── data/
│   └── questions/           Vom Spielleiter gepflegte Wochenendfragen
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

Das fachliche Zielbild und das vorgeschlagene Punktesystem stehen in [docs/product.md](docs/product.md).

Lokale Ergebnislisten können unter `data/result-lists/inbox` abgelegt werden. Der Ordnerinhalt wird aus Datenschutzgründen nicht in Git übernommen.

Die daraus abgeleiteten Format- und Importregeln stehen in [docs/result-list-analysis.md](docs/result-list-analysis.md).

Startlisten können mit `services/results-importer/src/extract_start_list.py` automatisch in lokales JSON überführt werden. Die analysierten Formate stehen in [docs/start-list-analysis.md](docs/start-list-analysis.md).

Die endgültigen Fragen eines Rennwochenendes werden vom Spielleiter in [`data/questions/weekend-questions.md`](data/questions/weekend-questions.md) gepflegt. Eine Anleitung und Beispiele für alle Fragetypen stehen in [`data/questions/README.md`](data/questions/README.md).
