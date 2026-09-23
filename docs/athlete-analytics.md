# Athletenübersicht U14/U16

Die Athletenübersicht wird als eigener Anwendungsfall auf der gemeinsamen Renndatenbasis aufgebaut. Das Tippspiel bleibt ein Verbraucher dieser Daten und bestimmt nicht deren Struktur.

## Fachliche Trennung

Alle Werte werden mit Saison und Stichtag gespeichert. Werte aus verschiedenen Saisons dürfen nicht als derselbe Stand zusammengeführt werden.

- Rennergebnis: Platz, Status, Laufzeiten, Gesamtzeit, Rückstand und DSV-Rennpunkte eines konkreten Rennens
- Ranglistenstand: Basiswert, Listenpunkte und veröffentlichte Ränge eines bestimmten DSV-Listenstands
- Rennanzahlstand: veröffentlichte Anzahl absolvierter Rennen zu einem Stichtag

Eine fehlende Person in einer Rennanzahl-Liste bedeutet nicht null Rennen. Die vorliegende Liste enthält für U14 nur Personen ab 17 und für U16 nur Personen ab 19 Rennen.

## Identität

Die DSV-ID ist der führende externe Schlüssel. Name, Verein und Jahrgang sind veränderliche Merkmale und eignen sich nicht als alleiniger Schlüssel. Bestehende interne Athleten-IDs bleiben erhalten und werden mit der DSV-ID verknüpft.

## Bereits umgesetzter Import

`extract_dsv_snapshot.py` erkennt automatisch DSV-Ranglisten und DSV-Rennanzahl-Listen. Der Import speichert:

- SHA-256-Prüfsumme, Dateiname, Format und Seitenzahl
- vollständigen extrahierten PDF-Rohtext
- Dokumentkennung, Saison und Stichtag
- normalisierte Zeilen mit DSV-ID, Namen, Jahrgang, Verein und Verband
- Basiswert, Listenpunkte und veröffentlichte Ränge beziehungsweise Rennanzahl
- Abdeckungsinformation für unvollständige Rennanzahl-Listen

Beispiel:

```powershell
python services/results-importer/src/extract_dsv_snapshot.py "C:\Pfad\DSVSA2638_ Ranglisten.pdf" --output data/result-lists/processed/dsv-ranking-2026-09-13.json
```

Der Import ist zunächst bewusst vom normalen Spielleiter-Workflow getrennt.

## Nächste Ausbaustufen

1. Neue Datenbanktabellen für versionierte Ranglisten- und Rennanzahl-Snapshots ergänzen.
2. Freigabeprozess der bestehenden Import-API auf die neuen Dokumenttypen erweitern.
3. DSV-ID beim Freigeben mit der internen Athletenidentität verknüpfen.
4. API-Endpunkt für ein Athletenprofil mit Ergebnissen, Punktentwicklung und Ranglistenverlauf ergänzen.
5. Eine einfache U14/U16-Athletenseite bauen und erst danach Diagramme und Vergleichsfunktionen ergänzen.

## Geplantes Athletenprofil

Das erste Profil zeigt pro Saison:

- gewertete Rennergebnisse und Status
- Rennen mit Start im ersten Lauf als belastbare Rennteilnahmen
- DSV-Rennpunkte je Rennen
- Verlauf der veröffentlichten Listenpunkte
- Rang in Deutschland, Altersklasse und Jahrgang, sofern im jeweiligen Ranglistenausschnitt enthalten
- Quelle und Stichtag jedes abgeleiteten Werts

Punktveränderungen werden nur zwischen zwei veröffentlichten Listenständen derselben Saison berechnet. Ein einzelner Listenstand ergibt noch keinen Verlauf.
