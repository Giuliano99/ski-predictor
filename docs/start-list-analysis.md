# Analyse der Beispiel-Startlisten

Analysiert wurden drei textbasierte PDF Startlisten. Dieses Dokument enthält keine Namen oder individuellen Meldedaten.

## Erkannte Varianten

| Variante | Wertungsgruppen | Starter | Oberhaching | Besondere Felder |
| --- | ---: | ---: | ---: | --- |
| DSValpin | 4 | 123 | 8 | DSV-ID und Verband |
| Race Horology einfach | 4 | 76 | 10 | keine externe Athleten-ID |
| Race Horology mit Code | 6 | 153 | 13 | Code, Verband und Setzpunkte |

Die drei Dateien decken unterschiedliche Positionen der Spalten und unterschiedliche Schreibweisen der Gruppenüberschriften ab.

## Benötigte Informationen vor einer Tipprunde

Aus einer Startliste werden folgende Daten übernommen:

* Veranstaltung und Datum
* Ort und Bewerbsnummer, sofern vorhanden
* Wertungsgruppen
* Startnummer
* vollständiger Name zur internen Zuordnung
* gekürzter Anzeigename für die Oberfläche
* Jahrgang
* Verein
* externe Athleten-ID, sofern vorhanden
* Verband und Setzpunkte, sofern vorhanden

## Automatische Erkennung

Der Extraktor erkennt das Quellsystem anhand der PDF Überschriften und Tabellenspalten. Anschließend verarbeitet er jede Zeile innerhalb der erkannten Wertungsgruppe.

Die Anzeigeform wird aus dem Namen als `Vorname N.` erzeugt. Vereinsvarianten wie `Skiteam Oberhaching e.V.` werden auf `Skiteam Oberhaching` normalisiert. `TSV Oberhaching` bleibt ein anderer Verein.

## Zuordnung zu bestehenden Athleten

Eine externe DSV-ID beziehungsweise ein Code ist der bevorzugte Schlüssel. Fehlt dieser wie in einer der Race Horology Varianten, wird ein lokaler Ersatzschlüssel aus normalisiertem vollständigem Namen, Jahrgang und Verein gebildet. Ersatzschlüssel müssen vor einer automatischen Zusammenführung geprüft werden.

## Workflow

```text
Startlisten-PDF
  → Textextraktion
  → Formaterkennung
  → Wertungsgruppen und Starter parsen
  → Vereinsnamen normalisieren
  → Oberhachinger Starter markieren
  → lokales JSON speichern
  → fachliche Prüfung
  → Starter-Snapshot der Tipprunde erzeugen
```

## Grenzen des ersten Extraktors

* Er verarbeitet textbasierte PDFs. Gescannte Bild-PDFs benötigen später OCR.
* Neue Layoutvarianten können einen zusätzlichen Parser benötigen.
* Eine fehlende Bewerbsnummer wird nicht erfunden.
* Der Extraktor entscheidet noch nicht automatisch, welche Tippfragen erzeugt werden.
* Vor Veröffentlichung einer Tipprunde bleibt eine kurze fachliche Prüfung erforderlich.
