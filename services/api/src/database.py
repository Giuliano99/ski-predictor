"""SQLite/PostgreSQL persistence for reusable ski data and Predictor submissions."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable


WORKSPACE = Path(__file__).resolve().parents[3]
POSTGRES_MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
SQLITE_MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations-sqlite"


class DatabaseError(RuntimeError):
    pass


def database_url(workspace: Path = WORKSPACE) -> str | None:
    configured = os.environ.get("DATABASE_URL", "").strip()
    if configured:
        return configured
    path = workspace / "config" / "database.local.json"
    if not path.is_file():
        return None
    settings = json.loads(path.read_text(encoding="utf-8"))
    provider = settings.get("provider")
    if provider == "postgresql":
        return str(settings.get("url", "")).strip() or None
    if provider == "sqlite":
        configured_path = Path(str(settings.get("path", "data/database/ski-predictor.sqlite3")))
        resolved = configured_path if configured_path.is_absolute() else workspace / configured_path
        return f"sqlite:///{resolved.resolve().as_posix()}"
    raise DatabaseError("Der konfigurierte Datenbank-Provider wird nicht unterstützt.")


def driver():
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError as error:
        raise DatabaseError(
            "Der PostgreSQL-Treiber fehlt. Bitte 'pip install -r services/api/requirements.txt' ausführen."
        ) from error
    return psycopg, Jsonb


class PostgreSQLDatabase:
    provider_name = "PostgreSQL"

    def __init__(self, url: str):
        self.url = url

    def connect(self):
        psycopg, _ = driver()
        try:
            return psycopg.connect(self.url, connect_timeout=3)
        except Exception as error:
            raise DatabaseError(f"PostgreSQL ist nicht erreichbar: {error}") from error

    def migrate(self) -> list[str]:
        applied: list[str] = []
        with self.connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            known = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
            for path in sorted(POSTGRES_MIGRATIONS.glob("*.sql")):
                if path.stem in known:
                    continue
                for statement in path.read_text(encoding="utf-8").split(";"):
                    if statement.strip():
                        connection.execute(statement)
                connection.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,))
                applied.append(path.stem)
        return applied

    def ping(self) -> bool:
        with self.connect() as connection:
            return connection.execute("SELECT 1").fetchone() == (1,)

    def json_value(self, value: Any) -> Any:
        _, Jsonb = driver()
        return Jsonb(value)

    def sync_documents(self, documents: Iterable[Any]) -> int:
        rows = list(documents)
        with self.connect() as connection:
            for document in rows:
                connection.execute(
                    """INSERT INTO source_documents
                    (id, content_hash, kind, original_name, storage_reference, size_bytes, modified_at,
                     media_type, season_id, weekend_date, archived)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                      content_hash=excluded.content_hash, kind=excluded.kind,
                      original_name=excluded.original_name, storage_reference=excluded.storage_reference,
                      size_bytes=excluded.size_bytes, modified_at=excluded.modified_at,
                      media_type=excluded.media_type, season_id=excluded.season_id,
                      weekend_date=excluded.weekend_date, archived=excluded.archived""",
                    (document.document_id, f"sha256-{document.content_hash}", document.kind,
                     document.original_name, document.storage_reference, document.size_bytes,
                     document.modified_at, document.media_type, document.season_id,
                     document.weekend_date, document.archived),
                )
        return len(rows)

    def save_extraction(
        self,
        job: dict[str, Any],
        document: Any,
        raw: dict[str, Any],
        normalized: dict[str, Any],
        review: dict[str, Any],
        source_text: str,
    ) -> None:
        Jsonb = self.json_value
        self.sync_documents([document])
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO extraction_imports
                (id, document_id, source_content_hash, extractor_version, source_format, status,
                 extracted_at, raw_payload, normalized_payload, source_text, review_payload)
                VALUES (%s, %s, %s, %s, %s, 'REVIEW_REQUIRED', %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET source_format=excluded.source_format,
                  status='REVIEW_REQUIRED', extracted_at=excluded.extracted_at,
                  raw_payload=excluded.raw_payload, normalized_payload=excluded.normalized_payload,
                  source_text=excluded.source_text, review_payload=excluded.review_payload,
                  approved_at=NULL""",
                (job["jobId"], document.document_id, job["sourceContentHash"], job["extractionVersion"],
                 raw.get("source", {}).get("format"), job.get("completedAt") or job.get("updatedAt"),
                 Jsonb(raw), Jsonb(normalized), source_text.replace("\x00", ""), Jsonb(review)),
            )

    def approve_extraction(self, job: dict[str, Any], artifact: dict[str, Any]) -> None:
        Jsonb = self.json_value
        document_id = artifact["documentId"]
        with self.connect() as connection:
            connection.execute(
                "UPDATE extraction_imports SET status='APPROVED', approved_at=%s, normalized_payload=%s "
                "WHERE id=%s",
                (job.get("approvedAt"), Jsonb(artifact), job["jobId"]),
            )
            event = artifact["event"]
            race = artifact["race"]
            connection.execute(
                """INSERT INTO events (id, name, event_date, location, payload) VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE SET name=excluded.name, event_date=excluded.event_date,
                  location=excluded.location, payload=excluded.payload""",
                (event["id"], event.get("name", "Unbekannt"), event.get("date"), event.get("location"), Jsonb(event)),
            )
            connection.execute(
                """INSERT INTO races (id,event_id,name,race_date,location,discipline,competition_number,payload)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET
                  event_id=excluded.event_id,name=excluded.name,race_date=excluded.race_date,
                  location=excluded.location,discipline=excluded.discipline,
                  competition_number=excluded.competition_number,payload=excluded.payload""",
                (race["id"], event["id"], race["name"], race.get("date"), race.get("location"),
                 race.get("discipline", "OTHER"), race.get("competitionNumber"), Jsonb(race)),
            )
            connection.execute("DELETE FROM race_groups WHERE document_id=%s", (document_id,))
            connection.execute(
                """INSERT INTO race_documents (race_id,document_id,extraction_id,document_type)
                VALUES (%s,%s,%s,%s) ON CONFLICT (race_id,document_id) DO UPDATE SET
                  extraction_id=excluded.extraction_id,document_type=excluded.document_type""",
                (race["id"], document_id, job["jobId"], artifact["documentType"]),
            )
            participant_key = "starters" if artifact["documentType"] == "START_LIST" else "entries"
            participant_type = "START" if participant_key == "starters" else "RESULT"
            for group in artifact.get("groups", []):
                group_id = connection.execute(
                    """INSERT INTO race_groups
                    (race_id,document_id,source_group_id,label,age_class,competition_category,
                     classification_method,winner_time_seconds,slowest_classified_time_seconds,payload)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (race["id"], document_id, group["id"], group.get("label", group["id"]),
                     group.get("ageClass"), group.get("competitionCategory"), group.get("classificationMethod"),
                     group.get("winnerTimeSeconds"), group.get("slowestClassifiedTimeSeconds"), Jsonb(group)),
                ).fetchone()[0]
                for person in group.get(participant_key, []):
                    athlete_id = person.get("athleteId")
                    if athlete_id:
                        connection.execute(
                            """INSERT INTO athletes (id,full_name,display_name,birth_year,target_club,payload)
                            VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET
                              full_name=excluded.full_name,display_name=excluded.display_name,
                              birth_year=COALESCE(excluded.birth_year,athletes.birth_year),
                              target_club=athletes.target_club OR excluded.target_club,
                              payload=excluded.payload,updated_at=now()""",
                            (athlete_id, person["fullName"], person["displayName"], person.get("birthYear"),
                             person.get("targetClub", False), Jsonb(person)),
                        )
                    participant_id = connection.execute(
                        """INSERT INTO race_participants
                        (group_id,document_id,race_id,athlete_id,participant_type,start_number,
                         external_athlete_id,full_name,display_name,birth_year,federation,club,target_club,
                         seed_points,status,rank,official_time_seconds,gap_seconds,percentage_gap,
                         federation_points,payload)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        RETURNING id""",
                        (group_id, document_id, race["id"], athlete_id, participant_type,
                         person["startNumber"], person.get("externalAthleteId"), person["fullName"],
                         person["displayName"], person.get("birthYear"), person.get("federation"),
                         person.get("club"), person.get("targetClub", False), person.get("seedPoints"),
                         person.get("status"), person.get("rank"), person.get("officialTimeSeconds"),
                         person.get("gapSeconds"), person.get("percentageGap"),
                         person.get("federationPoints"), Jsonb(person)),
                    ).fetchone()[0]
                    for run in person.get("runResults", []):
                        connection.execute(
                            "INSERT INTO run_results (participant_id,run_number,status,time_seconds,payload) "
                            "VALUES (%s,%s,%s,%s,%s)",
                            (participant_id, run["runNumber"], run["status"], run.get("timeSeconds"), Jsonb(run)),
                        )

    def save_submission(self, submission: dict[str, Any]) -> None:
        Jsonb = self.json_value
        with self.connect() as connection:
            player = submission["player"]
            connection.execute(
                """INSERT INTO predictor_submissions
                (id,tip_round_id,tip_round_version,player_id,player_display_name,submitted_at,answers,raw_payload)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
                (submission["id"], submission["tipRoundId"], submission["tipRoundVersion"],
                 player["id"], player["displayName"], submission["submittedAt"],
                 Jsonb(submission["answers"]), Jsonb(submission)),
            )

    def counts(self) -> dict[str, int]:
        tables = ("source_documents", "extraction_imports", "events", "races", "athletes",
                  "race_participants", "run_results", "predictor_submissions")
        with self.connect() as connection:
            return {table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in tables}

    @staticmethod
    def _json_result(value: Any) -> Any:
        return json.loads(value) if isinstance(value, str) else value

    @staticmethod
    def _timestamp_result(value: Any) -> str | None:
        if value is None:
            return None
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    def imports(self, document_id: str | None = None) -> list[dict[str, Any]]:
        where = " WHERE document_id=%s" if document_id else ""
        parameters = (document_id,) if document_id else ()
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id,document_id,source_content_hash,extractor_version,source_format,status,"
                "extracted_at,approved_at,length(source_text) FROM extraction_imports" + where +
                " ORDER BY extracted_at DESC",
                parameters,
            ).fetchall()
        return [{
            "id": row[0], "documentId": row[1], "sourceContentHash": row[2],
            "extractorVersion": row[3], "sourceFormat": row[4], "status": row[5],
            "extractedAt": self._timestamp_result(row[6]), "approvedAt": self._timestamp_result(row[7]),
            "sourceTextCharacters": row[8],
        } for row in rows]

    def import_by_id(self, import_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id,document_id,source_content_hash,extractor_version,source_format,status,"
                "extracted_at,approved_at,raw_payload,normalized_payload,source_text,review_payload "
                "FROM extraction_imports WHERE id=%s",
                (import_id,),
            ).fetchone()
        if not row:
            raise DatabaseError("Der Rohimport wurde nicht gefunden.")
        return {
            "id": row[0], "documentId": row[1], "sourceContentHash": row[2],
            "extractorVersion": row[3], "sourceFormat": row[4], "status": row[5],
            "extractedAt": self._timestamp_result(row[6]), "approvedAt": self._timestamp_result(row[7]),
            "raw": self._json_result(row[8]), "normalized": self._json_result(row[9]),
            "sourceText": row[10], "review": self._json_result(row[11]),
        }


