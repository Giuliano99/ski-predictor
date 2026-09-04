# Ski Document API

Die lokale Backend API stellt Start- und Ergebnislisten als gemeinsame Datenquelle für den Ski Predictor und weitere Projekte bereit. Die Original-PDFs bleiben im externen Datenspeicher. Eine spätere Datenbank enthält nur strukturierte Daten und Dokument-Metadaten.

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

## Endpunkte

```text
GET /api/v1/health
GET /api/v1/documents
GET /api/v1/documents/{documentId}
GET /api/v1/documents/{documentId}/file
POST /api/v1/documents/{documentId}/extract
GET /api/v1/documents/{documentId}/extraction
GET /api/v1/collections
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

Die API gibt keine absoluten Windows-Pfade aus. Sie liefert ausschließlich portable `storage://`-Referenzen und Download-URLs. Der allgemeine Dokumentenkatalog ist nur lesend. Änderungen am Spielbetrieb sind ausschließlich über die gesonderten Wochenend-Endpunkte möglich, die das lokale Spielleiter-Dashboard verwendet.

Tippabgaben werden mit `POST /api/v1/predictor/rounds/{tipRoundId}/submissions` validiert und automatisch im für das Wochenende konfigurierten `submissionsDir` gespeichert. Die API vergibt Abgabe-ID und Zeitstempel selbst. Nur eine geöffnete, nicht abgelaufene Runde mit passender Inhaltsversion wird angenommen. Eine spätere gültige Abgabe desselben Spielernamens zählt bei der Auswertung automatisch als neueste Abgabe.

Die API ist im MVP ausschließlich lokal erreichbar. Vor einer Veröffentlichung im Netzwerk oder Internet müssen Authentifizierung und Zugriffsschutz ergänzt werden. Die Datenbank folgt in einer späteren Ausbaustufe.

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
