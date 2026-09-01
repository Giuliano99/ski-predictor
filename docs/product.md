# Fachliches Zielbild

## 1. Produktidee

Ski Predictor ist ein vereinsinternes Tippspiel rund um die Athletinnen und Athleten des Skiteams Oberhaching. Getippt werden nicht nur Podiumsplätze. Jede Rennrunde enthält mehrere abwechslungsreiche Fragen zu den Ergebnissen des Teams.

In der Benutzeroberfläche werden minderjährige Athletinnen und Athleten als Vorname plus erster Buchstabe des Nachnamens angezeigt, beispielsweise `Anna M.`. Vollständige Namen dürfen intern für Import und Zuordnung verarbeitet werden, werden im Tippspiel aber nicht dargestellt.

Das Spiel soll den Rennsport im Verein sichtbarer machen und über eine ganze Saison hinweg eine nachvollziehbare Einzelwertung ermöglichen. Eine spätere Teamwertung kann zusätzlich Gruppen wie Altersklassen oder Trainerteams gegeneinander antreten lassen.

## 2. Umfang der Rennen

### Hauptfokus

* Rennen des Skiverbands München für die Altersklassen U8 bis U16
* Athletinnen und Athleten des Skiteams Oberhaching
* Mehrere Rennen eines Wochenendes werden zu einer gemeinsamen Tipprunde zusammengefasst

### Weitere mögliche Rennen

* Etwa vier Landkreisrennen pro Saison für alle ausgeschriebenen Altersklassen
* Qualifikationsrennen und weiterführende Serien wie Bayernliga
* DSV Wettbewerbe, sofern Athletinnen oder Athleten des Skiteams Oberhaching teilnehmen

Ob ein Rennen Teil des Tippspiels ist, wird pro Veranstaltung festgelegt. Es besteht kein Anspruch darauf, dass jedes Rennen einer Serie berücksichtigt wird.

## 3. Altersklassen und Disziplinen

Der erste Produktumfang unterstützt U8, U10, U12, U14 und U16. Weitere Altersklassen können für Landkreisrennen ergänzt werden.

Die Disziplin wird am einzelnen Rennen hinterlegt. Das Datenmodell darf deshalb keine feste Beschränkung auf Riesenslalom oder Slalom enthalten. Dadurch können später auch Formate wie Kids Cross abgebildet werden.

## 4. Tipprunde

Eine Tipprunde bildet in der Regel ein vollständiges Rennwochenende ab. Sie enthält:

* eine oder mehrere Veranstaltungen
* ein oder mehrere Rennen
* die teilnehmenden Oberhachinger Athletinnen und Athleten
* mehrere Tippfragen
* einen gemeinsamen Abgabeschluss
* einen Status

Abhängig von der Anzahl der Rennen enthält eine Tipprunde normalerweise sechs bis zehn Tippfragen. Die konkrete Zusammenstellung wird für jedes Wochenende festgelegt. Dabei sollen mehrere Tipparten kombiniert werden.

### Auswahl der Fragen

Die Community kann ihre Ideen außerhalb des Predictors an den Spielleiter senden, zunächst zum Beispiel über WhatsApp. Der Spielleiter wählt sechs bis zehn eindeutig auswertbare Fragen aus und trägt sie in der Markdown Datei des Rennwochenendes ein. Der Generator prüft die Datei gegen das Starterfeld und übernimmt die Fragen als Snapshot in die Tipprunde. Die Website selbst enthält keine Fragenverwaltung.

Mögliche Statuswerte sind `Entwurf`, `Offen`, `Geschlossen`, `Ausgewertet`, `Annulliert`.

Das auswählbare Starterfeld wird vor der Öffnung der Tipprunde aus einer offiziellen Startliste übernommen. Im Tippspiel erscheinen nur gemeldete Athletinnen und Athleten des Skiteams Oberhaching. Eine neue Startlistenversion kann das Starterfeld bis zum Abgabeschluss aktualisieren. Danach bleibt der für die Tipprunde gespeicherte Snapshot unverändert.

## 5. Abgabeschluss

Der Abgabeschluss ist standardmäßig Samstag um 00:00 Uhr vor den Rennen. Als Zeitzone gilt `Europe/Berlin`.