class SQLiteConnection:
    """Small compatibility wrapper for the shared parameterized SQL statements."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=10)
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 10000")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA synchronous = NORMAL")

    def __enter__(self) -> "SQLiteConnection":
        return self

    def __exit__(self, exception_type: Any, exception: Any, traceback: Any) -> None:
        if exception_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        self.connection.close()

    def execute(self, statement: str, parameters: Iterable[Any] = ()) -> sqlite3.Cursor:
        translated = statement.replace("%s", "?").replace("now()", "CURRENT_TIMESTAMP")
        return self.connection.execute(translated, tuple(parameters))


class SQLiteDatabase(PostgreSQLDatabase):
    provider_name = "SQLite"

    def __init__(self, path: Path):
        self.path = path.resolve()
        self.url = f"sqlite:///{self.path.as_posix()}"

    def connect(self) -> SQLiteConnection:
        try:
            return SQLiteConnection(self.path)
        except sqlite3.Error as error:
            raise DatabaseError(f"SQLite ist nicht erreichbar: {error}") from error

    def json_value(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def migrate(self) -> list[str]:
        applied: list[str] = []
        with self.connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version text PRIMARY KEY, applied_at text NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            known = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
            for path in sorted(SQLITE_MIGRATIONS.glob("*.sql")):
                if path.stem in known:
                    continue
                for statement in path.read_text(encoding="utf-8").split(";"):
                    if statement.strip():
                        connection.execute(statement)
                connection.execute("INSERT INTO schema_migrations (version) VALUES (?)", (path.stem,))
                applied.append(path.stem)
        return applied


class Database:
    """Provider factory used by the API without leaking database-specific code."""

    @classmethod
    def configured(cls, workspace: Path = WORKSPACE) -> PostgreSQLDatabase | SQLiteDatabase | None:
        url = database_url(workspace)
        if not url:
            return None
        if url.startswith("sqlite:///"):
            return SQLiteDatabase(Path(url.removeprefix("sqlite:///")))
        if url.startswith(("postgresql://", "postgres://")):
            return PostgreSQLDatabase(url)
        raise DatabaseError("Die konfigurierte Datenbank-URL wird nicht unterstützt.")
