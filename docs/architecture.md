# Architektur

## Zielbild

Ski Predictor wird als kleines Monorepo aufgebaut. Jeder ausführbare Teil erhält einen eigenen Bereich. Gemeinsame Fachlogik wird nicht an eine bestimmte Anwendung gebunden.

```text
apps/web ───────────────┐
apps/game-master ───────┼──► services/api ──► Datenbank
weitere Projekte ───────┘          │
                                   ▼
                            Dokumentenspeicher
                         Startlisten und Ergebnisse

services/results-importer liest Dokumente über dieselbe Speichergrenze,
normalisiert sie und liefert strukturierte Daten an die API.
```

## Verantwortlichkeiten

### Web

Zeigt Rennen, ermöglicht Tipps und stellt Ranglisten dar. Der aktuelle MVP nutzt noch lokale JSON-Ausgaben. Der spätere Datenzugriff erfolgt ausschließlich über die API.

### API

Stellt bereits einen neutralen, nur lesenden Dokumentenkatalog bereit. Er liefert portable Metadaten und Original-PDFs, ohne lokale Dateipfade offenzulegen. Später übernimmt die API zusätzlich Tippabgabe, strukturierte Renndaten, Auswertung, Ranglisten und Anmeldung.

### Results Importer

Liest Startlisten und Ergebnisse aus dem externen Dokumentenspeicher ein. Er validiert und normalisiert die Daten. Die PDFs bleiben im Storage; nur Metadaten und fachlich strukturierte Inhalte werden später in der Datenbank gespeichert.

### Domain

Enthält gemeinsame Datentypen und Regeln. Besonders die Punkteberechnung sollte nur an einer Stelle definiert werden.

## Sinnvolle nächste Schritte

1. Dokumenten API als gemeinsame Quelle stabilisieren
2. Spielleiter Oberfläche über die Backend API betreiben
3. Öffentliche Website über die Backend API versorgen
4. Strukturierte Renn- und Ergebnisdaten in PostgreSQL speichern
5. Anmeldung und Rollen ergänzen
