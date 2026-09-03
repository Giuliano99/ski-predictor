from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch


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


if __name__ == "__main__":
    unittest.main()
