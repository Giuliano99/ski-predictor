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


if __name__ == "__main__":
    unittest.main()
