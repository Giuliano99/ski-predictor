from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

import workflow_service  # noqa: E402


class SubmissionServiceTests(unittest.TestCase):
    def fixture(self, root: Path, status: str = "OPEN") -> tuple[str, dict, Path]:
        round_id = "tip-round-2030-01-05"
        config_directory = root / "config" / "weekends"
        processed_directory = root / "data" / "processed"
        submissions_directory = root / "data" / "submissions"
        config_directory.mkdir(parents=True)
        processed_directory.mkdir(parents=True)
        tip_round = {
            "schemaVersion": 1,
            "id": round_id,
            "status": "OPEN",
            "closesAt": "2030-01-05T00:00:00+01:00",
            "contentVersion": "sha256-" + "a" * 64,
            "questions": [
                {"id": "podiums", "type": "NUMBER", "minimum": 0, "maximum": 10},
                {"id": "winner", "type": "ATHLETE", "athleteIds": ["athlete-one", "athlete-two"]},
            ],
        }
        (processed_directory / "tip-round.json").write_text(json.dumps(tip_round), encoding="utf-8")
        config = {
            "id": round_id,
            "status": status,
            "tipRound": {"output": "data/processed/tip-round.json", "testMode": True},
            "submissionsDir": "data/submissions",
        }
        (config_directory / f"{round_id}.json").write_text(json.dumps(config), encoding="utf-8")
        payload = {
            "schemaVersion": 1,
            "id": "client-value-is-not-trusted",
            "tipRoundId": round_id,
            "tipRoundVersion": tip_round["contentVersion"],
            "player": {"id": "local-giuliano-g", "displayName": "  Giuliano   G. "},
            "submittedAt": "2000-01-01T00:00:00Z",
            "answers": {"podiums": "4", "winner": "athlete-one"},
        }
        return round_id, payload, submissions_directory

    def test_saves_validated_submission_with_server_identity_and_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            round_id, payload, submissions_directory = self.fixture(root)
            with patch.object(workflow_service, "WORKSPACE", root), patch.object(workflow_service, "CONFIG_DIRECTORY", root / "config" / "weekends"):
                response = workflow_service.save_submission(round_id, payload)
            files = list(submissions_directory.glob("*.json"))
            stored = json.loads(files[0].read_text(encoding="utf-8"))

        self.assertEqual(len(files), 1)
        self.assertTrue(stored["id"].startswith("submission-"))
        self.assertNotEqual(stored["submittedAt"], payload["submittedAt"])
        self.assertEqual(stored["player"]["displayName"], "Giuliano G.")
        self.assertEqual(stored["answers"]["podiums"], 4)
        self.assertEqual(response["submission"], stored)

    def test_rejects_outdated_round_version_without_writing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            round_id, payload, submissions_directory = self.fixture(root)
            payload["tipRoundVersion"] = "sha256-" + "b" * 64
            with patch.object(workflow_service, "WORKSPACE", root), patch.object(workflow_service, "CONFIG_DIRECTORY", root / "config" / "weekends"):
                with self.assertRaisesRegex(workflow_service.WorkflowError, "verändert"):
                    workflow_service.save_submission(round_id, payload)
            self.assertFalse(submissions_directory.exists())

    def test_rejects_submission_when_round_is_not_open(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            round_id, payload, submissions_directory = self.fixture(root, status="CLOSED")
            with patch.object(workflow_service, "WORKSPACE", root), patch.object(workflow_service, "CONFIG_DIRECTORY", root / "config" / "weekends"):
                with self.assertRaisesRegex(workflow_service.WorkflowError, "aktuell keine Tipps"):
                    workflow_service.save_submission(round_id, payload)
            self.assertFalse(submissions_directory.exists())

    def test_reset_test_weekend_keeps_inputs_and_removes_old_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "config" / "weekends" / "tip-round-2030-01-05.json"
            tip_round_path = root / "data" / "tip-round.json"
            website_path = root / "web" / "tip-round.json"
            evaluation_path = root / "data" / "evaluation.json"
            evaluation_website_path = root / "web" / "evaluation.json"
            report_path = root / "reports" / "results.md"
            submission_path = root / "submissions" / "tip.json"
            for path in (config_path, tip_round_path, website_path, evaluation_path, evaluation_website_path, report_path, submission_path):
                path.parent.mkdir(parents=True, exist_ok=True)
            tip_round = {"id": "tip-round-2030-01-05", "status": "EVALUATED"}
            tip_round_path.write_text(json.dumps(tip_round), encoding="utf-8")
            website_path.write_text(json.dumps(tip_round), encoding="utf-8")
            evaluation_path.write_text("{}", encoding="utf-8")
            evaluation_website_path.write_text("{}", encoding="utf-8")
            report_path.write_text("ready", encoding="utf-8")
            submission_path.write_text("{}", encoding="utf-8")
            config = {
                "id": "tip-round-2030-01-05",
                "status": "EVALUATED",
                "tipRound": {"testMode": True, "output": "data/tip-round.json", "websiteOutput": "web/tip-round.json"},
                "weekendEvaluation": {"output": "data/evaluation.json", "websiteOutput": "web/evaluation.json"},
                "resultReviewReport": "reports/results.md",
            }
            config_path.write_text(json.dumps(config), encoding="utf-8")

            with patch.object(workflow_service, "WORKSPACE", root):
                workflow_service.reset_test_weekend(config_path)

            reset_config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(reset_config["status"], "DRAFT")
            self.assertEqual(reset_config["statusHistory"][-1]["reason"], "TEST_RESET")
            self.assertEqual(json.loads(tip_round_path.read_text(encoding="utf-8"))["status"], "DRAFT")
            self.assertEqual(json.loads(website_path.read_text(encoding="utf-8"))["status"], "DRAFT")
            self.assertTrue(submission_path.is_file())
            self.assertFalse(evaluation_path.exists())
            self.assertFalse(evaluation_website_path.exists())
            self.assertFalse(report_path.exists())

    def test_production_weekend_cannot_be_reset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"tipRound": {"testMode": False}}), encoding="utf-8")

            with self.assertRaisesRegex(workflow_service.WorkflowError, "Testwochenende"):
                workflow_service.reset_test_weekend(path)


if __name__ == "__main__":
    unittest.main()
