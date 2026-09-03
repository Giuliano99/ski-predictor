# Spielleiter-Anleitung

Alle PowerShell-Befehle werden im Hauptordner des Repositories ausgeführt:

```powershell
cd C:\Users\GiulianoGaubbtellige\repos\12_rpi\ski-predictor
```

## Empfohlen: Spielleiter-Oberfläche

Für den normalen Betrieb reicht ein Befehl:

```powershell
.\scripts\game-master\Start-Dashboard.ps1
```

Die Oberfläche öffnet sich automatisch im Browser. Startlisten, Ergebnislisten und exportierte Tipps werden direkt dort ausgewählt. Die Oberfläche legt sie im richtigen Ordner ab und übernimmt Import, Zuordnung, Prüfberichte, Auswertung und Saisonwertung.

Der Spielleiter kontrolliert vor der Veröffentlichung den grünen Prüfbericht und bestätigt anschließend das Öffnen der Tipprunde. Nach dem Rennwochenende kontrolliert er den Ergebnisbericht und die Rangliste und archiviert das Wochenende. Eine echte geöffnete Runde wird bei laufender Oberfläche nach Erreichen des Abgabeschlusses automatisch geschlossen. Der Testmodus bleibt offen, bis der Spielleiter ihn schließt.

Die nachfolgenden PowerShell-Schritte bleiben als manueller Ersatz und zur Fehleranalyse erhalten.

### Ablage der Originaldokumente

Start- und Ergebnislisten werden nicht mehr im Repository abgelegt. Der lokale Datenordner ist in `config/local-storage.json` hinterlegt. Die Spielleiter-Oberfläche erzeugt darin automatisch diese Struktur:

```text
saisons/<Saison>/weekends/<Datum>/startlisten
saisons/<Saison>/weekends/<Datum>/ergebnislisten
```

In den eincheckbaren Wochenendkonfigurationen stehen nur portable `storage://`-Verweise. Der persönliche Windows-Pfad und die Original-PDFs gelangen dadurch nicht in Git.

In den Befehlen steht `JJJJ-MM-TT` für den ersten Renntag, zum Beispiel `2026-12-05`.

## Vor dem Rennwochenende

### 1. Neues Wochenende anlegen

```powershell
.\scripts\game-master\New-Weekend.ps1 -WeekendDate JJJJ-MM-TT -Title "Name des Rennwochenendes"
```

Der Assistent erstellt anschließend die benötigten Ordner, die Wochenendkonfiguration und eine Vorlage für die Tippfragen. Der Status ist zunächst `DRAFT`.

### 2. Startlisten ablegen

Die Startlisten als PDF in diesen erzeugten Ordner kopieren:

```text
data/result-lists/inbox/weekend-JJJJ-MM-TT/start-lists
```

### 3. Tippfragen festlegen

Die erzeugte Markdown-Datei bearbeiten:

```text
data/questions/weekend-questions-JJJJ-MM-TT.md
```

Es müssen sechs bis zehn Fragen vorhanden sein. Jede Frage muss eindeutig nennen, für welchen Tag, welches Rennen, welche Disziplin und gegebenenfalls welche Altersklasse sie gilt.

### 4. Wochenende vorbereiten und prüfen

```powershell
.\scripts\game-master\Prepare-Weekend.ps1 -Config config/weekends/tip-round-JJJJ-MM-TT.json
```

Das Skript erkennt die Startlisten, liest die Oberhachinger Starter aus, erzeugt die Tipprunde und schreibt den Prüfbericht nach:

```text
output/reports/review-tip-round-JJJJ-MM-TT.md
```

Nur bei `Status: BEREIT` fortfahren. Fehler zuerst in den Startlisten, Fragen oder der Wochenendkonfiguration korrigieren und den Befehl erneut ausführen.

### 5. Tipprunde öffnen

```powershell
.\scripts\game-master\Set-WeekendStatus.ps1 -Config config/weekends/tip-round-JJJJ-MM-TT.json -Status OPEN
```

Der Statuswechsel ist nur mit einem erfolgreichen Prüfbericht möglich.