Nach dem Abgabeschluss können Tipps weder neu abgegeben noch geändert werden. Der Abgabeschluss wird dennoch pro Tipprunde gespeichert, damit Rennen an anderen Wochentagen oder abweichende Abläufe später möglich bleiben.

## 6. Tipparten

Das System soll unterschiedliche Tipparten unterstützen. Nicht jede Tipprunde muss alle Tipparten enthalten.

Jede Frage nennt sichtbar die Rennen, auf die sie sich bezieht. Bei Fragen nach dem besten Ergebnis oder einer Gesamtzahl am Wochenende werden alle einbezogenen Rennen aufgeführt beziehungsweise als gesamtes Rennwochenende gekennzeichnet.

### Anzahl vorhersagen

Beispiele:

* Wie viele Podiumsplätze erreicht Oberhaching am gesamten Wochenende?
* Wie viele Top Ten Ergebnisse erreicht das Team?
* Wie viele Klassensiege werden erzielt?

### Person vorhersagen

Beispiele:

* Wer erzielt das beste Ergebnis des Wochenendes?
* Wer hat innerhalb einer Altersklasse den geringsten Rückstand?
* Wer ist die bestplatzierte Person des Skiteams?

### Interne Reihenfolge

Die Teilnehmenden tippen die Reihenfolge der Oberhachinger Athletinnen und Athleten innerhalb einer Altersklasse. Maßgeblich ist die offizielle Platzierung im ausgewählten Rennen.

### Platzierung vorhersagen

Beispiele:

* Welche Platzierung erreicht eine bestimmte Person?
* Wie viele Oberhachinger schaffen es unter die ersten fünf?

### Direktvergleich

Beispiele:

* Wer liegt im direkten Vergleich weiter vorne?
* Welche Altersklasse sammelt mehr Podiumsplätze?

### Podium vorhersagen

Für geeignete Rennen kann weiterhin ein vollständiges Podium oder ein internes Oberhachinger Podium getippt werden. Diese Tippart ist jedoch nur eine von mehreren.

## 7. Punktesystem

Jede Tippfrage ist maximal 100 Punkte wert. Dadurch bleiben unterschiedliche Tipparten vergleichbar. Vergeben werden grundsätzlich die Stufen 100, 80, 60, 40, 20 und 0 Punkte.

### Exakte Anzahl oder Platzierung

| Abweichung vom Ergebnis | Punkte |
| --- | ---: |
| exakt | 100 |
| um 1 abweichend | 80 |
| um 2 abweichend | 60 |
| um 3 abweichend | 40 |
| um 4 abweichend | 20 |
| um 5 oder mehr abweichend | 0 |

### Beste Person oder geringster Rückstand

Die ausgewählte Person wird anhand ihrer tatsächlichen internen Oberhachinger Reihenfolge bewertet.

| Tatsächliche interne Position | Punkte |
| --- | ---: |
| 1 | 100 |
| 2 | 80 |
| 3 | 60 |
| 4 | 40 |
| 5 | 20 |
| ab Position 6 oder ohne Wertung | 0 |

### Interne Reihenfolge

Für jede getippte Person wird die Abweichung zwischen getippter und tatsächlicher interner Position nach der Staffel 100, 80, 60, 40, 20 und 0 bewertet. Der Mittelwert aller Einzelwerte ergibt die Punktzahl der Frage. Das Ergebnis wird auf eine ganze Zahl gerundet.

Beispiel: Drei Personen bringen 100, 80 und 60 Punkte. Die Frage wird mit 80 Punkten gewertet.

### Direktvergleich

Ein richtiger Tipp erhält 100 Punkte. Ein falscher Tipp erhält 0 Punkte. Bei einem offiziell nicht auflösbaren Gleichstand wird die Frage annulliert.

### Vollständiges Podium

Jeder Podiumsplatz wird einzeln bewertet. Eine richtige Person auf dem richtigen Platz erhält 100 Punkte. Eine richtige Person auf einem anderen Podiumsplatz erhält 60 Punkte. Eine Person außerhalb des Podiums erhält 0 Punkte. Der Mittelwert der drei Positionen ergibt die Punktzahl der Frage.

## 8. Wochenendwertung

