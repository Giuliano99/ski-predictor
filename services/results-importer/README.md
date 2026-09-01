# Race Data Importer

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

## Künstliches Testwochenende

Die Option `--test-weekend-date` ist ausschließlich für Fixtures gedacht. Sie verändert die Quelldateien nicht und kennzeichnet die erzeugte Tipprunde mit `testFixture: true`.

```powershell
python services/results-importer/src/generate_tip_round.py data/result-lists/processed/startliste2.json data/result-lists/processed/startliste3.json --questions data/questions/weekend-questions.md --test-weekend-date 2026-01-03 --output data/result-lists/processed/example-weekend-tip-round.json
```

## Tests

```powershell
python -m unittest discover services/results-importer/tests
```
