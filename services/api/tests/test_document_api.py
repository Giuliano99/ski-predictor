from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import Mock, patch


SOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from document_catalog import DocumentCatalog, classify_path  # noqa: E402
from server import ApiServer  # noqa: E402


class DocumentCatalogTests(unittest.TestCase):
    def test_classifies_active_and_archived_documents(self) -> None:
        self.assertEqual(
            classify_path(Path("saisons/2025-2026/weekends/2026-03-07/ergebnislisten/rennen.pdf")),
            ("RESULT_LIST", "2025-2026", "2026-03-07", False),
        )
        self.assertEqual(classify_path(Path("archiv/alt/startliste1.pdf")), ("START_LIST", None, None, True))

    def test_catalog_exposes_stable_identity_and_filters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_directory = root / "saisons" / "2025-2026" / "weekends" / "2026-03-07" / "ergebnislisten"
            result_directory.mkdir(parents=True)
            (result_directory / "rennen.pdf").write_bytes(b"%PDF test")
            catalog = DocumentCatalog(root)
            first = catalog.documents()[0]
            second = catalog.documents()[0]
            filtered = catalog.query(kind="RESULT_LIST", weekend_date="2026-03-07")
        self.assertEqual(first.document_id, second.document_id)
        self.assertEqual(first.content_hash, second.content_hash)
        self.assertEqual(len(filtered), 1)
        self.assertNotIn(str(root), json.dumps(first.public_value()))


class DocumentApiTests(unittest.TestCase):
    def running_server(self, root: Path) -> tuple[ApiServer, threading.Thread, str]:
        server = ApiServer(("127.0.0.1", 0), DocumentCatalog(root))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread, f"http://127.0.0.1:{server.server_port}"

    def test_lists_and_downloads_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_directory = root / "saisons" / "2025-2026" / "weekends" / "2026-03-07" / "ergebnislisten"
            result_directory.mkdir(parents=True)
            content = b"%PDF reusable"
            (result_directory / "rennen.pdf").write_bytes(content)
            server, thread, base_url = self.running_server(root)
            try:
                with urllib.request.urlopen(f"{base_url}/api/v1/documents?kind=RESULT_LIST") as response:
                    payload = json.load(response)
                document_id = payload["items"][0]["documentId"]
                with urllib.request.urlopen(f"{base_url}/api/v1/documents/{document_id}/file") as response:
                    downloaded = response.read()
                    etag = response.headers["ETag"]
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(downloaded, content)
        self.assertTrue(etag.startswith('"sha256-'))

    def test_exposes_game_master_workflow_through_versioned_api(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch("server.all_weekends", return_value=[{"id": "tip-round-2030-01-05", "status": "DRAFT"}]):
            server, thread, base_url = self.running_server(Path(directory))
            try:
                with urllib.request.urlopen(f"{base_url}/api/v1/weekends") as response:
                    payload = json.load(response)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
        self.assertEqual(payload["weekends"][0]["id"], "tip-round-2030-01-05")

    def test_accepts_submission_through_public_api(self) -> None:
        accepted = {"message": "gespeichert", "submission": {"id": "submission-server"}}
        with tempfile.TemporaryDirectory() as directory, patch("server.save_submission", return_value=accepted) as save_submission:
            server, thread, base_url = self.running_server(Path(directory))
            request = urllib.request.Request(
                f"{base_url}/api/v1/predictor/rounds/tip-round-2030-01-05/submissions",
                data=json.dumps({"tipRoundId": "tip-round-2030-01-05"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request) as response:
                    payload = json.load(response)
                    status = response.status
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
        self.assertEqual(status, 201)
        self.assertEqual(payload, accepted)
        save_submission.assert_called_once()

    def test_exposes_extraction_jobs_and_approved_races(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "startliste.pdf"
            pdf.write_bytes(b"%PDF test")
            catalog = DocumentCatalog(root)
            document_id = catalog.documents()[0].document_id
            server = ApiServer(("127.0.0.1", 0), catalog)
            server.extractions = Mock()
            server.extractions.start.return_value = ({"jobId": "extract-test", "status": "PENDING"}, True)
            server.extractions.races.return_value = [{"id": "race-test", "name": "Testpokal"}]
            server.extractions.athletes.return_value = [{"id": "athlete-test", "displayName": "Anna A."}]
            server.extractions.merge_athletes.return_value = {"id": "athlete-target", "displayName": "Anna A."}
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            request = urllib.request.Request(
                f"{base_url}/api/v1/documents/{document_id}/extract",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request) as response:
                    extraction_payload = json.load(response)
                    extraction_status = response.status
                with urllib.request.urlopen(f"{base_url}/api/v1/races") as response:
                    race_payload = json.load(response)
                with urllib.request.urlopen(f"{base_url}/api/v1/athletes?targetClub=true") as response:
                    athlete_payload = json.load(response)
                merge_request = urllib.request.Request(
                    f"{base_url}/api/v1/athlete-identities/merge",
                    data=json.dumps({"sourceAthleteId": "athlete-source", "targetAthleteId": "athlete-target"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                with urllib.request.urlopen(merge_request) as response:
                    merge_payload = json.load(response)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
        self.assertEqual(extraction_status, 202)
        self.assertTrue(extraction_payload["created"])
        self.assertEqual(race_payload["items"][0]["id"], "race-test")
        self.assertEqual(athlete_payload["items"][0]["id"], "athlete-test")
        self.assertEqual(merge_payload["athlete"]["id"], "athlete-target")


if __name__ == "__main__":
    unittest.main()
