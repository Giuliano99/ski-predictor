# Ski Document API

Die lokale Backend API stellt Start- und Ergebnislisten als gemeinsame Datenquelle für den Ski Predictor und weitere Projekte bereit. Die Original-PDFs bleiben im externen Datenspeicher. Lokal speichert SQLite Dokument-Metadaten, vollständigen PDF-Text, den unveränderten strukturierten Rohimport und normalisierte Renndaten. PostgreSQL bleibt das Zielsystem für den Raspberry Pi.

## Starten

Aus dem Projekt-Hauptordner:

```powershell
.\scripts\game-master\Start-Backend.ps1
```

Danach stehen die Dokumentation und anklickbare Beispiele unter `http://127.0.0.1:4175` bereit. Die API lauscht ausschließlich auf dem lokalen Rechner.

Der normale Start erfolgt über die Spielleiter-Oberfläche. Dabei laufen API, Dashboard und Tippspiel gemeinsam:

```powershell
.\scripts\game-master\Start-Dashboard.ps1
```

```text
http://127.0.0.1:4175/spielleiter/
http://127.0.0.1:4175/tippspiel/
```

## Datenbank einrichten

```powershell
.\scripts\game-master\Initialize-Database.ps1
```

`Initialize-Database.ps1` erstellt die lokale SQLite-Datei, führt versionierte
Migrationen aus und übernimmt vorhandene Dokumente, Extraktionen und Tippabgaben.
Es läuft kein eigener Datenbankdienst. Die API führt neue Migrationen und den
Dokumentabgleich beim Start automatisch aus. `DATABASE_URL` überschreibt die
lokale Konfiguration und aktiviert später PostgreSQL auf dem Raspberry Pi.

Tipprunden, Fragen, Wochenendauswertungen und Saisonranglisten werden beim Start
und nach Spielleiter-Aktionen in die Datenbank synchronisiert. Die öffentlichen
Predictor-Endpunkte lesen primär aus der Datenbank. Nur wenn keine Datenbank
konfiguriert ist, dienen die bisherigen JSON-Artefakte als Rückfalloption.
Auch die Wochenendauswertung verwendet Datenbank-Tippabgaben primär und fällt nur
für ältere Testbestände ohne Datenbankeintrag auf JSON zurück.

## Endpunkte

```text
GET /api/v1/health
GET /api/v1/documents
GET /api/v1/documents/{documentId}
GET /api/v1/documents/{documentId}/file
POST /api/v1/documents/{documentId}/extract
GET /api/v1/documents/{documentId}/extraction
GET /api/v1/collections
GET /api/v1/imports
GET /api/v1/imports/{importId}
GET /api/v1/weekends
POST /api/v1/weekends/{weekendId}/extractions
GET /api/v1/extraction-jobs
GET /api/v1/extraction-jobs/{jobId}
POST /api/v1/extraction-jobs/{jobId}/approve
GET /api/v1/events
GET /api/v1/races
GET /api/v1/races/{raceId}
GET /api/v1/races/{raceId}/start-list
GET /api/v1/races/{raceId}/results
GET /api/v1/athletes
GET /api/v1/athletes/{athleteId}
GET /api/v1/athletes/{athleteId}/results
POST /api/v1/athlete-identities/merge
GET /api/v1/predictor/rounds/current
POST /api/v1/predictor/rounds/{tipRoundId}/submissions
GET /api/v1/predictor/rounds/{tipRoundId}/evaluation
GET /api/v1/predictor/seasons/{seasonId}/leaderboard
GET /api/v1/openapi.json
```

Filter für die Dokumentensuche:

```text
kind=START_LIST|RESULT_LIST|UNKNOWN
seasonId=2025-2026
weekendDate=2026-03-07
contentHash=sha256-...
archived=true|false
offset=0
limit=100
```

Beispiel für ein anderes Python-Projekt:

```python
import json
import urllib.request

url = "http://127.0.0.1:4175/api/v1/documents?kind=RESULT_LIST&seasonId=2025-2026"
with urllib.request.urlopen(url) as response:
    result_lists = json.load(response)["items"]
```

`documentId` identifiziert ein Dokument an seinem Ablageort. `contentHash` identifiziert den unveränderten Dateiinhalt. Andere Projekte können dadurch bereits verarbeitete PDFs erkennen und doppelte Arbeit vermeiden.

`GET /api/v1/imports?documentId=...` listet alle Parser-Versionen eines Dokuments.
`GET /api/v1/imports/{importId}` liefert den vollständigen PDF-Text, Rohimport,
normalisierten Import und Prüfbericht. Damit können weitere Projekte auf dieselbe
Datenbasis zugreifen, ohne Predictor-interne Dateien oder Tabellen zu kennen.

