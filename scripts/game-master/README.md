# Spielleiter Workflow

Alle Befehle werden aus dem Repository Hauptordner ausgeführt.

Für den normalen Ablauf steht eine Browseroberfläche zur Verfügung:

```powershell
.\scripts\game-master\Start-Dashboard.ps1
```

Die folgenden Einzelbefehle bleiben für Fehleranalyse und Sonderfälle erhalten.

## Neues Wochenende anlegen

Der Assistent legt die Ordner, die Konfiguration und sechs anpassbare Beispielfragen an:

```powershell
.\scripts\game-master\New-Weekend.ps1
```

Das Datum kann auch direkt mitgegeben werden:

```powershell
.\scripts\game-master\New-Weekend.ps1 -WeekendDate 2026-12-05 -Title "SVM Wochenende Lenggries"
```

Danach werden die Startlisten als PDF in den angezeigten Ordner kopiert und die Fragen angepasst. Beim Vorbereiten erkennt das Skript die PDFs automatisch und trägt sie in die Konfiguration ein.

Nach einem grünen Prüfbericht wird die Tipprunde geöffnet:

```powershell
.\scripts\game-master\Set-WeekendStatus.ps1 -Config config/weekends/tip-round-JJJJ-MM-TT.json -Status OPEN
```

## 1. Wochenende vorbereiten

Startlisten werden aus den PDFs gelesen, normalisiert und zusammen mit den Fragen zur Tipprunde verarbeitet. Die Website erhält automatisch die neue lokale Tipprunde.

```powershell
.\scripts\game-master\Prepare-Weekend.ps1
```

Für eine andere Konfiguration:

```powershell
.\scripts\game-master\Prepare-Weekend.ps1 -Config config/weekends/mein-wochenende.json
```

Das aktuelle vollständige Beispielwochenende mit sechs Startlisten wird so vorbereitet:

```powershell
.\scripts\game-master\Prepare-Weekend.ps1 -Config config/weekends/tip-round-2026-03-07.json
```

Bei jeder Vorbereitung wird unter `output/reports` ein Prüfbericht erzeugt. Blockierende Fehler stoppen den Ablauf. Warnungen bleiben sichtbar und können vor der Freigabe geprüft werden.

Danach wird die Website gestartet und die exportierten Tippabgaben werden im konfigurierten Submission Ordner gesammelt.

Nach Ablauf der Tippfrist wird die Runde geschlossen:

```powershell
.\scripts\game-master\Set-WeekendStatus.ps1 -Config config/weekends/tip-round-JJJJ-MM-TT.json -Status CLOSED
```

## 2. Wochenende auswerten

Ergebnislisten werden importiert, alle abgegebenen Tipps ausgewertet und Wochenend- sowie Saisonrangliste für die Website aktualisiert.

Bei einem neu angelegten Wochenende reicht es, alle Ergebnis-PDFs in den erzeugten `results` Ordner zu kopieren. Der Ergebnis-Assistent ordnet sie anhand von Datum, Rennname, Disziplin und Altersklasse automatisch den Startlisten zu.

```powershell
.\scripts\game-master\Evaluate-Weekend.ps1
```

Die Saisonaggregation kann bei Bedarf übersprungen werden:

```powershell
.\scripts\game-master\Evaluate-Weekend.ps1 -SkipSeason
```

Vor der Punkteberechnung entsteht unter `output/reports` ein Ergebnis-Prüfbericht. Er kontrolliert die Zuordnungen, fehlende Oberhachinger Starter, doppelte Startnummern, Zeiten, Platzierungen sowie die Verteilung von `CLASSIFIED`, `DNS`, `DNF` und `DSQ`. Blockierende Fehler stoppen die Auswertung.

Nach erfolgreicher Auswertung wechselt das Wochenende automatisch auf `EVALUATED`. Anschließend kann es archiviert werden:

```powershell
.\scripts\game-master\Set-WeekendStatus.ps1 -Config config/weekends/tip-round-JJJJ-MM-TT.json -Status ARCHIVED
```

Erlaubte Übergänge sind `DRAFT → OPEN → CLOSED → EVALUATED → ARCHIVED`. Eine Runde kann aus `DRAFT`, `OPEN` oder `CLOSED` alternativ als `CANCELLED` markiert werden.

## Ablauf vorab prüfen

Beide Skripte unterstützen PowerShell `-WhatIf`. Dabei werden keine Dateien verändert.

```powershell
.\scripts\game-master\Prepare-Weekend.ps1 -WhatIf
.\scripts\game-master\Evaluate-Weekend.ps1 -WhatIf
```

Die Skripte brechen sofort ab, wenn Dateien fehlen, keine Tippabgaben vorliegen oder ein Verarbeitungsschritt fehlschlägt. Pfade außerhalb des Repositories werden abgelehnt.
