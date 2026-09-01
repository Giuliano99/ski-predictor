# Fachliches Datenmodell

Dieses Dokument beschreibt den ersten technischen Entwurf. Die verbindlichen Spielregeln stehen in [`product.md`](product.md).

## Beziehungen

```text
Saison
  └── Veranstaltung
        └── Rennen
              ├── Starterfeld
              └── Ergebnis

Tipprunde
  ├── ein oder mehrere Rennen
  ├── sechs bis zehn Tippfragen
  └── Tippabgaben

Team
  └── mehrere Tippende
```

## Zentrale Objekte

### Athlete

Eine Athletin oder ein Athlet des Skiteams Oberhaching. Für den lokalen MVP reicht ein Anzeigename. Geburtsjahr und Altersklasse werden getrennt gespeichert, weil sich die Altersklasse zwischen Saisons ändern kann.

### Event

Eine Veranstaltung oder ein Rennwochenende. Beispiele sind ein SVM Wochenende oder eine Landkreisveranstaltung.

### Race

Ein einzelnes wertbares Rennen innerhalb einer Veranstaltung. Altersklasse, Disziplin, Startzeit und Anzahl der Läufe gehören zum Rennen.

### StartList

Die offizielle Startliste wird vor dem Rennwochenende eingelesen. Sie enthält Wertungsgruppen und alle gemeldeten Starter. Für das Tippspiel werden daraus ausschließlich die Athletinnen und Athleten des Skiteams Oberhaching als auswählbare Optionen übernommen.

Eine Starterposition enthält Startnummer, vollständigen Namen für die interne Zuordnung, gekürzten Anzeigenamen, Jahrgang, Verein und optional externe Athleten-ID, Verband und Setzpunkte. Vollständige Namen bleiben in lokalen Importdaten. Die Oberfläche verwendet ausschließlich `Vorname N.`.

### RaceResult

Das offizielle Ergebnis eines Rennens. Ein Ergebnis besteht aus einer oder mehreren Wertungsgruppen. Für jede Wertungsgruppe werden mindestens die Siegerzeit, die langsamste gewertete Zeit und die Ergebnisse der Oberhachinger Athleten benötigt.

Die offizielle Ergebniszeit und Platzierung sind maßgeblich. Einzellaufzeiten werden getrennt gespeichert und nicht zur Neuberechnung der offiziellen Wertung verwendet.

Der erste Ergebnisimport unterstützt die beiden vorliegenden Race Horology Varianten mit und ohne externe Athleten-ID. Eine Ergebnisdatei wird über Bewerbsnummer beziehungsweise Startlisten-Datei einem Rennen zugeordnet. Vollständige lokale Ergebnisdaten bleiben von Git ausgeschlossen.

### TipRound

Die spielbare Einheit eines Wochenendes. Sie verbindet Rennen, Abgabeschluss und sechs bis zehn Tippfragen.

Die auswählbaren Athleten einer Tipprunde werden als Snapshot aus der zuletzt geprüften Startliste übernommen. Aktualisierte Startlisten dürfen den Snapshot nur vor dem Abgabeschluss ersetzen.

### TipQuestion

Eine einzelne Frage mit Tippart, Geltungsbereich und Auswertungsregel. Jede Frage verweist verpflichtend auf ein oder mehrere Rennen. Wochenendfragen verweisen auf alle Rennen der Tipprunde. Die erste Version unterstützt Anzahl, Personenauswahl, interne Reihenfolge, Platzierung, Direktvergleich und Podium.

Die ausgewählten Fragen werden vom Spielleiter in einer Markdown Datei gepflegt. Der Generator löst gekürzte Anzeigenamen gegen das Starterfeld auf, validiert Typ und Parameter und übernimmt die Fragen in die Tipprunde. Die Markdown Datei ist redaktionelle Eingabe und kein Teil der Predictor Website.

### TipSubmission

Die vollständige Tippabgabe einer Person für eine Tipprunde. Bis zur späteren Anmeldung verwendet der MVP lokale Demo-IDs.

### Team

Eine Gruppe von Tippenden. Die Teamwertung verwendet den Durchschnitt der Wochenendpunkte aller zum Abgabeschluss zugeordneten Mitglieder.

## Ergebnisstatus

`CLASSIFIED` bezeichnet einen regulär gewerteten Lauf. `DNS`, `DNF` und `DSQ` bezeichnen gleichermaßen einen nicht gewerteten Lauf. Die ursprünglichen Statuswerte bleiben trotzdem erhalten, damit das Ergebnis korrekt dargestellt werden kann.

## Noch benötigte Informationen

Die fünf Beispiel-Ergebnislisten sind in [`result-list-analysis.md`](result-list-analysis.md) zusammengefasst. Die drei Startlisten und ihre Extraktion sind in [`start-list-analysis.md`](start-list-analysis.md) dokumentiert. Für den realistischen Abnahmetest fehlt noch ein echtes vollständiges Rennwochenende, insbesondere mit einer U8- oder U10-Wertung nach dem besten Lauf.

## Ablauf vor dem Rennwochenende

1. Startlisten-PDF lokal ablegen
2. PDF automatisch in normalisiertes JSON extrahieren
3. Veranstaltungsdaten und Wertungsgruppen prüfen
4. Vereinsnamen normalisieren
5. Oberhachinger Starter prüfen
6. Athleten über externe ID oder Ersatzschlüssel zuordnen
7. Generator erzeugt Starter-Snapshot, Frist und sechs bis zehn Fragen als Entwurf
8. Entwurf fachlich prüfen und bei Bedarf Fragen anpassen
9. Geprüfte Tipprunde für die Website freigeben

Wenn keine externe Athleten-ID vorhanden ist, wird vorläufig ein Ersatzschlüssel aus normalisiertem Namen, Jahrgang und Verein verwendet. Diese Zuordnung muss bei Namensabweichungen manuell bestätigt werden.
