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

    def test_rejects_duplicate_athletes_in_podium_and_ranking_answers(self) -> None:
        tip_round = {"questions": [{
            "id": "podium", "type": "PODIUM", "positions": 3,
            "athleteIds": ["athlete-one", "athlete-two", "athlete-three"],
        }]}
        with self.assertRaisesRegex(workflow_service.WorkflowError, "nur einmal"):
            workflow_service.validate_submission_answers(
                tip_round,
                {"podium": ["athlete-one", "athlete-one", "athlete-two"]},
            )

    def test_public_submissions_return_only_latest_current_version_per_player(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            round_id, payload, submissions_directory = self.fixture(root)
            submissions_directory.mkdir(parents=True)
            current_version = payload["tipRoundVersion"]
            values = [
                {"id": "submission-alice-old", "tipRoundId": round_id, "tipRoundVersion": current_version, "player": {"id": "alice", "displayName": "Alice A."}, "submittedAt": "2030-01-01T10:00:00Z", "answers": {"podiums": 2}},
                {"id": "submission-alice-new", "tipRoundId": round_id, "tipRoundVersion": current_version, "player": {"id": "alice", "displayName": "Alice A."}, "submittedAt": "2030-01-01T11:00:00Z", "answers": {"podiums": 4}},
                {"id": "submission-bob", "tipRoundId": round_id, "tipRoundVersion": current_version, "player": {"id": "bob", "displayName": "Bob B."}, "submittedAt": "2030-01-01T09:00:00Z", "answers": {"podiums": 3}},
                {"id": "submission-carol", "tipRoundId": round_id, "tipRoundVersion": "old", "player": {"id": "carol", "displayName": "Carol C."}, "submittedAt": "2030-01-01T12:00:00Z", "answers": {"podiums": 9}},
            ]
            for index, value in enumerate(values):
                (submissions_directory / f"submission-{index}.json").write_text(json.dumps(value), encoding="utf-8")

            with patch.object(workflow_service, "WORKSPACE", root), patch.object(workflow_service, "CONFIG_DIRECTORY", root / "config" / "weekends"):
                evaluation = {"evaluations": [{
                    "submissionId": "submission-alice-new", "tipRoundVersion": current_version,
                    "weekendPoints": 80, "maximumWeekendPoints": 100,
                    "questionEvaluations": [{"questionId": "podiums", "status": "SCORED", "points": 80, "maximumPoints": 100, "scoreExplanation": "Abweichung 1"}],
                }]}
                response = workflow_service.latest_public_submissions(round_id, evaluation=evaluation)

        self.assertEqual(response["total"], 2)
        self.assertEqual([item["player"]["displayName"] for item in response["items"]], ["Alice A.", "Bob B."])
        self.assertEqual(response["items"][0]["answers"]["podiums"], 4)
        self.assertEqual(response["items"][0]["evaluation"]["questions"]["podiums"]["points"], 80)
        self.assertIsNone(response["items"][1]["evaluation"])
        self.assertNotIn("id", response["items"][0])

    def test_start_list_overview_groups_all_starters_and_marks_target_club(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            round_id, _, _ = self.fixture(root)
            start_path = root / "data" / "processed" / "start-list.json"
            start_list = {
                "source": {"fileName": "samstag.pdf"},
                "event": {"name": "Kids Cup", "date": "2030-01-05", "location": "Jochberg", "discipline": "GS"},
                "groups": [{
                    "id": "u10-female", "label": "U10 weiblich", "ageClass": "U10", "competitionCategory": "FEMALE", "birthYears": [2020],
                    "starters": [
                        {"startNumber": 1, "displayName": "Anna A.", "birthYear": 2020, "club": "Skiteam Oberhaching", "targetClub": True},
                        {"startNumber": 2, "displayName": "Bea B.", "birthYear": 2020, "club": "WSV Test", "targetClub": False},
                    ],
                }],
            }
            start_path.write_text(json.dumps(start_list), encoding="utf-8")
            config_path = root / "config" / "weekends" / f"{round_id}.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["startLists"] = [{"output": "data/processed/start-list.json"}]
            config_path.write_text(json.dumps(config), encoding="utf-8")

            with patch.object(workflow_service, "WORKSPACE", root), patch.object(workflow_service, "CONFIG_DIRECTORY", root / "config" / "weekends"):
                response = workflow_service.start_list_overview(round_id)

        self.assertEqual(response["totalStarters"], 2)
        self.assertEqual(response["targetClubStarters"], 1)
        self.assertEqual(response["items"][0]["groups"][0]["starters"][0]["displayName"], "Anna A.")
        self.assertTrue(response["items"][0]["groups"][0]["starters"][0]["targetClub"])

    def test_result_list_overview_keeps_times_statuses_and_federation_points(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            round_id, _, _ = self.fixture(root)
            result_path = root / "data" / "processed" / "result-list.json"
            result_list = {
                "source": {"fileName": "sonntag-ergebnis.pdf"}, "official": True,
                "event": {"name": "Kids Cup", "date": "2030-01-06", "location": "Jochberg", "discipline": "SL"},
                "groups": [{"id": "u14-female", "label": "U14 weiblich", "ageClass": "U14", "competitionCategory": "FEMALE", "classificationMethod": "SUM_VALID_RUNS", "entries": [
                    {"startNumber": 7, "displayName": "Anna A.", "birthYear": 2016, "club": "Skiteam Oberhaching", "targetClub": True, "status": "CLASSIFIED", "rank": 1, "officialTimeSeconds": 93.76, "gapSeconds": 0.0, "percentageGap": 0.0, "federation": "BSV-MU", "federationPoints": 90.51, "runResults": [{"runNumber": 1, "status": "CLASSIFIED", "timeSeconds": 46.69}]},
                    {"startNumber": 8, "displayName": "Bea B.", "birthYear": 2016, "club": "WSV Test", "targetClub": False, "status": "DNF", "runResults": [{"runNumber": 1, "status": "DNF"}]},
                ]}],
            }
            result_path.write_text(json.dumps(result_list), encoding="utf-8")
            config_path = root / "config" / "weekends" / f"{round_id}.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["results"] = [{"output": "data/processed/result-list.json"}]
            config_path.write_text(json.dumps(config), encoding="utf-8")

            with patch.object(workflow_service, "WORKSPACE", root), patch.object(workflow_service, "CONFIG_DIRECTORY", root / "config" / "weekends"):
                response = workflow_service.result_list_overview(round_id)

        entry = response["items"][0]["groups"][0]["entries"][0]
        self.assertEqual(response["totalEntries"], 2)
        self.assertEqual(response["targetClubEntries"], 1)
        self.assertEqual(entry["officialTimeSeconds"], 93.76)
        self.assertEqual(entry["federationPoints"], 90.51)
        self.assertEqual(response["items"][0]["groups"][0]["classificationMethod"], "SUM_VALID_RUNS")

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
