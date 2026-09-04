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

Zeigt Rennen, ermöglicht Tipps und stellt Ranglisten dar. Tipprunden, Auswertungen, Ranglisten und Tippabgaben laufen im normalen Betrieb bereits über die API. Lokale JSON-Ausgaben bleiben nur als Rückfall erhalten.

### API

Stellt einen neutralen Dokumentenkatalog bereit. Er liefert portable Metadaten und Original-PDFs, ohne lokale Dateipfade offenzulegen. Persistente Extraktionsaufträge erzeugen Rohdaten, normalisierte Renndaten und Prüfberichte. Nur vom Spielleiter freigegebene Daten werden über die allgemeinen Event- und Rennen-Endpunkte veröffentlicht. Tippabgabe, Auswertung und Ranglisten laufen ebenfalls über diese API.

### Results Importer

Liest Startlisten und Ergebnisse aus dem externen Dokumentenspeicher ein. Er validiert und normalisiert die Daten. Die PDFs bleiben im Storage; nur Metadaten und fachlich strukturierte Inhalte werden später in der Datenbank gespeichert.

### Domain

Enthält gemeinsame Datentypen und Regeln. Besonders die Punkteberechnung sollte nur an einer Stelle definiert werden.

### Athletenidentität

Die API führt eine kanonische Athletenkartei. Externe Verbandscodes sind starke Identifikatoren; ohne Code dienen normalisierter Name, Geburtsjahr und Verein als stabiler fachlicher Schlüssel. Ähnlichkeitstreffer erfordern eine Spielleiterprüfung. Manuelle Zusammenführungen werden als Weiterleitung gespeichert, sodass bereits erzeugte Rennartefakte nicht verändert werden müssen. Beim späteren Datenbankwechsel werden Athleten, externe Kennungen, Aliase und Weiterleitungen in getrennte Tabellen übernommen.

## Nächste Ausbaustufen

1. Extraktionen an mehreren echten Rennwochenenden fachlich prüfen
2. Dokumentübergreifende Athletenidentität stabilisieren
3. Dateibasierte Extraktionsablage durch PostgreSQL ersetzen
4. Externen Cloud-Speicher anbinden
5. Anmeldung und Rollen ergänzen
