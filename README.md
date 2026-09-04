# Ski Predictor

Die vollständige Anleitung für die Durchführung eines Rennwochenendes steht in [SPIELLEITER.md](SPIELLEITER.md).

Ski Predictor ist ein Tippspiel für Ski Rennen. Aktuell enthält das Repository einen statischen Website MVP mit Demo Daten.

## Projektstruktur

```text
ski-predictor/
├── apps/
│   └── web/                 Öffentliche Website
├── services/
│   ├── api/                 Backend, PDF-Extraktion und gemeinsame Renndaten
│   └── results-importer/    Parser und fachliche Ergebnisverarbeitung
├── packages/
│   └── domain/              Gemeinsame Fachlogik und Datentypen
├── config/
│   └── weekends/            Konfiguration pro Rennwochenende
├── scripts/
│   └── game-master/         Automatisierter Spielleiter Workflow
├── data/
│   └── questions/           Vom Spielleiter gepflegte Wochenendfragen
└── docs/                    Architektur und Produktentscheidungen
```

Die Struktur trennt auslieferbare Anwendungen, Hintergrunddienste und gemeinsam genutzten Code. Noch nicht umgesetzte Bereiche enthalten lediglich eine kurze Beschreibung ihres späteren Zwecks.

## MVP lokal starten

```powershell
.\scripts\game-master\Start-Dashboard.ps1
```

Danach sind die Website unter `http://127.0.0.1:4175/tippspiel/`, die Spielleiter-Oberfläche unter `http://127.0.0.1:4175/spielleiter/` und die API-Dokumentation unter `http://127.0.0.1:4175/` erreichbar.

## Spielleiter Oberfläche

Der vollständige Ablauf kann über ein lokales Dashboard bedient werden:

```powershell
.\scripts\game-master\Start-Dashboard.ps1
```

Die Oberfläche öffnet sich unter `http://127.0.0.1:4175/spielleiter/`. Dort können Wochenenden angelegt, Fragen bearbeitet sowie Startlisten, Tippabgaben und Ergebnisse ausgewählt werden. Import, Zuordnung, Prüfung, Auswertung und Saisonwertung laufen über die gemeinsame Backend API automatisch.

## Spielleiter Workflow per PowerShell

Das aktuelle Testwochenende vom 7. und 8. März 2026 wird mit zwei Befehlen vorbereitet und später ausgewertet:

```powershell
.\scripts\game-master\Prepare-Weekend.ps1
.\scripts\game-master\Evaluate-Weekend.ps1
```

Die Auswertung wird erst ausgeführt, sobald die sechs Ergebnislisten in der Wochenendkonfiguration ergänzt wurden.

Details zur Oberfläche stehen in [`apps/game-master/README.md`](apps/game-master/README.md). Die einzelnen Befehle und der sichere `-WhatIf` Modus stehen in [`scripts/game-master/README.md`](scripts/game-master/README.md).

## Aktueller Umfang

* Übersicht des nächsten Rennens
* konfigurierbare Tippfragen mit Validierung
* validiertes Speichern der Tippabgaben über die lokale Backend API
* automatischer Import von Start- und Ergebnislisten
* persistente PDF-Extraktionsaufträge mit Prüfbericht und Freigabe
* allgemeine API für freigegebene Veranstaltungen und Rennen
* Wochenend- und Saisonrangliste
* Karten für kommende Rennen
* Responsive Darstellung

Anmeldung und Datenbank sind bewusst noch nicht implementiert.

Weitere Informationen stehen in [docs/architecture.md](docs/architecture.md).

## Gemeinsame Dokumenten API

Start- und Ergebnislisten können auch von anderen lokalen Projekten über eine neutrale Backend API gelesen werden:

```powershell
.\scripts\game-master\Start-Backend.ps1
```

Die API-Dokumentation ist anschließend unter `http://127.0.0.1:4175` erreichbar. Details stehen in [services/api/README.md](services/api/README.md).

Das fachliche Zielbild und das vorgeschlagene Punktesystem stehen in [docs/product.md](docs/product.md).

Lokale Ergebnislisten können unter `data/result-lists/inbox` abgelegt werden. Der Ordnerinhalt wird aus Datenschutzgründen nicht in Git übernommen.

Die daraus abgeleiteten Format- und Importregeln stehen in [docs/result-list-analysis.md](docs/result-list-analysis.md).

Startlisten können mit `services/results-importer/src/extract_start_list.py` automatisch in lokales JSON überführt werden. Die analysierten Formate stehen in [docs/start-list-analysis.md](docs/start-list-analysis.md).

Die endgültigen Fragen eines Rennwochenendes werden vom Spielleiter in [`data/questions/weekend-questions.md`](data/questions/weekend-questions.md) gepflegt. Eine Anleitung und Beispiele für alle Fragetypen stehen in [`data/questions/README.md`](data/questions/README.md).