Die Wertung eines Wochenendes wird normalisiert, damit Wochenenden mit unterschiedlich vielen Tippfragen gleich wichtig sind.

```text
Wochenendpunkte = erreichte Fragepunkte / maximal mögliche Fragepunkte × 1.000
```

Das Ergebnis wird auf eine ganze Zahl gerundet. Eine vollständig richtige Tipprunde bringt somit immer 1.000 Wochenendpunkte, unabhängig von der Anzahl der Fragen.

Annullierte Fragen werden weder bei den erreichten noch bei den maximal möglichen Punkten berücksichtigt.

## 9. Nicht gewertete Läufe und Penalty-Zeit

Die Status `DNS`, `DNF` und `DSQ` werden fachlich gleich behandelt. In allen drei Fällen liegt kein gewerteter Lauf vor.

### Platzierungsfragen

Eine Person ohne gewerteten Lauf wird hinter allen Personen mit einem offiziellen Ergebnis eingeordnet. Gibt es mehrere Personen ohne gewerteten Lauf, erhalten diese untereinander keine Reihenfolge.

Wird eine Person ohne gewerteten Lauf als beste Person, Podiumsplatz oder konkrete interne Position getippt, erhält dieser Teil des Tipps 0 Punkte. Haben in der für eine Frage betrachteten Gruppe überhaupt keine Personen einen gewerteten Lauf, wird die betroffene Frage annulliert.

### Zeit- und Rückstandsfragen

Für Berechnungen, die zwingend einen Zeitwert benötigen, wird eine Penalty-Zeit vergeben:

```text
Penalty-Zeit = Maximum aus
  Siegerzeit × 1,30
  langsamste gewertete Zeit × 1,05
```

Damit beträgt der Penalty-Rückstand mindestens 30 Prozent auf die Siegerzeit. Gleichzeitig liegt die Penalty-Zeit immer mindestens fünf Prozent hinter der langsamsten regulär gewerteten Zeit.

Gibt es im betreffenden Rennen keine Siegerzeit oder überhaupt keine gewertete Zeit, wird die davon abhängige Tippfrage annulliert.

## 10. Vergleichbarer prozentualer Rückstand

Zeitabstände aus unterschiedlichen Rennen werden ausschließlich über den prozentualen Rückstand verglichen:

```text
Prozentualer Rückstand = (Fahrzeit − Siegerzeit) / Siegerzeit × 100
```

Ein geringerer Prozentwert ist besser. Für Personen ohne gewerteten Lauf wird zunächst die definierte Penalty-Zeit eingesetzt und daraus anschließend der prozentuale Rückstand berechnet.

Absolute Zeitabstände in Sekunden dürfen nur innerhalb desselben Rennens angezeigt werden. Sie dürfen nicht zur Ermittlung des besten Ergebnisses über mehrere Rennen verwendet werden.

## 10.1 Maßgebliches Gesamtergebnis

Für das Tippspiel zählt immer das in der offiziellen Ergebnisliste ausgewiesene Gesamtergebnis. Je nach Rennen kann dieses unterschiedlich gebildet werden:

* bester gültiger Lauf
* Summe aus mehreren Läufen
* ein einzelner Wertungslauf
* eine andere offiziell festgelegte Wertung

Das Tippspiel berechnet das Gesamtergebnis nicht selbst aus den Einzellaufzeiten neu. Es übernimmt die offizielle Laufzeit beziehungsweise Totalzeit und die offizielle Platzierung der jeweiligen Wertungsgruppe.

Einzellaufzeiten und Einzellaufstatus werden zusätzlich gespeichert. Sie dienen der Nachvollziehbarkeit, ändern aber nicht das veröffentlichte Gesamtergebnis. Insbesondere kann bei einer Bestlaufwertung ein `DNF` oder `DSQ` in einem Lauf vorliegen und die Person durch einen anderen gültigen Lauf trotzdem offiziell klassifiziert sein.

## 11. Saisonwertung

Die Saisonwertung ist die Summe aller Wochenendpunkte. Wer nicht an einer gültigen Tipprunde teilnimmt, erhält für diese Runde 0 Punkte.

Bei Punktgleichheit gelten zunächst folgende Kriterien:

