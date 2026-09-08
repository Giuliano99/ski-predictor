# Datenbank und Rohimport

## Ziel

Die Renndaten sind ein eigenständiger Datenbestand. Der Ski Predictor ist nur
einer von mehreren möglichen Nutzern. Deshalb liegen Tippabgaben in getrennten
Tabellen und das allgemeine Rennmodell enthält keine Tippspiel-Logik.

## Drei Ebenen

1. Das Original-PDF bleibt unverändert im konfigurierten Storage. Die Datenbank
   speichert Pfad, Dateigröße, Änderungszeit und SHA-256-Prüfsumme.
2. Jeder Parserlauf erzeugt einen versionierten Rohimport. `raw_payload` enthält
   das vollständige extrahierte JSON. `source_text` enthält zusätzlich den
   gesamten auslesbaren PDF-Text. Neue Parser können deshalb später auch Angaben
   erschließen, die heute noch nicht als eigene Spalte modelliert sind.
3. Nach Prüfung und Freigabe entstehen normalisierte Datensätze für Veranstaltung,
   Rennen, Altersklasse, Athlet, Start, Ergebnis und einzelnen Lauf.

Die PDF-Binärdatei wird nicht in der Datenbank dupliziert. Sie bleibt über
`storage_reference` und `content_hash` eindeutig und revisionssicher zugeordnet.

## Ergebnisinformationen

Neben dem vollständigen Rohinhalt sind unter anderem direkt abfragbar:

* Verbandscode, Verein, Jahrgang, Altersklasse und Geschlecht
* Startnummer und Setzpunkte aus Startlisten
* DNS, DNF, DSQ und gewertete Läufe
* Laufzeiten, offizielle Gesamtzeit, Rang und Rückstand
* prozentualer Rückstand
* DSV-Verbands- beziehungsweise Rennpunkte pro Athlet
* F-Wert und berechneter, gerundeter, minimaler sowie angewandter Zuschlag
* offizielle Teilnehmerstatistik

Die vollständigen Tabellen der Zuschlagsberechnung bleiben im `source_text`, auch
wenn sie noch nicht vollständig relational zerlegt werden.

## Predictor-Daten

SQLite ist die primäre Lesequelle der öffentlichen API für veröffentlichte
Tipprunden, Fragen, Tippabgaben, Wochenendauswertungen und Saisonranglisten. Nach
jedem Spielleiter-Schritt werden die erzeugten Fachdaten automatisch synchronisiert.
Die vorhandenen JSON-Dateien bleiben vorerst als nachvollziehbarer Export und
Rückfalloption bestehen.

Die Wochenendauswertung lädt Tippabgaben ebenfalls zuerst aus der Datenbank. Nur
wenn dort für eine Runde noch keine Abgabe liegt, verwendet sie ältere JSON-Exporte.

```text
predictor_rounds
predictor_questions
predictor_round_status_history
predictor_submissions
weekend_evaluations
season_leaderboards
```

## Lokal starten

```powershell
.\scripts\game-master\Initialize-Database.ps1
```

Die lokale SQLite-Datei liegt unter `data/database/ski-predictor.sqlite3` und wird
nicht in Git eingecheckt. Die ignorierte Konfiguration
`config/database.local.json` entsteht automatisch aus
`config/database.example.json`. SQLite benötigt weder Docker noch WSL, keinen
separaten Dienst und keine Adminrechte. Die PDF-Dateien dürfen weiterhin im
OneDrive-Ordner liegen; die aktive SQLite-Datei bleibt bewusst außerhalb davon.

## Raspberry Pi

Auf dem Raspberry Pi wird PostgreSQL verwendet. Die Repository-Schicht hält die
fachlichen Schreibvorgänge für SQLite und PostgreSQL identisch; beide Provider
haben eigene versionierte SQL-Migrationen. Auf dem Pi wird die Verbindung
ausschließlich über `DATABASE_URL` gesetzt. Port 5432 wird nicht ins Internet
freigegeben. Nur die Backend API greift auf PostgreSQL zu. Vor der Umstellung
übernimmt ein Importbefehl den lokalen Roh- und Fachdatenbestand.

Vor dem Umzug werden automatisierte `pg_dump`-Sicherungen, ein Wiederherstellungstest,
TLS für die öffentliche Website und getrennte Produktions-Zugangsdaten ergänzt.
