# Race Data Importer

Für den normalen Spielleiterbetrieb müssen die folgenden Einzelbefehle nicht manuell ausgeführt werden. Der automatisierte Ablauf steht unter [`scripts/game-master`](../../scripts/game-master/README.md). Die Einzelbefehle in diesem Dokument dienen der Entwicklung und Fehleranalyse.

Dieser Dienst liest Startlisten und textbasierte Race Horology Ergebnislisten aus PDF Dateien ein.

Der Dienst bleibt vom API Dienst getrennt. So können Importläufe unabhängig geplant, wiederholt und überwacht werden.

Der erste MVP unterstützt textbasierte PDF Startlisten aus DSValpin und Race Horology. Die Ausgabe ist normalisiertes JSON und bleibt wegen der enthaltenen Namen lokal unter `data/result-lists/processed`.

## Startliste extrahieren

Abhängigkeiten einmalig installieren:

```powershell
python -m pip install -r services/results-importer/requirements.txt
```

```powershell
python services/results-importer/src/extract_start_list.py data/result-lists/inbox/startliste1.pdf
```

Die Zusammenfassung auf der Konsole enthält nur Anzahlen und keine Namen. Das vollständige JSON wird standardmäßig unter `data/result-lists/processed` gespeichert.

## Tipprunde erzeugen

Aus einer geprüften normalisierten Startliste und der redaktionellen Markdown Datei wird ein lokaler Entwurf mit sechs bis zehn Fragen erzeugt:

```powershell
python services/results-importer/src/generate_tip_round.py data/result-lists/processed/startliste3.json --questions data/questions/weekend-questions.md
```

Mehrere Startlisten desselben Rennwochenendes können gemeinsam übergeben werden. Sie dürfen höchstens drei Tage auseinanderliegen.

Nach der fachlichen Prüfung kann der Entwurf direkt für die lokale Website erzeugt werden:

```powershell
python services/results-importer/src/generate_tip_round.py data/result-lists/processed/startliste3.json --questions data/questions/weekend-questions.md --output apps/web/src/data/tip-round.local.json
```

Die Website bevorzugt diese lokale Datei und fällt andernfalls auf die versionierte Demo Tipprunde zurück. `tip-round.local.json` wird von Git ignoriert. Der Generator übernimmt ausschließlich gekürzte Anzeigenamen. Vollständige Namen bleiben in den lokalen Importdaten.

Das Format und Beispiele für alle Fragetypen stehen in [`data/questions/README.md`](../../data/questions/README.md). Ohne `--questions` verwendet der Generator weiterhin seine automatischen Vorschläge.

## Ergebnisliste extrahieren

Die normalisierte Startliste wird zur eindeutigen Zuordnung und Vollständigkeitsprüfung mitgegeben:

```powershell
python services/results-importer/src/extract_result_list.py data/result-lists/inbox/example-weekend/rennen3.pdf --start-list data/result-lists/processed/startliste3.json --output data/result-lists/processed/rennen3.json
```

Das Ergebnis enthält das offizielle Gesamtergebnis, beide Läufe, Platzierung, prozentualen Rückstand und den ursprünglichen Status. `NAS`, `NIZ` und `DIS` werden fachlich als `DNS`, `DNF` und `DSQ` normalisiert.

### Wertung von DNS, DNF und DSQ

- `DNS` wird aus der sportlichen Reihenfolge entfernt. Eine Platzierungsfrage für diese Person oder ein betroffenes Duell wird annulliert. In Ranglisten wird die Person aus dem Tipp entfernt und die restliche Reihenfolge zusammengeschoben.
- `DNF` und `DSQ` werden gleich behandelt. Sie teilen sich hinter allen gewerteten Personen den letzten Platz.
- Die Reihenfolge mehrerer `DNF` oder `DSQ` ist für die Punktevergabe bedeutungslos.
- Bei Platzierungsfragen ist der gemeinsame letzte Platz die höchste offizielle Platzierung der Wertungsgruppe plus eins.
- Sind in einem Duell beide Personen `DNF` oder `DSQ`, oder besteht eine komplette Rangfolge nur daraus, wird die Frage annulliert.
- Die Penalty-Zeit bleibt für technische Rückstandsberechnungen erhalten, löst aber keinen Gleichstand zwischen `DNF` und `DSQ` auf.

