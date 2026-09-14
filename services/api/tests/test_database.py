from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from database import Database, SQLiteDatabase, database_url  # noqa: E402


class DatabaseConfigurationTests(unittest.TestCase):
    def test_environment_overrides_local_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config" / "database.local.json").write_text(
                json.dumps({"provider": "postgresql", "url": "postgresql://local"}), encoding="utf-8"
            )
            with patch.dict(os.environ, {"DATABASE_URL": "postgresql://environment"}):
                self.assertEqual(database_url(root), "postgresql://environment")

    def test_database_is_optional_without_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(Database.configured(Path(directory)))

    def test_sqlite_configuration_resolves_relative_to_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config" / "database.local.json").write_text(
                json.dumps({"provider": "sqlite", "path": "data/test.sqlite3"}), encoding="utf-8"
            )
            configured = Database.configured(root)

            self.assertIsInstance(configured, SQLiteDatabase)
            self.assertEqual(configured.path, (root / "data" / "test.sqlite3").resolve())

    def test_sqlite_stores_raw_text_points_runs_and_submission(self) -> None:
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as directory:
            database = SQLiteDatabase(Path(directory) / "ski.sqlite3")
            self.assertEqual(database.migrate(), ["001_initial", "002_predictor_state", "003_extraction_history", "004_authentication"])
            document = SimpleNamespace(
                document_id="doc-test", content_hash="abc", kind="RESULT_LIST",
                original_name="result.pdf", storage_reference="storage://result.pdf",
                size_bytes=123, modified_at="2030-01-01T00:00:00Z", media_type="application/pdf",
                season_id="2029-2030", weekend_date="2030-01-01", archived=False,
            )
            job = {
                "jobId": "extract-test", "sourceContentHash": "sha256-abc",
                "extractionVersion": "extractor-test", "updatedAt": "2030-01-01T10:00:00Z",
                "approvedAt": "2030-01-01T11:00:00Z",
            }
            person = {
                "athleteId": "athlete-test", "startNumber": 7, "externalAthleteId": "12345",
                "fullName": "Anna Beispiel", "displayName": "Anna B.", "birthYear": 2014,
                "federation": "BSV-MU", "club": "Skiteam Oberhaching", "targetClub": True,
                "status": "CLASSIFIED", "rank": 1, "officialTimeSeconds": 90.5,
                "federationPoints": 42.75,
                "runResults": [{"runNumber": 1, "status": "CLASSIFIED", "timeSeconds": 45.1}],
            }
            raw = {"source": {"format": "RACE_HOROLOGY_CODE"}, "pointsCalculations": [{"fValue": 1010.0}]}
            artifact = {
                "documentId": "doc-test", "documentType": "RACE_RESULT",
                "event": {"id": "event-test", "name": "Testcup", "date": "2030-01-01"},
                "race": {"id": "race-test", "eventId": "event-test", "name": "Testcup",
                         "date": "2030-01-01", "discipline": "GS"},
                "groups": [{"id": "u16-female", "label": "U16 weiblich", "ageClass": "U16",
                            "competitionCategory": "FEMALE", "classificationMethod": "SUM_OF_RUNS",
                            "entries": [person]}],
            }
            database.save_extraction(job, document, raw, artifact, {"status": "BEREIT"}, "Punktezuschlag: 25,00")
            database.approve_extraction(job, artifact)
            replacement_job = {
                **job, "jobId": "extract-replacement", "updatedAt": "2030-01-01T12:00:00Z",
                "approvedAt": "2030-01-01T12:30:00Z",
            }
            replacement_artifact = {
                **artifact, "race": {**artifact["race"], "id": "race-replacement"},
            }
            database.save_extraction(replacement_job, document, raw, replacement_artifact, {"status": "BEREIT"}, "Punktezuschlag: 25,00")
            database.approve_extraction(replacement_job, replacement_artifact)
            database.save_submission({
                "id": "submission-test", "tipRoundId": "tip-round-test-test", "tipRoundVersion": "sha256-test",
                "player": {"id": "player-test", "displayName": "Test"},
                "submittedAt": "2030-01-01T09:00:00Z", "answers": {"q1": "athlete-test"},
            })
            tip_round = {
                "id": "tip-round-2030-01-01", "seasonId": "2029-2030", "title": "Test",
                "status": "OPEN", "contentVersion": "sha256-round",
                "opensAt": "2029-12-20T08:00:00Z", "closesAt": "2030-01-01T00:00:00Z",
                "questions": [{"id": "q1", "type": "ATHLETE", "prompt": "Wer gewinnt?", "raceLabel": "Testcup"}],
            }
            config = {
                "id": tip_round["id"], "seasonId": "2029-2030", "status": "OPEN",
                "statusHistory": [{"status": "OPEN", "changedAt": "2029-12-20T08:00:00Z"}],
            }
            database.save_tip_round(config, tip_round)
            database.save_weekend_evaluation({
                "tipRoundId": tip_round["id"], "seasonId": "2029-2030",
                "tipRoundVersion": "sha256-round", "generatedAt": "2030-01-01T12:00:00Z", "standings": [],
            })
            database.save_season_leaderboard({
                "seasonId": "2029-2030", "generatedAt": "2030-01-01T12:00:00Z", "standings": [],
            })

            with database.connect() as connection:
                points = connection.execute("SELECT federation_points FROM race_participants").fetchone()[0]
                source_text = connection.execute("SELECT source_text FROM extraction_imports WHERE id=%s", (replacement_job["jobId"],)).fetchone()[0]
                import_statuses = dict(connection.execute("SELECT id,status FROM extraction_imports").fetchall())
                race_documents = connection.execute("SELECT race_id FROM race_documents").fetchall()

            self.assertEqual(points, 42.75)
            self.assertIn("Punktezuschlag", source_text)
            self.assertEqual(import_statuses["extract-test"], "SUPERSEDED")
            self.assertEqual(import_statuses["extract-replacement"], "APPROVED")
            self.assertEqual(race_documents, [("race-replacement",)])
            self.assertEqual(database.imports("doc-test")[0]["sourceFormat"], "RACE_HOROLOGY_CODE")
            self.assertEqual(database.import_by_id("extract-test")["raw"]["pointsCalculations"][0]["fValue"], 1010.0)
            self.assertEqual(database.counts()["run_results"], 1)
            self.assertEqual(database.counts()["predictor_submissions"], 1)
            self.assertEqual(database.current_tip_round()["id"], tip_round["id"])
            self.assertEqual(database.weekend_evaluation(tip_round["id"])["tipRoundVersion"], "sha256-round")
            self.assertEqual(database.season_leaderboard("2029-2030")["standings"], [])
            self.assertEqual(database.counts()["predictor_questions"], 1)


if __name__ == "__main__":
    unittest.main()
