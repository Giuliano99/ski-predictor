import sys
import unittest
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(MODULE_ROOT))
VERSION = "sha256-" + "a" * 64

from evaluate_tip_round import build_outcomes, evaluate  # noqa: E402


class EvaluateTipRoundTests(unittest.TestCase):
    def setUp(self):
        self.tip_round = {
            "id": "test-round",
            "contentVersion": VERSION,
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
        submission = {"schemaVersion": 1, "id": "submission-1", "tipRoundId": "test-round", "tipRoundVersion": VERSION, "player": {"id": "max-m", "displayName": "Max M."}, "submittedAt": "2026-01-01T12:00:00Z", "answers": {
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
        self.assertEqual(points["order"], 100)
        self.assertEqual(result["weekendPoints"], 1000)

    def test_dnf_and_dsq_share_last_place_in_either_order(self):
        tip_round = {
            "id": "tie-round",
            "contentVersion": VERSION,
            "races": [{"id": "race-1"}],
            "athletes": [
                {"id": "athlete-a", "starts": [{"raceId": "race-1", "startNumber": 1}]},
                {"id": "athlete-b", "starts": [{"raceId": "race-1", "startNumber": 2}]},
                {"id": "athlete-c", "starts": [{"raceId": "race-1", "startNumber": 3}]},
            ],
            "questions": [{"id": "order", "type": "INTERNAL_RANKING", "evaluationMetric": "INTERNAL_ORDER", "raceIds": ["race-1"], "athleteIds": ["athlete-a", "athlete-b", "athlete-c"], "positions": 3}],
        }
        results = [{"raceId": "race-1", "official": True, "groups": [{
            "id": "u12", "winnerTimeSeconds": 100.0, "slowestClassifiedTimeSeconds": 100.0,
            "entries": [
                {"startNumber": 1, "status": "CLASSIFIED", "rank": 1, "officialTimeSeconds": 100.0, "percentageGap": 0.0},
                {"startNumber": 2, "status": "DNF"},
                {"startNumber": 3, "status": "DSQ"},
            ],
        }]}]
        submission = {"id": "submission", "tipRoundId": "tie-round", "tipRoundVersion": VERSION, "player": {"id": "gg", "displayName": "GG"}, "answers": {"order": ["athlete-a", "athlete-c", "athlete-b"]}}

        evaluation = evaluate(tip_round, results, submission)["questionEvaluations"][0]

        self.assertEqual(evaluation["points"], 100)
        self.assertEqual(evaluation["actualAnswer"]["rankGroups"], [["athlete-a"], ["athlete-b", "athlete-c"]])
        self.assertEqual(set(evaluation["actualAnswer"]["unclassified"]), {"athlete-b", "athlete-c"})

    def test_dns_annuls_named_questions_and_is_removed_from_ranking(self):
        tip_round = {
            "id": "dns-round",
            "contentVersion": VERSION,
            "races": [{"id": "race-1"}],
            "athletes": [
                {"id": "athlete-a", "starts": [{"raceId": "race-1", "startNumber": 1}]},
                {"id": "athlete-b", "starts": [{"raceId": "race-1", "startNumber": 2}]},
            ],
            "questions": [
                {"id": "place", "type": "PLACEMENT", "evaluationMetric": "EXACT_PLACEMENT", "raceIds": ["race-1"], "athleteId": "athlete-b"},
                {"id": "duel", "type": "HEAD_TO_HEAD", "evaluationMetric": "DIRECT_COMPARISON", "raceIds": ["race-1"], "athleteIds": ["athlete-a", "athlete-b"]},
                {"id": "order", "type": "INTERNAL_RANKING", "evaluationMetric": "INTERNAL_ORDER", "raceIds": ["race-1"], "athleteIds": ["athlete-a", "athlete-b"], "positions": 2},
            ],
        }
        results = [{"raceId": "race-1", "official": True, "groups": [{
            "id": "u12", "winnerTimeSeconds": 100.0, "slowestClassifiedTimeSeconds": 100.0,
            "entries": [
                {"startNumber": 1, "status": "CLASSIFIED", "rank": 1, "officialTimeSeconds": 100.0, "percentageGap": 0.0},
                {"startNumber": 2, "status": "DNS"},
            ],
        }]}]
        submission = {"id": "submission", "tipRoundId": "dns-round", "tipRoundVersion": VERSION, "player": {"id": "gg", "displayName": "GG"}, "answers": {"place": "2", "duel": "athlete-a", "order": ["athlete-b", "athlete-a"]}}

        result = evaluate(tip_round, results, submission)
        evaluations = {item["questionId"]: item for item in result["questionEvaluations"]}

        self.assertEqual(evaluations["place"]["status"], "ANNULLED")
        self.assertEqual(evaluations["duel"]["status"], "ANNULLED")
        self.assertEqual(evaluations["order"]["points"], 100)
        self.assertEqual(evaluations["order"]["actualAnswer"]["dns"], ["athlete-b"])

    def test_dnf_gets_virtual_last_place_for_placement_question(self):
        tip_round = {
            "id": "placement-round",
            "contentVersion": VERSION,
            "races": [{"id": "race-1"}],
            "athletes": [{"id": "athlete-b", "starts": [{"raceId": "race-1", "startNumber": 2}]}],
            "questions": [{"id": "place", "type": "PLACEMENT", "evaluationMetric": "EXACT_PLACEMENT", "raceIds": ["race-1"], "athleteId": "athlete-b"}],
        }
        results = [{"raceId": "race-1", "official": True, "groups": [{
            "id": "u12", "winnerTimeSeconds": 100.0, "slowestClassifiedTimeSeconds": 105.0,
            "entries": [
                {"startNumber": 1, "status": "CLASSIFIED", "rank": 1, "officialTimeSeconds": 100.0, "percentageGap": 0.0},
                {"startNumber": 2, "status": "DNF"},
            ],
        }]}]
        submission = {"id": "submission", "tipRoundId": "placement-round", "tipRoundVersion": VERSION, "player": {"id": "gg", "displayName": "GG"}, "answers": {"place": "2"}}

        evaluation = evaluate(tip_round, results, submission)["questionEvaluations"][0]

        self.assertEqual(evaluation["actualAnswer"], 2)
        self.assertEqual(evaluation["points"], 100)

    def test_submission_from_another_tip_round_is_rejected(self):
        submission = {"id": "submission-1", "tipRoundId": "another-round", "tipRoundVersion": VERSION, "player": {"id": "max-m", "displayName": "Max M."}, "answers": {}}
        with self.assertRaisesRegex(ValueError, "belongs to tip round"):
            evaluate(self.tip_round, self.results, submission)

    def test_submission_from_another_content_version_is_rejected(self):
        submission = {"id": "submission-1", "tipRoundId": "test-round", "tipRoundVersion": "sha256-" + "b" * 64, "player": {"id": "max-m", "displayName": "Max M."}, "answers": {}}
        with self.assertRaisesRegex(ValueError, "content version"):
            evaluate(self.tip_round, self.results, submission)

    def test_incomplete_submission_is_rejected(self):
        submission = {"id": "submission-1", "tipRoundId": "test-round", "tipRoundVersion": VERSION, "player": {"id": "max-m", "displayName": "Max M."}, "answers": {}}
        with self.assertRaisesRegex(ValueError, "missing answers"):
            evaluate(self.tip_round, self.results, submission)

    def test_best_result_uses_best_race_even_if_another_race_is_dsq(self):
        tip_round = {
            "id": "weekend",
            "contentVersion": VERSION,
            "races": [{"id": "race-1"}, {"id": "race-2"}],
            "athletes": [
                {"id": "victoria", "starts": [{"raceId": "race-1", "startNumber": 5}, {"raceId": "race-2", "startNumber": 7}]},
                {"id": "julia", "starts": [{"raceId": "race-1", "startNumber": 45}, {"raceId": "race-2", "startNumber": 43}]},
            ],
            "questions": [{"id": "best", "type": "ATHLETE", "evaluationMetric": "BEST_RESULT", "raceIds": ["race-1", "race-2"], "athleteIds": ["victoria", "julia"]}],
        }
        results = [
            {"raceId": "race-1", "official": True, "groups": [{"id": "u8", "winnerTimeSeconds": 57.22, "slowestClassifiedTimeSeconds": 60.0, "entries": [{"startNumber": 5, "status": "CLASSIFIED", "rank": 1, "officialTimeSeconds": 57.22, "percentageGap": 0.0}, {"startNumber": 45, "status": "CLASSIFIED", "rank": 2, "officialTimeSeconds": 58.0, "percentageGap": 1.36}]}]},
            {"raceId": "race-2", "official": True, "groups": [{"id": "u8", "winnerTimeSeconds": 55.0, "slowestClassifiedTimeSeconds": 58.0, "entries": [{"startNumber": 7, "status": "DSQ"}, {"startNumber": 43, "status": "CLASSIFIED", "rank": 2, "officialTimeSeconds": 56.0, "percentageGap": 1.82}]}]},
        ]
        submission = {"id": "submission", "tipRoundId": "weekend", "tipRoundVersion": VERSION, "player": {"id": "bb", "displayName": "BB"}, "answers": {"best": "victoria"}}
        result = evaluate(tip_round, results, submission)
        evaluation = result["questionEvaluations"][0]
        self.assertEqual(evaluation["points"], 100)
        self.assertEqual(evaluation["actualAnswer"]["winner"], "victoria")
        self.assertNotIn("victoria", evaluation["actualAnswer"]["unclassified"])


if __name__ == "__main__":
    unittest.main()
