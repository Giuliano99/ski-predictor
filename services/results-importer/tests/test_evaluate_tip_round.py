import sys
import unittest
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(MODULE_ROOT))

from evaluate_tip_round import build_outcomes, evaluate  # noqa: E402


class EvaluateTipRoundTests(unittest.TestCase):
    def setUp(self):
        self.tip_round = {
            "id": "test-round",
            "races": [{"id": "race-1"}],
            "athletes": [
                {"id": "athlete-a", "starts": [{"raceId": "race-1", "startNumber": 1}]},
                {"id": "athlete-b", "starts": [{"raceId": "race-1", "startNumber": 2}]},
            ],
            "questions": [
                {"id": "podiums", "type": "NUMBER", "evaluationMetric": "PODIUM_COUNT", "raceIds": ["race-1"]},
                {"id": "best", "type": "ATHLETE", "evaluationMetric": "BEST_RESULT", "raceIds": ["race-1"], "athleteIds": ["athlete-a", "athlete-b"]},
                {"id": "gap", "type": "ATHLETE", "evaluationMetric": "LOWEST_PERCENTAGE_GAP", "raceIds": ["race-1"], "athleteIds": ["athlete-a", "athlete-b"]},
                {"id": "place", "type": "PLACEMENT", "evaluationMetric": "EXACT_PLACEMENT", "raceIds": ["race-1"], "athleteId": "athlete-a"},
                {"id": "duel", "type": "HEAD_TO_HEAD", "evaluationMetric": "DIRECT_COMPARISON", "raceIds": ["race-1"], "athleteIds": ["athlete-a", "athlete-b"]},
                {"id": "order", "type": "INTERNAL_RANKING", "evaluationMetric": "INTERNAL_ORDER", "raceIds": ["race-1"], "athleteIds": ["athlete-a", "athlete-b"], "positions": 2},
            ],
        }
        self.results = [{
            "raceId": "race-1",
            "official": True,
            "groups": [{
                "id": "u12-male",
                "winnerTimeSeconds": 100.0,
                "slowestClassifiedTimeSeconds": 105.0,
                "entries": [
                    {"startNumber": 1, "status": "CLASSIFIED", "rank": 1, "officialTimeSeconds": 100.0, "percentageGap": 0.0},
                    {"startNumber": 2, "status": "DNF"},
                ],
            }],
        }]

    def test_penalty_gap_uses_winner_plus_thirty_percent(self):
        outcomes = build_outcomes(self.tip_round, self.results)
        dnf = next(outcome for outcome in outcomes if outcome["athleteId"] == "athlete-b")
        self.assertTrue(dnf["penaltyApplied"])
        self.assertAlmostEqual(dnf["effectivePercentageGap"], 30.0)

    def test_all_question_types_are_scored_and_normalized(self):
        submission = {"schemaVersion": 1, "id": "submission-1", "tipRoundId": "test-round", "submittedAt": "2026-01-01T12:00:00Z", "answers": {
            "podiums": "1",
            "best": "athlete-a",
            "gap": "athlete-a",
            "place": "1",
            "duel": "athlete-a",
            "order": ["athlete-a", "athlete-b"],
        }}
        result = evaluate(self.tip_round, self.results, submission)
        points = {item["questionId"]: item["points"] for item in result["questionEvaluations"]}
        self.assertEqual(points["podiums"], 100)
        self.assertEqual(points["order"], 50)
        self.assertEqual(result["weekendPoints"], 917)

    def test_submission_from_another_tip_round_is_rejected(self):
        submission = {"id": "submission-1", "tipRoundId": "another-round", "answers": {}}
        with self.assertRaisesRegex(ValueError, "belongs to tip round"):
            evaluate(self.tip_round, self.results, submission)

    def test_incomplete_submission_is_rejected(self):
        submission = {"id": "submission-1", "tipRoundId": "test-round", "answers": {}}
        with self.assertRaisesRegex(ValueError, "missing answers"):
            evaluate(self.tip_round, self.results, submission)


if __name__ == "__main__":
    unittest.main()
