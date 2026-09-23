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
            with patch("extraction_service.extract_start_list", return_value=raw):
                replacement, replacement_created = service.start(document.document_id, {"force": True})
                wait_for_status(service, replacement["jobId"], {"REVIEW_REQUIRED", "FAILED"})
            replacement_approved = service.approve(replacement["jobId"])
            previous = service.job(job["jobId"])
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
        self.assertTrue(replacement_created)
        self.assertEqual(replacement_approved["status"], "APPROVED")
        self.assertEqual(previous["status"], "SUPERSEDED")
        self.assertEqual(previous["supersededBy"], replacement["jobId"])
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

    def test_extracts_and_approves_dsv_ranking_for_athlete_profile(self) -> None:
        raw = {
            "schemaVersion": 1,
            "documentType": "DSV_RANKING",
            "source": {"fileName": "DSVSA9999_Ranglisten.pdf", "format": "DSV_RANKING_PDF"},
            "snapshot": {"documentId": "DSVSA9999", "seasonId": "2029-2030",
                         "publishedAt": "2030-09-13T17:39:14", "timezone": "Europe/Berlin"},
            "sections": [{
                "scope": "OVERALL", "label": "TOP 250 Gesamt", "gender": "FEMALE",
                "entries": [{"externalAthleteId": "12345", "firstName": "Anna", "lastName": "BEISPIEL",
                             "birthYear": 2015, "club": "Skiteam Oberhaching", "federation": "BSV-MU",
                             "basePoints": 75.5, "listPoints": 70.25, "overallRank": 42,
                             "ageClassRank": 12, "birthYearRank": 7}],
            }],
            "statistics": {"sections": 1, "entries": 1, "uniqueAthletes": 1,
                           "targetClubEntries": 1, "targetClubUniqueAthletes": 1},
            "warnings": [],
            "rawText": "vollständiger Ranglistentext",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = self.document(root / "DSVSA9999_Ranglisten.pdf", "DSV_RANKING", "doc-ranking")
            service = ExtractionService(FakeCatalog([document]), root / "extractions")
            with patch("extraction_service.extract_dsv_snapshot", return_value=raw):
                job, created = service.start(document.document_id)
                completed = wait_for_status(service, job["jobId"], {"REVIEW_REQUIRED", "FAILED"})
            approved = service.approve(job["jobId"])
            athletes = service.athletes(target_club=True)
            profile = service.athlete(athletes[0]["id"])
            analytics = service.athlete_analytics(athletes[0]["id"])

        self.assertTrue(created)
        self.assertEqual(completed["status"], "REVIEW_REQUIRED")
        self.assertEqual(approved["status"], "APPROVED")
        self.assertEqual(len(profile["rankings"]), 1)
        self.assertEqual(profile["rankings"][0]["ranking"]["listPoints"], 70.25)
        self.assertEqual(profile["rankings"][0]["snapshot"]["seasonId"], "2029-2030")
        self.assertEqual(analytics["seasons"][0]["latestRanking"]["overallRank"], 42)
        self.assertIsNone(analytics["seasons"][0]["listPointsChange"])

    def test_approves_all_ready_documents_of_a_weekend(self) -> None:
        def raw(filename: str) -> dict:
            return {
                "schemaVersion": 1, "documentType": "START_LIST",
                "source": {"fileName": filename, "format": "TEST", "extractedAt": "2030-01-01T00:00:00Z"},
                "event": {"name": filename, "date": "2030-01-05", "discipline": "GS", "competitionNumber": filename},
                "groups": [{"id": "u12", "label": "U12", "ageClass": "U12", "competitionCategory": "MIXED", "starters": [{"startNumber": 1, "displayName": "Anna A.", "fullName": "Anna Beispiel", "birthYear": 2018, "club": "Skiteam Oberhaching", "targetClub": True}]}],
                "warnings": [],
            }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            documents = [
                self.document(root / "samstag.pdf", document_id="doc-samstag"),
                self.document(root / "sonntag.pdf", document_id="doc-sonntag"),
            ]
            service = ExtractionService(FakeCatalog(documents), root / "extractions")
            with patch("extraction_service.extract_start_list", side_effect=lambda path: raw(path.name)):
                jobs = [service.start(document.document_id)[0] for document in documents]
                for job in jobs:
                    wait_for_status(service, job["jobId"], {"REVIEW_REQUIRED", "FAILED"})
            approved = service.approve_ready("2030-01-05")

        self.assertEqual(len(approved), 2)
        self.assertTrue(all(item["status"] == "APPROVED" for item in approved))

    def test_analytics_calculates_points_change_between_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = ExtractionService(FakeCatalog([]), Path(directory) / "extractions")
            athlete = {"id": "athlete-test", "displayName": "Anna B.", "externalIds": ["12345"]}
            rankings = []
            for snapshot_id, published_at, points in (
                ("snapshot-one", "2030-08-01T10:00:00", 100.0),
                ("snapshot-two", "2030-09-01T10:00:00", 92.5),
            ):
                rankings.append({
                    "snapshot": {"id": snapshot_id, "documentId": snapshot_id, "seasonId": "2030-2031", "publishedAt": published_at},
                    "section": {"scope": "OVERALL", "label": "TOP 250 Gesamt", "gender": "FEMALE"},
                    "ranking": {"basePoints": points, "listPoints": points, "overallRank": 50},
                })
            with patch.object(service, "athlete", return_value={**athlete, "starts": [], "results": [], "rankings": rankings, "raceCounts": []}):
                analytics = service.athlete_analytics(athlete["id"])

        season = analytics["seasons"][0]
        self.assertEqual(season["listPointsChange"], -7.5)
        self.assertEqual(season["latestRanking"]["listPoints"], 92.5)

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
