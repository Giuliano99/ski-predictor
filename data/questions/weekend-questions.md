# Fragen für das Rennwochenende

<!--
Dieses Blatt wird vom Spielleiter gepflegt.

Jede Frage beginnt mit ##. Erlaubte Typen:
ANZAHL, PERSON, PLATZIERUNG, DUELL, REIHENFOLGE und PODIUM.

Personen werden mit dem gekürzten Anzeigenamen aus der Startliste eingetragen.
Mehrere Personen werden mit | getrennt. ALLE wählt alle Oberhachinger Starter aus.
Rennen: ALLE gilt für das gesamte Wochenende. Einzelne Rennnamen werden mit | getrennt.
Die Rennnamen müssen exakt den Namen aus der erzeugten Wochenendübersicht entsprechen.
Das Blatt muss mindestens 6 und höchstens 10 Fragen enthalten.

KOPIERVORLAGEN
================

Kopiere die gewünschte Vorlage unterhalb dieses Kommentarblocks und passe sie an.
Die Beispielnamen müssen exakt durch Anzeigenamen aus der aktuellen Startliste ersetzt werden.

1. ANZAHL
---------

## Wie viele Podiumsplätze erreicht Oberhaching?
Typ: ANZAHL
Auswertung: PODIUMSPLAETZE
Rennen: ALLE
Hinweis: Alle Rennen des Wochenendes zusammen
Minimum: 0
Maximum: 20

2. PERSON
----------

## Wer erzielt das beste Ergebnis des Wochenendes?
Typ: PERSON
Auswertung: BESTES_ERGEBNIS
Rennen: ALLE
Hinweis: Verglichen wird die offizielle Platzierung
Personen: ALLE

Statt ALLE kann die Auswahl eingeschränkt werden:
Personen: Anna M. | Lea K. | Emilia S.

3. PLATZIERUNG
---------------

## Welche Platzierung erreicht Anna M.?
Typ: PLATZIERUNG
Auswertung: PLATZIERUNG
Rennen: SVM U12 Cup
Hinweis: Es zählt die offizielle Platzierung in ihrer Wertungsgruppe
Person: Anna M.
Minimum: 1
Maximum: 40

4. DUELL
--------

## Wer gewinnt den direkten Vergleich?
Typ: DUELL
Auswertung: DIREKTVERGLEICH
Rennen: SVM U12 Cup
Hinweis: Es zählt das offizielle Gesamtergebnis
Personen: Anna M. | Lea K.

5. REIHENFOLGE
---------------

## Wie lautet die interne Reihenfolge der Oberhachinger Starter?
Typ: REIHENFOLGE
Auswertung: INTERNE_REIHENFOLGE
Rennen: SVM U12 Cup
Hinweis: Ordne die Personen nach dem offiziellen Gesamtergebnis
Personen: Anna M. | Lea K. | Emilia S.
Positionen: 3

6. PODIUM
---------

## Wie sieht das interne Oberhachinger Podium aus?
Typ: PODIUM
Auswertung: INTERNES_PODIUM
Rennen: ALLE
Hinweis: Über alle Rennen nach bestem prozentualen Rückstand
Personen: ALLE
Positionen: 3
-->

## Wie viele Podiumsplätze erreicht Oberhaching am gesamten Wochenende?
Typ: ANZAHL
Auswertung: PODIUMSPLAETZE
Rennen: ALLE
Hinweis: Alle Wertungsgruppen der ausgewählten Rennen zusammen
Minimum: 0
Maximum: 20

## Wie viele Top 10 Ergebnisse erzielt Oberhaching?
Typ: ANZAHL
Auswertung: TOP_10
Grenze: 10
Rennen: ALLE
Hinweis: Am gesamten Wochenende ist jeweils das offizielle Gesamtergebnis maßgeblich
Minimum: 0
Maximum: 30

## Wer erzielt das beste Ergebnis des Rennwochenendes?
Typ: PERSON
Auswertung: BESTES_ERGEBNIS
Rennen: ALLE
Hinweis: Verglichen wird zunächst die offizielle Platzierung
Personen: ALLE

## Wer hat den geringsten prozentualen Rückstand?
Typ: PERSON
Auswertung: GERINGSTER_RUECKSTAND
Rennen: ALLE
Hinweis: Am gesamten Wochenende macht der prozentuale Rückstand unterschiedliche Wertungsgruppen vergleichbar
Personen: ALLE

## Wie sieht das interne Oberhachinger Podium aus?
Typ: PODIUM
Auswertung: INTERNES_PODIUM
Rennen: ALLE
Hinweis: Über alle Rennen nach bestem prozentualen Rückstand
Personen: ALLE
Positionen: 3

## Wie viele Oberhachinger Starter kommen in die Wertung?
Typ: ANZAHL
Auswertung: GEWERTETE
Rennen: ALLE
Hinweis: Am gesamten Wochenende gelten DNS, DNF und DSQ nicht als gewertet
Minimum: 0
Maximum: 30

## Welche Platzierung erreicht Clara S.?
Typ: PLATZIERUNG
Auswertung: PLATZIERUNG
Rennen: MINI München Cup 2 Willi-Wein-Gedächtnisrennen RS
Hinweis: Am Samstag im Riesenslalom des MINI München Cups zählt die offizielle Platzierung in der Wertungsgruppe U14 weiblich Jahrgang 2013
Person: Clara S.
Minimum: 1
Maximum: 40

## Wer gewinnt den direkten Vergleich zwischen Alexander T. und Simon P.?
Typ: DUELL
Auswertung: DIREKTVERGLEICH
Rennen: MINI München Cup 2 Willi-Wein-Gedächtnisrennen RS
Hinweis: Am Samstag im Riesenslalom des MINI München Cups zählt das offizielle Gesamtergebnis in der gemeinsamen Wertungsgruppe
Personen: Alexander T. | Simon P.

## Wie lautet die interne Reihenfolge der U14 weiblich Jahrgang 2012?
Typ: REIHENFOLGE
Auswertung: INTERNE_REIHENFOLGE
Rennen: MINI München Cup 2 Willi-Wein-Gedächtnisrennen RS
Hinweis: Ordne die Oberhachinger Starterinnen am Samstag im Riesenslalom des MINI München Cups nach dem offiziellen Gesamtergebnis
Personen: Marlene E. | Marlene W. | Lea R.
Positionen: 3
