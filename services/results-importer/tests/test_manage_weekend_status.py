import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(MODULE_ROOT))
VERSION = "sha256-" + "a" * 64

from manage_weekend_status import change_status  # noqa: E402


class ManageWeekendStatusTests(unittest.TestCase):
    def create_workspace(self, status="DRAFT"):
        temporary = tempfile.TemporaryDirectory()
        workspace = Path(temporary.name)
        config_path = workspace / "config.json"
        config = {
            "id": "tip-round-test",
            "status": status,
            "reviewReport": "question-review.md",
            "resultReviewReport": "result-review.md",
            "tipRound": {"output": "tip-round.json", "websiteOutput": "website.json"},
            "weekendEvaluation": {"output": "evaluation.json", "websiteOutput": "evaluation-web.json"},
        }
        config_path.write_text(json.dumps(config), encoding="utf-8")
        (workspace / "tip-round.json").write_text(json.dumps({"status": status, "contentVersion": VERSION}), encoding="utf-8")
        (workspace / "website.json").write_text(json.dumps({"status": status, "contentVersion": VERSION}), encoding="utf-8")
        return temporary, workspace, config_path

    def test_open_requires_ready_report_and_updates_all_artifacts(self):
        temporary, workspace, config_path = self.create_workspace()
        self.addCleanup(temporary.cleanup)
        (workspace / "question-review.md").write_text("**Status: BEREIT**", encoding="utf-8")

        result = change_status(workspace, config_path, "OPEN", datetime(2026, 9, 3, tzinfo=timezone.utc))

        self.assertEqual(result["status"], "OPEN")
        self.assertEqual(json.loads((workspace / "tip-round.json").read_text())["status"], "OPEN")
        self.assertEqual(json.loads((workspace / "website.json").read_text())["status"], "OPEN")
        self.assertEqual(result["statusHistory"][-1]["status"], "OPEN")

    def test_invalid_transition_is_rejected(self):
        temporary, workspace, config_path = self.create_workspace()
        self.addCleanup(temporary.cleanup)

        with self.assertRaisesRegex(ValueError, "DRAFT -> CLOSED"):
            change_status(workspace, config_path, "CLOSED")

    def test_evaluated_requires_result_report_and_evaluation(self):
        temporary, workspace, config_path = self.create_workspace("CLOSED")
        self.addCleanup(temporary.cleanup)
        (workspace / "result-review.md").write_text("**Status: BEREIT**", encoding="utf-8")
        (workspace / "evaluation.json").write_text("{}", encoding="utf-8")

        result = change_status(workspace, config_path, "EVALUATED")

        self.assertEqual(result["status"], "EVALUATED")


if __name__ == "__main__":
    unittest.main()
