from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


SOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from document_catalog import Document  # noqa: E402
from extraction_service import ExtractionService  # noqa: E402


class FakeCatalog:
    def __init__(self, documents: list[Document]):
        self._documents = documents

    def find(self, document_id: str) -> Document | None:
        return next((item for item in self._documents if item.document_id == document_id), None)

    def query(self, *, weekend_date: str | None = None, archived: bool | None = None) -> list[Document]:
        return [item for item in self._documents if not weekend_date or item.weekend_date == weekend_date]


def wait_for_status(service: ExtractionService, job_id: str, expected: set[str]) -> dict:
    for _ in range(300):
        job = service.job(job_id)
        if job["status"] in expected:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not reach {expected}")


class ExtractionServiceTests(unittest.TestCase):
    def document(self, path: Path, kind: str = "START_LIST", document_id: str = "doc-test") -> Document:
        path.write_bytes(b"%PDF fixture")
        return Document(
            document_id=document_id,
            content_hash="a" * 64,
            kind=kind,
            original_name=path.name,
            storage_reference=f"storage://{path.name}",
            size_bytes=path.stat().st_size,
            modified_at="2030-01-01T00:00:00Z",
            media_type="application/pdf",
            season_id="2029-2030",
            weekend_date="2030-01-05",
            archived=False,
            path=path,
        )

    def test_extracts_reviews_approves_and_publishes_race_data(self) -> None:
        raw = {
            "schemaVersion": 1,
            "documentType": "START_LIST",
            "source": {"fileName": "startliste.pdf", "format": "TEST", "extractedAt": "2030-01-01T00:00:00Z"},
            "event": {"name": "Testpokal", "date": "2030-01-05", "location": "Testberg", "discipline": "GS", "competitionNumber": "T-1"},
            "groups": [{"id": "u12", "label": "U12", "ageClass": "U12", "competitionCategory": "MIXED", "starters": [{"startNumber": 1, "displayName": "Anna A.", "fullName": "Anna Beispiel", "birthYear": 2018, "club": "Skiteam Oberhaching", "targetClub": True}]}],
            "warnings": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = self.document(root / "startliste.pdf")
            service = ExtractionService(FakeCatalog([document]), root / "extractions")
            with patch("extraction_service.extract_start_list", return_value=raw):
                job, created = service.start(document.document_id)
                completed = wait_for_status(service, job["jobId"], {"REVIEW_REQUIRED", "FAILED"})
            self.assertTrue(created)
            self.assertEqual(completed["status"], "REVIEW_REQUIRED")
            extraction = service.extraction(document.document_id)
            approved = service.approve(job["jobId"])
            athletes = service.athletes(target_club=True)
            athlete = service.athlete(athletes[0]["id"])
            duplicate, duplicate_created = service.start(document.document_id)
            races = service.races()
            race = service.race(races[0]["id"])

        self.assertEqual(extraction["normalized"]["statistics"]["participants"], 1)
        self.assertIn("Status: BEREIT", extraction["report"])
        self.assertEqual(approved["status"], "APPROVED")
        self.assertTrue(extraction["normalized"]["groups"][0]["starters"][0]["athleteId"].startswith("athlete-"))
        self.assertEqual(len(athletes), 1)
        self.assertEqual(len(athlete["starts"]), 1)
        self.assertFalse(duplicate_created)
        self.assertEqual(duplicate["jobId"], job["jobId"])
        self.assertTrue(races[0]["hasStartList"])
        self.assertEqual(race["event"]["name"], "Testpokal")

    def test_failed_extraction_is_persisted_with_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = self.document(root / "ergebnis.pdf", "RESULT_LIST")
            service = ExtractionService(FakeCatalog([document]), root / "extractions")
            with patch("extraction_service.extract_result_list", side_effect=ValueError("Keine Ergebnisgruppen erkannt")):
                job, _ = service.start(document.document_id)
                completed = wait_for_status(service, job["jobId"], {"FAILED"})
        self.assertEqual(completed["status"], "FAILED")
        self.assertIn("Keine Ergebnisgruppen", completed["error"])

    def test_approval_reconciles_parallel_documents_by_external_id(self) -> None:
        def raw(name: str, filename: str) -> dict:
            return {
                "schemaVersion": 1, "documentType": "START_LIST",
                "source": {"fileName": filename, "format": "TEST", "extractedAt": "2030-01-01T00:00:00Z"},
                "event": {"name": "Testpokal", "date": "2030-01-05", "discipline": "GS"},
                "groups": [{"id": "u12", "label": "U12", "ageClass": "U12", "competitionCategory": "MIXED", "starters": [{"startNumber": 1, "externalAthleteId": "10042", "displayName": f"{name.split()[0]} B.", "fullName": name, "birthYear": 2017, "club": "Skiteam Oberhaching", "targetClub": True}]}],
                "warnings": [],
            }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_document = self.document(root / "samstag.pdf", document_id="doc-samstag")
            second_document = self.document(root / "sonntag.pdf", document_id="doc-sonntag")
            service = ExtractionService(FakeCatalog([first_document, second_document]), root / "extractions")
            with patch("extraction_service.extract_start_list", side_effect=lambda path: raw("Victoria Beispiel", path.name) if path.name == "samstag.pdf" else raw("Viktoria Beispiel", path.name)):
                first_job, _ = service.start(first_document.document_id)
                second_job, _ = service.start(second_document.document_id)
                wait_for_status(service, first_job["jobId"], {"REVIEW_REQUIRED"})
                wait_for_status(service, second_job["jobId"], {"REVIEW_REQUIRED"})
            before_first = service.extraction(first_document.document_id)["normalized"]["groups"][0]["starters"][0]["athleteId"]
            before_second = service.extraction(second_document.document_id)["normalized"]["groups"][0]["starters"][0]["athleteId"]
            service.approve(first_job["jobId"])
            service.approve(second_job["jobId"])
            athletes = service.athletes()

        self.assertNotEqual(before_first, before_second)
        self.assertEqual(len(athletes), 1)
        self.assertEqual(set(athletes[0]["sourceDocumentIds"]), {"doc-samstag", "doc-sonntag"})


if __name__ == "__main__":
    unittest.main()
