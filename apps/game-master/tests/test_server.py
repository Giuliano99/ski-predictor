from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SOURCE_DIRECTORY = Path(__file__).resolve().parents[3] / "services" / "api" / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))
import workflow_service as SERVER  # noqa: E402


class DashboardTests(unittest.TestCase):
    def test_safe_filename_removes_directories_and_rejects_wrong_type(self) -> None:
        self.assertEqual(SERVER.safe_filename("../../Startliste März.pdf", ".pdf"), "Startliste März.pdf")
        with self.assertRaises(SERVER.WorkflowError):
            SERVER.safe_filename("tip.exe", ".json")

    def test_report_summary_extracts_status_and_issues(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.md"
            report.write_text(
                "# Bericht\n\n**Status: WARNUNGEN**\n\n## Fehler\n\n- Keine blockierenden Fehler.\n\n"
                "## Warnungen\n\n- Bitte Zuordnung kontrollieren.\n\n## Hinweise\n\n- 2 Dateien geprüft.\n",
                encoding="utf-8",
            )
            summary = SERVER.report_summary(report)
        self.assertEqual(summary["status"], "WARNUNGEN")
        self.assertEqual(summary["errors"], [])
        self.assertEqual(summary["warnings"], ["Bitte Zuordnung kontrollieren."])

    def test_weekend_state_allows_open_only_after_ready_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            config_directory = workspace / "config" / "weekends"
            config_directory.mkdir(parents=True)
            start_directory = workspace / "data" / "starts"
            result_directory = workspace / "data" / "results"
            submission_directory = workspace / "data" / "submissions"
            for path in (start_directory, result_directory, submission_directory):
                path.mkdir(parents=True)
            (start_directory / "start.pdf").write_bytes(b"pdf")
            questions = workspace / "questions.md"
            questions.write_text("# Ausreichend lange Fragenvorlage", encoding="utf-8")
            review = workspace / "review.md"
            review.write_text("# Bericht\n\n**Status: BEREIT**\n", encoding="utf-8")
            config = {
                "id": "tip-round-2030-01-05", "seasonId": "2029-2030", "status": "DRAFT",
                "questionsFile": "questions.md", "startListsDirectory": "data/starts", "resultsDirectory": "data/results",
                "startLists": [], "results": [], "submissionsDir": "data/submissions",
                "tipRound": {"title": "Test", "testMode": False},
                "reviewReport": "review.md", "resultReviewReport": "result-review.md",
            }
            config_path = config_directory / "tip-round-2030-01-05.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with patch.object(SERVER, "WORKSPACE", workspace), patch.object(SERVER, "CONFIG_DIRECTORY", config_directory):
                state = SERVER.weekend_state(config_path)
        self.assertTrue(state["actions"]["prepare"])
        self.assertTrue(state["actions"]["open"])
        self.assertFalse(state["actions"]["evaluate"])


if __name__ == "__main__":
    unittest.main()
