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

## Lokale Datenbank und API

Die Migration `005_athlete_analytics` speichert freigegebene Ranglisten- und Rennanzahlstände relational. Der bestehende Importablauf erkennt beide Dokumenttypen, erzeugt einen Prüfbericht und übernimmt sie erst nach der Freigabe. Die DSV-ID wird dabei mit der bestehenden internen Athletenidentität verknüpft.

Das Athletenprofil ist über folgende lokale API-Routen verfügbar:

- `GET /api/v1/athletes/{athleteId}` für alle zugeordneten Rohansichten
- `GET /api/v1/athletes/{athleteId}/rankings` für Ranglistenstände
- `GET /api/v1/athletes/{athleteId}/race-counts` für veröffentlichte Rennanzahlstände
- `GET /api/v1/athletes/{athleteId}/analytics` für die saisonweise aufbereitete Übersicht

Die Analytics-Antwort unterscheidet die in der eigenen Datenbasis vorhandenen Rennstarts von der offiziell veröffentlichten Rennanzahl. Eine Punkteveränderung wird erst berechnet, wenn mindestens zwei Ranglistenstände derselben Saison vorliegen.

## Nächste Ausbaustufen

Die lokale U14/U16-Athletenseite ist unter `/athleten/` erreichbar. Sie bietet eine mobile Athletenauswahl, Saisonfilter, Kennzahlen, Rennergebnisse und einen vorbereiteten Punkteverlauf. Der Zugriff verwendet dieselbe Spielleiter-Anmeldung.

Im Spielleiterportal können DSV-Ranglisten und Rennanzahl-Listen mit Saisonangabe hochgeladen werden. Die Datei wird automatisch im externen Datenspeicher abgelegt und ausgelesen. Erst die Kontrolle und Freigabe des Prüfberichts bleibt manuell.

Als nächste Ausbaustufen bleiben:

1. Weitere Ranglistenstände derselben Saison importieren, damit die Entwicklung aus echten Stützpunkten besteht.
2. Athletenvergleich und Filter nach Altersklasse ergänzen.
3. Nach fachlicher Abnahme entscheiden, ob ausgewählte Profile öffentlich oder weiterhin nur intern sichtbar sein sollen.

## Geplantes Athletenprofil

Das erste Profil zeigt pro Saison:

- gewertete Rennergebnisse und Status
- Rennen mit Start im ersten Lauf als belastbare Rennteilnahmen
- DSV-Rennpunkte je Rennen
- Verlauf der veröffentlichten Listenpunkte
- Rang in Deutschland, Altersklasse und Jahrgang, sofern im jeweiligen Ranglistenausschnitt enthalten
- Quelle und Stichtag jedes abgeleiteten Werts

Punktveränderungen werden nur zwischen zwei veröffentlichten Listenständen derselben Saison berechnet. Ein einzelner Listenstand ergibt noch keinen Verlauf.
