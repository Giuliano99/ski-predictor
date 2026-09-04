# Spielleiter-Oberfläche

Das lokale Dashboard bündelt den vollständigen Spielleiter-Workflow in einer Browseroberfläche. Es benötigt neben Python und PowerShell keine zusätzlichen Pakete.

Start aus dem Projekt-Hauptordner:

```powershell
.\scripts\game-master\Start-Dashboard.ps1
```

Danach startet ein gemeinsamer Backend-Prozess. Die Spielleiter-Oberfläche öffnet sich unter `http://127.0.0.1:4175/spielleiter/`. Unter `http://127.0.0.1:4175/tippspiel/` ist gleichzeitig die öffentliche Testwebsite erreichbar; beide beziehen ihre Daten aus derselben API.

Die Oberfläche nutzt ausschließlich die versionierten Endpunkte unter `/api/v1` und übernimmt:

1. Anlegen eines Rennwochenendes samt Ordnern und Fragenvorlage
2. Ablage der Startlisten und Ergebnislisten sowie Kontrolle der automatisch gespeicherten Tippabgaben
3. Automatisches Auslesen der PDFs für die wiederverwendbare Renndaten-API
4. Prüfung und Freigabe der strukturierten Renndaten
5. Import und Zuordnung aller PDFs für das Tippspiel
6. Erzeugung und Anzeige der Prüfberichte
7. Auswertung aller Tipps und Aktualisierung der Saisonwertung
8. Automatisches Schließen einer echten Tipprunde nach dem Abgabeschluss, solange das Dashboard läuft

Bewusste Bestätigungen bleiben das Öffnen der geprüften Tipprunde und das Archivieren nach der Ergebniskontrolle. Im Testmodus wird eine Runde nicht automatisch anhand des Datums geschlossen.

## Externer Datenspeicher

Start- und Ergebnislisten neuer Wochenenden liegen außerhalb des Repositories. Die lokale, nicht eingecheckte Datei `config/local-storage.json` legt den Speicherordner fest. Eine portable Vorlage befindet sich in `config/local-storage.example.json`.

Wochenendkonfigurationen verwenden dafür Pfade wie `storage://saisons/2026-2027/weekends/2026-12-05/startlisten`. Dadurch enthalten sie keinen persönlichen Windows-Pfad und können später ohne Änderung der Fachlogik auf einen anderen Speicheranbieter umgestellt werden.
