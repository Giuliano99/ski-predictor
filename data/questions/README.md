# Fragen pflegen

Der Spielleiter sammelt die Fragen außerhalb des Predictors und trägt die endgültige Auswahl in [`weekend-questions.md`](weekend-questions.md) ein.

## Ablauf

1. Fragen zum Beispiel über WhatsApp einsammeln.
2. Sechs bis zehn Fragen in `weekend-questions.md` eintragen.
3. Startliste extrahieren.
4. Tipprunde mit `--questions` erzeugen.
5. Website lokal prüfen.

```powershell
python services\results-importer\src\generate_tip_round.py data\result-lists\processed\startliste3.json --questions data\questions\weekend-questions.md --output apps\web\src\data\tip-round.local.json
```

## Fragetypen

Jede Frage benötigt zusätzlich `Rennen`. Mit `Rennen: ALLE` gilt sie für alle Rennen des Wochenendes. Mehrere konkrete Rennen werden mit `|` getrennt. Die Namen müssen exakt den Rennnamen aus der Wochenendübersicht entsprechen.

Formuliere zusätzlich bereits in der Überschrift eindeutig, ob die Frage das ganze Wochenende oder einen bestimmten Tag, Bewerb und eine bestimmte Disziplin betrifft. Eine optionale feste `ID` verhindert, dass bereits exportierte Tipps ungültig werden, wenn nur der Fragetext präzisiert wird. Nach Beginn der Tippabgabe darf diese ID nicht mehr geändert werden.

`Auswertung` legt fest, welche offizielle Kennzahl verwendet wird. Für Anzahl sind `PODIUMSPLAETZE`, `TOP_10` und `GEWERTETE` möglich. Für Person sind `BESTES_ERGEBNIS` und `GERINGSTER_RUECKSTAND` möglich. Die übrigen Typen verwenden die gleichnamige Auswertung aus den Vorlagen.

### Anzahl

```markdown
## Wie viele Podiumsplätze erreicht Oberhaching?
ID: podium-count-weekend
Typ: ANZAHL
Auswertung: PODIUMSPLAETZE
Rennen: ALLE
Hinweis: Alle Rennen zusammen
Minimum: 0
Maximum: 20
```

### Person

`Personen: ALLE` bietet alle Oberhachinger Starter zur Auswahl an.

```markdown
## Wer erzielt das beste Ergebnis?
Typ: PERSON
Auswertung: BESTES_ERGEBNIS
Rennen: ALLE
Hinweis: Es zählt die offizielle Platzierung
Personen: ALLE
```

### Platzierung

```markdown
## Welche Platzierung erreicht Anna M.?
Typ: PLATZIERUNG
Auswertung: PLATZIERUNG
Rennen: SVM U12 Cup
Hinweis: Es zählt die offizielle Platzierung
Person: Anna M.
Minimum: 1
Maximum: 40
```

### Direktvergleich

```markdown
## Wer gewinnt den direkten Vergleich?
Typ: DUELL
Auswertung: DIREKTVERGLEICH
Rennen: SVM U12 Cup
Hinweis: Es zählt die offizielle Platzierung
Personen: Anna M. | Lea K.
```

### Reihenfolge oder Podium

```markdown
## Wie lautet die interne Reihenfolge?
Typ: REIHENFOLGE
Auswertung: INTERNE_REIHENFOLGE
Rennen: SVM U12 Cup
Hinweis: Es zählt das offizielle Gesamtergebnis
Personen: Anna M. | Lea K. | Emilia S.
Positionen: 3
```

Der Generator bricht mit einer verständlichen Fehlermeldung ab, wenn ein Anzeigename nicht in der Startliste vorkommt, doppeldeutig ist oder die Anzahl der Fragen nicht zwischen sechs und zehn liegt.
