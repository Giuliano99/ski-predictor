# Architektur

## Zielbild

Ski Predictor wird als kleines Monorepo aufgebaut. Jeder ausführbare Teil erhält einen eigenen Bereich. Gemeinsame Fachlogik wird nicht an eine bestimmte Anwendung gebunden.

```text
Browser
   │
   ▼
apps/web
   │
   ▼
services/api ──────► Datenbank
   ▲
   │
services/results-importer ──────► Externe Ergebnisquelle

packages/domain wird von Web, API und Importer gemeinsam genutzt.
```

## Verantwortlichkeiten

### Web

Zeigt Rennen, ermöglicht Tipps und stellt Ranglisten dar. Der aktuelle MVP nutzt ausschließlich lokale Demo Daten.

### API

Übernimmt später Anmeldung, Datenzugriff, Tippabgabe, Auswertung und Ranglisten.

### Results Importer

Liest später Starterlisten und Ergebnisse aus einer externen Quelle ein. Er validiert und normalisiert die Daten, bevor sie über die API oder direkt über eine interne Schnittstelle gespeichert werden.

### Domain

Enthält gemeinsame Datentypen und Regeln. Besonders die Punkteberechnung sollte nur an einer Stelle definiert werden.

## Sinnvolle nächste Schritte

1. Fachliche Anforderungen und Punkteberechnung festlegen
2. Web MVP in wiederverwendbare Komponenten aufteilen
3. API Vertrag definieren
4. Anmeldung und persistente Speicherung ergänzen
5. Ergebnisquelle auswählen und Importer umsetzen