Die API gibt keine absoluten Windows-Pfade aus. Sie liefert ausschließlich portable `storage://`-Referenzen und Download-URLs. Der allgemeine Dokumentenkatalog ist nur lesend. Änderungen am Spielbetrieb sind ausschließlich über die gesonderten Wochenend-Endpunkte möglich, die das lokale Spielleiter-Dashboard verwendet.

Tippabgaben werden mit `POST /api/v1/predictor/rounds/{tipRoundId}/submissions` validiert und automatisch im für das Wochenende konfigurierten `submissionsDir` sowie in der konfigurierten Datenbank gespeichert. Die API vergibt Abgabe-ID und Zeitstempel selbst. Nur eine geöffnete, nicht abgelaufene Runde mit passender Inhaltsversion wird angenommen. Eine spätere gültige Abgabe desselben Spielernamens zählt bei der Auswertung automatisch als neueste Abgabe.

Die API ist im MVP ausschließlich lokal erreichbar. Vor einer Veröffentlichung im Netzwerk oder Internet müssen Authentifizierung und Zugriffsschutz ergänzt werden.
SQLite öffnet keinen Netzwerk-Port. Auf dem Raspberry Pi wird später ausschließlich die Backend API nach außen freigegeben, niemals der PostgreSQL-Port.

## PDF-Extraktion

`POST /api/v1/documents/{documentId}/extract` legt einen persistenten Auftrag an. Die Verarbeitung läuft im Hintergrund und kann über `GET /api/v1/extraction-jobs/{jobId}` verfolgt werden.

```text
PENDING → PROCESSING → REVIEW_REQUIRED → APPROVED
                         └──────────────→ FAILED
```

Zu jedem erfolgreichen Auftrag werden drei lokale Artefakte unter `data/extractions/jobs/<jobId>` erzeugt:

* unveränderte Extraktion aus dem vorhandenen PDF-Importer
* allgemeines normalisiertes Renndokument
* lesbarer Prüfbericht

Parallel legt die Datenbank einen versionierten Rohimport an. Er enthält das komplette
extrahierte JSON und den vollständigen PDF-Text. U14/U16-Verbands- und Rennpunkte,
Laufzeiten, Status sowie Zuschlagsberechnungen bleiben dadurch für andere Projekte
verfügbar. Erst nach Freigabe werden zusätzlich relationale Tabellen für schnelle
Abfragen nach Athlet, Rennen, Klasse oder Lauf befüllt.

Der Ordner wird nicht in Git eingecheckt. Nur `APPROVED` Daten erscheinen unter `/api/v1/events` und `/api/v1/races`. Der Spielleiter kann alle PDFs eines Wochenendes gesammelt über die Oberfläche anstoßen und einzeln freigeben.

Ergebnislisten im DSValpin-Format benötigen die passende Startliste. Falls keine Dokument-ID mitgegeben wurde, versucht die API nach Freigabe der Startlisten die beste Zuordnung desselben Wochenendes automatisch. Gleich gute Zuordnungen werden als Warnung im Prüfbericht angezeigt.

## Athletenidentität

Jeder Teilnehmer erhält eine dokumentübergreifend stabile `athleteId`. Die Zuordnung verwendet in dieser Reihenfolge:

1. eindeutigen Verbandscode
2. normalisierten Namen, Geburtsjahr und Verein
3. einen ähnlichen Namen bei gleichem Geburtsjahr und Verein mit verpflichtender Sichtprüfung
4. eine neue deterministische Kennung

Die Prüfberichte zählen `NEW`, `EXACT`, `EXTERNAL_ID`, `FUZZY_REVIEW` und `CONFLICT`. Ein neuer unsicherer Ähnlichkeitstreffer stoppt die Freigabe einmal und zeigt den aktualisierten Prüfbericht. Ein Konflikt muss aufgelöst werden. Doppelte Einträge lassen sich in der Spielleiter-Oberfläche oder über `POST /api/v1/athlete-identities/merge` zusammenführen. Dabei bleibt die alte Kennung als Weiterleitung erhalten.

Die lokale Kartei liegt unter `data/extractions/athletes.json` und wird nicht in Git eingecheckt. `/api/v1/athletes/{athleteId}` liefert alle freigegebenen Starts und Ergebnisse dieser Person. Mit `?targetClub=true` kann die Liste auf das Skiteam Oberhaching eingeschränkt werden.

## Datenqualität prüfen

Der rein lesende Audit prüft fehlende Extraktionen, ausstehende Freigaben,
unvollständige Rennen, Identitätskonflikte und mögliche doppelte Athleten:

```powershell
python services/api/src/database_cli.py audit --output output/reports/data-quality.md
```

Der Bericht verändert keine Daten. Unsichere Korrekturen bleiben eine bewusste
Entscheidung des Spielleiters.

Im Spielleiter-Portal erscheint derselbe aktuelle Stand unter **Datenqualität**.
Die maschinenlesbare Variante liefert `GET /api/v1/admin/data-quality`.
