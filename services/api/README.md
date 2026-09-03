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
GET /api/v1/collections
GET /api/v1/weekends
GET /api/v1/predictor/rounds/current
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

Die API gibt keine absoluten Windows-Pfade aus. Sie liefert ausschließlich portable `storage://`-Referenzen und Download-URLs. Der allgemeine Dokumentenkatalog ist nur lesend. Änderungen am Spielbetrieb sind ausschließlich über die gesonderten Wochenend-Endpunkte möglich, die das lokale Spielleiter-Dashboard verwendet. Datenbank und Authentifizierung folgen in späteren Ausbaustufen.
