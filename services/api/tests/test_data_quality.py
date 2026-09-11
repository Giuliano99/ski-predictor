from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


SOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from data_quality import audit_database, render_markdown  # noqa: E402
from database import SQLiteDatabase  # noqa: E402


class DataQualityTests(unittest.TestCase):
    def test_empty_database_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = SQLiteDatabase(Path(directory) / "test.sqlite3")
            database.migrate()
            report = audit_database(database, set())
            self.assertEqual(report["status"], "BEREIT")
            self.assertEqual(report["errors"], 0)
            self.assertIn("Keine Auffaelligkeiten", render_markdown(report))

    def test_unprocessed_document_and_duplicate_identity_are_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = SQLiteDatabase(Path(directory) / "test.sqlite3")
            database.migrate()
            document = SimpleNamespace(
                document_id="doc-test", content_hash="abc", kind="START_LIST",
                original_name="start.pdf", storage_reference="storage://start.pdf",
                size_bytes=123, modified_at="2030-01-01T00:00:00Z", media_type="application/pdf",
                season_id="2029-2030", weekend_date="2030-01-01", archived=False,
            )
            database.sync_documents([document])
            with database.connect() as connection:
                for athlete_id in ("athlete-1", "athlete-2"):
                    connection.execute(
                        "INSERT INTO athletes (id,full_name,display_name,birth_year,target_club,payload) "
                        "VALUES (%s,%s,%s,%s,%s,%s)",
                        (athlete_id, "Anna Beispiel", "Anna B.", 2014, False, json.dumps({})),
                    )
            report = audit_database(database, {"doc-test"})
            codes = {issue["code"] for issue in report["issues"]}
            self.assertEqual(report["status"], "WARNUNGEN")
            self.assertIn("DOCUMENT_WITHOUT_IMPORT", codes)
            self.assertIn("POSSIBLE_DUPLICATE_ATHLETE", codes)

    def test_broken_text_encoding_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = SQLiteDatabase(Path(directory) / "test.sqlite3")
            database.migrate()
            with database.connect() as connection:
                connection.execute(
                    "INSERT INTO athletes (id,full_name,display_name,birth_year,target_club,payload) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    ("athlete-1", "Max M\ufffdller", "Max M.", 2014, False, json.dumps({})),
                )
            report = audit_database(database)
            issue = next(item for item in report["issues"] if item["code"] == "BROKEN_TEXT_ENCODING")
            self.assertEqual(report["status"], "FEHLER")
            self.assertEqual(issue["records"][0]["field"], "full_name")


if __name__ == "__main__":
    unittest.main()