### Versionsschutz

Jede erzeugte Tipprunde erhält eine SHA-256-Inhaltsversion über Rennen, Starter, Wertungsgruppen, Fragen und Abgabefrist. Die Website schreibt diese Version in jede exportierte Tippabgabe. Die Auswertung lehnt fehlende oder abweichende Versionen ab. Der Statuswechsel selbst verändert die Inhaltsversion nicht.

`Prepare-Weekend.ps1` darf nur im Status `DRAFT` ausgeführt werden. Damit bleiben die veröffentlichten Inhalte ab `OPEN` unverändert.

## Tippabgabe auswerten

```powershell
python services/results-importer/src/evaluate_tip_round.py apps/web/src/data/tip-round.local.json data/result-lists/processed/rennen3.json --submission data/submissions/inbox/tipp-tip-round-2026-01-03.json --output apps/web/src/data/evaluation.local.json
```

Die JSON Datei wird zuvor in der Website über `Tipp exportieren` heruntergeladen und nach `data/submissions/inbox` verschoben. Der Dateiname im Befehl muss bei Bedarf angepasst werden. Die Engine prüft Tipprunden ID, Vollständigkeit, Wertebereiche und zulässige Athleten. Danach wertet sie alle sechs Fragetypen mit der Staffel 100, 80, 60, 40, 20 und 0 aus und normalisiert das Wochenende auf maximal 1.000 Punkte.

Für lokale technische Tests kann statt einer echten Abgabe weiterhin `--perfect-fixture` verwendet werden:

Für die aktuell lokal geladene Tipprunde kann eine direkt in der Website sichtbare Testauswertung so erzeugt werden:

```powershell
python services/results-importer/src/evaluate_tip_round.py apps/web/src/data/tip-round.local.json data/result-lists/processed/rennen3.json --perfect-fixture --output apps/web/src/data/evaluation.local.json
```

`evaluation.local.json` wird von Git ignoriert. Die Website blendet den Auswertungsbereich automatisch ein, wenn die Kennung zur geladenen Tipprunde passt.

## Alle Abgaben eines Wochenendes auswerten

Jede Person gibt in der Testwebsite einen Ranglistennamen ein, speichert ihren Tipp und exportiert ihn. Alle Dateien dieser Runde werden in `data/submissions/inbox/tip-round-2026-01-03` gesammelt. Pro Ranglistenkennung zählt die zeitlich neueste Abgabe.

```powershell
python services/results-importer/src/evaluate_submissions.py apps/web/src/data/tip-round.local.json data/result-lists/processed/rennen3.json --submissions-dir data/submissions/inbox/tip-round-2026-01-03 --output data/submissions/processed/weekend-tip-round-2026-01-03.json --website-output apps/web/src/data/weekend-evaluation.local.json
```

Die Wochenendauswertung enthält die Platzierung aller Teilnehmer und ihre Einzelauswertungen. Die Website findet anhand der lokal gespeicherten Abgabe ID automatisch die passende persönliche Auswertung.

## Saisonrangliste erzeugen

Alle bisher erzeugten Wochenendauswertungen werden ohne Streichergebnis addiert:

```powershell
python services/results-importer/src/aggregate_season.py data/submissions/processed/weekend-tip-round-2026-01-03.json --output data/submissions/processed/season-2026-2027.json --website-output apps/web/src/data/season-leaderboard.local.json
```

Sobald weitere Wochenenden vorliegen, werden deren archivierte JSON Dateien vor `--output` ergänzt. Die Saisonrangliste enthält Gesamtpunkte, Anzahl gewerteter Tipprunden und Durchschnittspunkte.

## Künstliches Testwochenende

Die Option `--test-weekend-date` ist ausschließlich für Fixtures gedacht. Sie verändert die Quelldateien nicht und kennzeichnet die erzeugte Tipprunde mit `testFixture: true`.

```powershell
python services/results-importer/src/generate_tip_round.py data/result-lists/processed/startliste2.json data/result-lists/processed/startliste3.json --questions data/questions/weekend-questions.md --test-weekend-date 2026-01-03 --output data/result-lists/processed/example-weekend-tip-round.json
```

## Tests

```powershell
python -m unittest discover services/results-importer/tests
```