Mit dem Öffnen wird die vorbereitete Version der Rennen, Starter und Fragen verbindlich. Danach `Prepare-Weekend.ps1` nicht erneut ausführen und die Fragen nicht mehr verändern. Exportierte Tipps enthalten automatisch die passende Inhaltsversion; Tipps einer anderen Version werden abgelehnt.

### 6. Website lokal kontrollieren

```powershell
.\scripts\game-master\Start-Dashboard.ps1
```

Danach im Browser öffnen:

```text
http://127.0.0.1:4175/tippspiel/
```

### 7. Tippabgaben sammeln

Die Spieler exportieren ihre Tipps auf der Website als JSON-Datei. Alle Dateien werden hier abgelegt:

```text
data/submissions/inbox/tip-round-JJJJ-MM-TT
```

Wenn ein Spieler mehrfach abgibt, verwendet die Auswertung automatisch seine neueste Abgabe.

### 8. Tipprunde schließen

Nach Ablauf der Tippfrist:

```powershell
.\scripts\game-master\Set-WeekendStatus.ps1 -Config config/weekends/tip-round-JJJJ-MM-TT.json -Status CLOSED
```

Danach können auf der Website keine Tipps mehr gespeichert werden.

## Nach dem Rennwochenende und Auswertung

### 1. Ergebnislisten ablegen

Alle offiziellen Ergebnislisten als PDF in diesen Ordner kopieren:

```text
data/result-lists/inbox/weekend-JJJJ-MM-TT/results
```

Die Dateinamen sind nicht entscheidend. Der Ergebnis-Assistent ordnet die PDFs anhand von Datum, Rennname, Disziplin und Altersklasse den Startlisten zu.

### 2. Ergebnisse prüfen und Tipps auswerten

```powershell
.\scripts\game-master\Evaluate-Weekend.ps1 -Config config/weekends/tip-round-JJJJ-MM-TT.json
```

Der Ablauf führt automatisch folgende Schritte aus:

1. Ergebnislisten erkennen und den Startlisten zuordnen
2. Ergebnisse und Oberhachinger Starter prüfen
3. `DNS`, `DNF` und `DSQ` nach den festgelegten Regeln behandeln
4. Alle Tippabgaben auswerten
5. Wochenend- und Saisonwertung aktualisieren
6. Den Status auf `EVALUATED` setzen

Bei einem Fehler wird die Punkteberechnung gestoppt. Der Ergebnis-Prüfbericht steht hier:

```text
output/reports/results-tip-round-JJJJ-MM-TT.md
```

Er muss `Status: BEREIT` anzeigen.

### 3. Ergebnis auf der Website kontrollieren

Falls der lokale Webserver nicht mehr läuft:

```powershell
.\scripts\game-master\Start-Dashboard.ps1
```

Die Website unter `http://127.0.0.1:4175/tippspiel/` öffnen und kontrollieren:

- Wochenendrangliste
- Saisonrangliste
- Punkte je Frage
- annullierte Fragen
- gemeinsame letzte Plätze bei `DNF` und `DSQ`
- nicht berücksichtigte `DNS`

### 4. Wochenende archivieren

Nach der abschließenden Kontrolle archivieren:

```powershell
.\scripts\game-master\Set-WeekendStatus.ps1 -Config config/weekends/tip-round-JJJJ-MM-TT.json -Status ARCHIVED
```

## Sonderfall: Rennwochenende absagen

Eine Runde im Status `DRAFT`, `OPEN` oder `CLOSED` kann abgesagt werden:

```powershell
.\scripts\game-master\Set-WeekendStatus.ps1 -Config config/weekends/tip-round-JJJJ-MM-TT.json -Status CANCELLED
```

Eine abgesagte Runde wird nicht ausgewertet.

## Fachlichen Referenztest ausführen

Der geprüfte Beispiel-Spieltag vom 7. und 8. März 2026 ist als datensparsamer Referenzfall hinterlegt. Der Test stellt sicher, dass spätere Änderungen die erwarteten Punkte nicht unbemerkt verändern:

```powershell
python -m unittest discover -s services/results-importer/tests -p "test_reference_weekend.py"
```

Die erwarteten Werte dürfen nur bewusst nach einer vollständigen fachlichen Kontrolle neu übernommen werden:

```powershell
python services/results-importer/src/build_reference_fixture.py
```
