# Analyse der Beispiel-Ergebnislisten

Analysiert wurden fünf lokale Ergebnislisten aus der Saison 2025/26. Dieses Dokument enthält bewusst keine Namen oder individuellen Ergebnisse.

## Erkannte Formate

| Beispiel | Serie | Altersklassen | Wertungsprinzip |
| --- | --- | --- | --- |
| DSV Schülercup | DSV | U14 | Summe aus zwei Läufen |
| Oberhachinger Meisterschaft | Landkreis und Verein | U8 bis Erwachsene | offiziell ausgewiesene Laufzeit |
| MINI München Cup | SVM | U14 und U16 | Summe aus zwei Läufen |
| SVM Vielseitigkeitslauf | SVM | U8 und U10 | bester gültiger Lauf |
| SVM U8/U10 Cup Slalom | SVM | U8 und U10 | bester gültiger Lauf |

## Gemeinsame Felder

Alle Beispiele enthalten mindestens:

* Veranstaltungsname
* Datum und Ort
* Bewerbsnummer
* Alters- oder Wertungsgruppe
* Rang
* Startnummer
* Name
* Jahrgang
* Verein
* offizielle Laufzeit oder Totalzeit

Je nach Serie kommen Verband, Athleten-Code, Einzellaufzeiten, Zeitdifferenz und Verbandspunkte hinzu.

## Wertungsgruppen

Eine PDF enthält regelmäßig mehrere voneinander unabhängige Wertungsgruppen. Die Trennung erfolgt je nach Rennen über:

* Altersklasse
* Geschlecht beziehungsweise Wettbewerbskategorie
* einzelnen Jahrgang
* Kombination dieser Merkmale

Siegerzeit und Rückstand dürfen deshalb nicht global für die gesamte Datei berechnet werden. Sie gehören immer zu einer einzelnen Wertungsgruppe.

## Laufmodelle

U8- und U10-Listen zeigen häufig zwei Einzellaufzeiten, während die offizielle Laufzeit dem besseren gültigen Lauf entspricht. Ein `DIS` oder `NIZ` in einem Lauf verhindert dort nicht automatisch eine offizielle Klassifizierung, wenn der andere Lauf gültig ist.

Bei U14, U16 und DSV Rennen wird in den Beispielen die Summe beider gültiger Läufe als Total beziehungsweise Laufzeit verwendet. Ein fehlender gültiger Lauf führt dort normalerweise zu keiner offiziellen Platzierung.

Die Importlogik darf das Wertungsprinzip daher nicht allein aus der Anzahl vorhandener Laufspalten ableiten. Maßgeblich sind die offizielle Rangfolge und die offizielle Ergebniszeit.

## Statusabbildung

Die deutschen Kürzel werden beim Import normalisiert:

| Quellenwert | Normalisierter Status |
| --- | --- |
| `NAS` | `DNS` |
| `NIZ` | `DNF` |
| `DIS` | `DSQ` |

Status werden sowohl pro Einzellauf als auch für das offizielle Gesamtergebnis gespeichert. Der Gesamtstatus wird nicht automatisch aus einem einzelnen Laufstatus abgeleitet.

## Vereinszuordnung

Der Vereinsname tritt mindestens als `Skiteam Oberhaching` und `Skiteam Oberhaching e.V.` auf. Beide Werte werden auf eine gemeinsame Vereins-ID normalisiert. Ähnlich klingende Vereine wie `TSV Oberhaching` dürfen nicht automatisch zugeordnet werden.

## Konsequenzen für das Datenmodell

1. Ein Rennen besitzt mehrere Wertungsgruppen.
2. Jede Wertungsgruppe besitzt eine eigene Siegerzeit.
3. Offizielle Ergebniszeit und Einzellaufzeiten werden getrennt gespeichert.
4. Das offizielle Wertungsprinzip wird als Metadatum gespeichert.
5. Ein Eintrag kann trotz ungültigem Einzellauf offiziell klassifiziert sein.
6. Externe Athleten-IDs und Bewerbsnummern werden optional erhalten.
7. Prozentuale Rückstände werden erst nach Zuordnung zur Wertungsgruppe berechnet.
