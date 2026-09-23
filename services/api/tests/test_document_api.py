from __future__ import annotations

import json
import http.cookiejar
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch


SOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from document_catalog import DocumentCatalog, classify_path  # noqa: E402
import server as server_module  # noqa: E402
from server import ApiServer  # noqa: E402
from auth_service import hash_password  # noqa: E402
from database import SQLiteDatabase  # noqa: E402


class DocumentCatalogTests(unittest.TestCase):
    def test_current_round_prefers_open_weekend_over_newer_finished_weekend(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_directory = root / "config" / "weekends"
            config_directory.mkdir(parents=True)
            (config_directory / "tip-round-2030-03-02.json").write_text(
                json.dumps({"id": "newer", "status": "EVALUATED"}), encoding="utf-8"
            )
            (config_directory / "tip-round-2030-01-05.json").write_text(
                json.dumps({"id": "open", "status": "OPEN"}), encoding="utf-8"
            )

            with patch.object(server_module, "WORKSPACE", root):
                selected = server_module.current_config()

        self.assertEqual(selected["id"], "open")

    def test_classifies_active_and_archived_documents(self) -> None:
        self.assertEqual(
            classify_path(Path("saisons/2025-2026/weekends/2026-03-07/ergebnislisten/rennen.pdf")),
            ("RESULT_LIST", "2025-2026", "2026-03-07", False),
        )
        self.assertEqual(
            classify_path(Path("saisons/2025-2026/ergebnislisten/DSV-Schuelerrennen.pdf")),
            ("RESULT_LIST", "2025-2026", None, False),
        )
        self.assertEqual(classify_path(Path("archiv/alt/startliste1.pdf")), ("START_LIST", None, None, True))
        self.assertEqual(
            classify_path(Path("saisons/2026-2027/ranglisten/DSVSA2638_ Ranglisten.pdf")),
            ("DSV_RANKING", "2026-2027", None, False),
        )
        self.assertEqual(
            classify_path(Path("saisons/2025-2026/rennanzahl/Anzahl der gefahrenen Rennen.pdf")),
            ("DSV_RACE_COUNT", "2025-2026", None, False),
        )

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

    def test_serves_responsive_athlete_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "athletes"
            (app / "assets").mkdir(parents=True)
            (app / "index.html").write_text('<meta name="viewport" content="width=device-width"><main>AthletenAnalyse</main>', encoding="utf-8")
            (app / "import.html").write_text('<meta name="viewport" content="width=device-width"><main>Datenimport</main>', encoding="utf-8")
            (app / "assets" / "athletes.css").write_text("@media (max-width:800px){main{display:block}}", encoding="utf-8")
            (app / "assets" / "import.js").write_text("const importPage = true;", encoding="utf-8")
            with patch.object(server_module, "ATHLETE_DIRECTORY", app):
                server, thread, base_url = self.running_server(root)
                try:
                    with urllib.request.urlopen(f"{base_url}/athleten/") as response:
                        html = response.read().decode("utf-8")
                    with urllib.request.urlopen(f"{base_url}/athleten/assets/athletes.css") as response:
                        css = response.read().decode("utf-8")
                    with urllib.request.urlopen(f"{base_url}/athleten/import.html") as response:
                        import_html = response.read().decode("utf-8")
                    with urllib.request.urlopen(f"{base_url}/athleten/assets/import.js") as response:
                        import_js = response.read().decode("utf-8")
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)

        self.assertIn("width=device-width", html)
        self.assertIn("max-width:800px", css)
        self.assertIn("Datenimport", import_html)
        self.assertIn("importPage", import_js)

    def test_uploads_athlete_data_and_starts_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            server, thread, base_url = self.running_server(root)
            server.extractions.start = Mock(return_value=({"jobId": "extract-test", "status": "PENDING"}, True))
            request = urllib.request.Request(
                f"{base_url}/api/v1/athlete-data/files/rankings?seasonId=2030-2031&filename=ranking.pdf",
                data=b"%PDF ranking", headers={"Content-Type": "application/pdf"}, method="POST",
            )
            try:
                with urllib.request.urlopen(request) as response:
                    payload = json.load(response)
                    status = response.status
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            stored = root / "saisons" / "2030-2031" / "ranglisten" / "ranking.pdf"
            self.assertEqual(stored.read_bytes(), b"%PDF ranking")
        self.assertEqual(status, 201)
        self.assertEqual(payload["job"]["jobId"], "extract-test")

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

    def test_exposes_database_quality_report_for_game_master(self) -> None:
        database = Mock()
        expected = {"status": "WARNUNGEN", "errors": 0, "warnings": 2, "issues": []}
        with tempfile.TemporaryDirectory() as directory, patch("server.audit_database", return_value=expected) as audit:
            root = Path(directory)
            (root / "startliste.pdf").write_bytes(b"%PDF test")
            server = ApiServer(("127.0.0.1", 0), DocumentCatalog(root), database)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/v1/admin/data-quality") as response:
                    payload = json.load(response)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

        self.assertEqual(payload, expected)
        self.assertEqual(len(audit.call_args.args[1]), 1)

    def test_authentication_enforces_player_and_game_master_roles(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "SKI_AUTH_REQUIRED": "1", "SKI_REGISTRATION_CODE": "invite-test",
        }, clear=False), patch("server.all_weekends", return_value=[]):
            root = Path(directory)
            database = SQLiteDatabase(root / "auth.sqlite3")
            database.migrate()
            for user_id, username, role in (("user-player", "spieler", "PLAYER"), ("user-admin", "admin", "GAME_MASTER")):
                database.create_user({
                    "id": user_id, "username": username, "displayName": username.title(),
                    "passwordHash": hash_password("sicheres Passwort 123"), "role": role, "active": True,
                })
            server = ApiServer(("127.0.0.1", 0), DocumentCatalog(root), database)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"

            def login(username: str):
                opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                request = urllib.request.Request(
                    f"{base_url}/api/v1/auth/login",
                    data=json.dumps({"username": username, "password": "sicheres Passwort 123"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                with opener.open(request) as response:
                    return opener, json.load(response)["user"]

            try:
                with self.assertRaises(urllib.error.HTTPError) as unauthorized:
                    urllib.request.urlopen(f"{base_url}/api/v1/weekends")
                registration_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                registration = urllib.request.Request(
                    f"{base_url}/api/v1/auth/register",
                    data=json.dumps({
                        "username": "neu.spieler", "displayName": "Neu Spieler",
                        "password": "sicheres Passwort 456", "inviteCode": "invite-test",
                    }).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST",
                )
                with registration_opener.open(registration) as response:
                    registered = json.load(response)["user"]
                    registration_status = response.status
                with registration_opener.open(f"{base_url}/api/v1/auth/me") as response:
                    registered_session = json.load(response)["user"]
                player_opener, player = login("spieler")
                with player_opener.open(f"{base_url}/api/v1/auth/me") as response:
                    current = json.load(response)["user"]
                with self.assertRaises(urllib.error.HTTPError) as forbidden:
                    player_opener.open(f"{base_url}/api/v1/weekends")
                with player_opener.open(f"{base_url}/tippspiel/") as response:
                    predictor_status = response.status
                accepted_submission = {
                    "id": "submission-authenticated", "tipRoundId": "tip-round-2030-01-05",
                    "player": {"id": player["id"], "displayName": player["displayName"]},
                    "answers": {},
                }
                with patch("server.save_submission", return_value={"submission": accepted_submission}) as save_submission, \
                        patch.object(database, "save_submission"):
                    submission_request = urllib.request.Request(
                        f"{base_url}/api/v1/predictor/rounds/tip-round-2030-01-05/submissions",
                        data=json.dumps({
                            "player": {"id": "fremdes-konto", "displayName": "Fremder Name"},
                            "answers": {},
                        }).encode("utf-8"),
                        headers={"Content-Type": "application/json", "X-CSRF-Token": player["csrfToken"]},
                        method="POST",
                    )
                    with player_opener.open(submission_request) as response:
                        submission_status = response.status
                    protected_payload = save_submission.call_args.args[1]
                logout_without_csrf = urllib.request.Request(f"{base_url}/api/v1/auth/logout", data=b"{}", method="POST")
                with self.assertRaises(urllib.error.HTTPError) as csrf_forbidden:
                    player_opener.open(logout_without_csrf)
                logout = urllib.request.Request(
                    f"{base_url}/api/v1/auth/logout", data=b"{}", method="POST",
                    headers={"X-CSRF-Token": player["csrfToken"]},
                )
                with player_opener.open(logout) as response:
                    logout_status = response.status
                admin_opener, admin = login("admin")
                with admin_opener.open(f"{base_url}/api/v1/weekends") as response:
                    weekends_status = response.status
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

        self.assertEqual(unauthorized.exception.code, 401)
        self.assertEqual(registration_status, 201)
        self.assertEqual(registered_session["id"], registered["id"])
        self.assertEqual(forbidden.exception.code, 403)
        self.assertEqual(csrf_forbidden.exception.code, 403)
        self.assertEqual(current["id"], player["id"])
        self.assertEqual(admin["role"], "GAME_MASTER")
        self.assertEqual(predictor_status, 200)
        self.assertEqual(submission_status, 201)
        self.assertEqual(protected_payload["player"], {"id": player["id"], "displayName": player["displayName"]})
        self.assertEqual(protected_payload["authenticatedUserId"], player["id"])
        self.assertEqual(logout_status, 200)
        self.assertEqual(weekends_status, 200)

    def test_approves_ready_weekend_extractions_in_one_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch("server.weekend_config_path"):
            server, thread, base_url = self.running_server(Path(directory))
            server.extractions = Mock()
            server.extractions.approve_ready.return_value = [{"jobId": "extract-ready", "status": "APPROVED"}]
            request = urllib.request.Request(
                f"{base_url}/api/v1/weekends/tip-round-2030-01-05/extractions/approve-ready",
                data=b"{}", headers={"Content-Type": "application/json"}, method="POST",
            )
            try:
                with urllib.request.urlopen(request) as response:
                    payload = json.load(response)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

        self.assertEqual(len(payload["items"]), 1)
        server.extractions.approve_ready.assert_called_once_with("2030-01-05")

    def test_predictor_reads_round_evaluation_and_leaderboard_from_database(self) -> None:
        database = Mock()
        database.current_tip_round.return_value = {
            "id": "tip-round-2030-01-05", "seasonId": "2029-2030", "status": "OPEN", "questions": [],
        }
        database.weekend_evaluation.return_value = {"tipRoundId": "tip-round-2030-01-05", "standings": []}
        database.season_leaderboard.return_value = {"seasonId": "2029-2030", "standings": []}
        with tempfile.TemporaryDirectory() as directory:
            server = ApiServer(("127.0.0.1", 0), DocumentCatalog(Path(directory)), database)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                with urllib.request.urlopen(f"{base_url}/api/v1/predictor/rounds/current") as response:
                    tip_round = json.load(response)
                with urllib.request.urlopen(f"{base_url}/api/v1/predictor/rounds/tip-round-2030-01-05/evaluation") as response:
                    evaluation = json.load(response)
                with urllib.request.urlopen(f"{base_url}/api/v1/predictor/seasons/2029-2030/leaderboard") as response:
                    leaderboard = json.load(response)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

        self.assertEqual(tip_round["status"], "OPEN")
        self.assertEqual(evaluation["tipRoundId"], tip_round["id"])
        self.assertEqual(leaderboard["seasonId"], "2029-2030")

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