1. mehr Tipprunden mit 1.000 Punkten
2. mehr Tippfragen mit 100 Punkten
3. mehr gespielte Tipprunden
4. geteilter Rang, wenn weiterhin Gleichstand besteht

Es gibt keine Streichergebnisse. Jede gültige Tipprunde zählt vollständig zur Saisonwertung.

## 12. Optionale Teamwertung

Eine Teamwertung ist für eine spätere Iteration vorgesehen. Mögliche Teams sind:

* Tippende einer Altersklasse
* Trainerteams
* frei zusammengestellte Gruppen

Die Teamwertung verwendet die Durchschnittspunktzahl aller dem Team für die jeweilige Tipprunde zugeordneten Personen:

```text
Team-Wochenendpunkte = Summe der Wochenendpunkte aller Teammitglieder / Anzahl der Teammitglieder
```

Das Ergebnis wird auf eine ganze Zahl gerundet. Eine Person ohne abgegebenen Tipp bringt 0 Punkte in den Teamdurchschnitt ein. Die Teamzuordnung wird zu Beginn der Tipprunde festgehalten, damit spätere Änderungen eine bereits abgeschlossene Wertung nicht verändern.

Die Saisonpunktzahl eines Teams ist die Summe seiner Team-Wochenendpunkte. Durch den Durchschnitt haben große und kleine Teams grundsätzlich dieselbe maximal mögliche Punktzahl.

## 13. Ausfälle und Annullierungen

Wird ein vollständiges Rennen abgebrochen oder offiziell annulliert, werden alle ausschließlich davon abhängigen Tippfragen annulliert. Dafür werden keine Punkte vergeben. Die Fragen beeinflussen auch nicht die maximal möglichen Wochenendpunkte.

Wird ein vollständiges Rennwochenende annulliert, wird die gesamte Tipprunde annulliert und nicht in die Saisonwertung aufgenommen.

Einzelne `DNS`, `DNF` und `DSQ` führen nicht zur Annullierung des gesamten Rennens. Sie werden nach den Regeln für nicht gewertete Läufe behandelt.

## 14. Ergebnisse

Für die Wertung zählt ausschließlich das offizielle Endergebnis der jeweiligen Veranstaltung. Korrekturen am offiziellen Ergebnis müssen eine erneute Berechnung der betroffenen Tippfragen und Ranglisten auslösen können.

Der erste technische Import liest die vorliegenden textbasierten Race Horology Ergebnislisten automatisch ein. Weitere PDF Formate und gescannte Dokumente werden erst nach einem realistischen Wochenendtest ergänzt.

Eine Ergebnisliste kann mehrere getrennte Wertungsgruppen enthalten. Siegerzeit, langsamste gewertete Zeit, Platzierung und prozentualer Rückstand werden immer innerhalb der jeweiligen offiziellen Wertungsgruppe bestimmt. Eine Wertungsgruppe kann neben der Altersklasse auch Geschlecht beziehungsweise Wettbewerbskategorie und Jahrgang berücksichtigen.

## 15. Nicht Bestandteil der ersten Iterationen

* Anmeldung und Nutzerkonten
* Datenbank
* automatischer Ergebnisimport
* Benachrichtigungen
* öffentliche Teamverwaltung

## 16. Offene Entscheidungen

Vor der endgültigen Implementierung der Wertungslogik müssen noch folgende Punkte entschieden werden:

1. genaue Auswahl und Mischung der sechs bis zehn Tippfragen pro Wochenende
2. organisatorische Zusammensetzung späterer Teams
3. Aufnahme weiterer Altersklassen bei offenen Landkreisrennen
4. Behandlung von Personen, die während der Saison einem Team beitreten oder es verlassen

## 17. Definition des ersten fachlichen MVP

Der erste fachliche MVP ist erreicht, wenn lokal ohne Anmeldung und Datenbank folgender Ablauf funktioniert:

1. Eine Tipprunde mit mehreren Rennen und Tippfragen anzeigen
2. Tipps für mindestens vier unterschiedliche Tipparten abgeben
3. Abgabeschluss berücksichtigen
4. Ergebnisse manuell erfassen
5. alle Fragen automatisch nach den definierten Regeln auswerten
6. normalisierte Wochenendpunkte berechnen
7. eine lokale Saisonrangliste anzeigen
