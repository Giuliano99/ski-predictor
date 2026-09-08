import json
import sys
import unittest
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(MODULE_ROOT))

from evaluate_submissions import build_weekend_evaluation  # noqa: E402


class ReferenceWeekendTests(unittest.TestCase):
    def test_reviewed_weekends_keep_their_expected_scores(self):
        cases = (
            ("reference-weekend-2026-03-07.json", "2025-2026"),
            ("reference-weekend-2027-01-13.json", "2026-2027"),
        )
        for fixture_name, season_id in cases:
            with self.subTest(fixture=fixture_name):
                fixture_path = Path(__file__).parent / "fixtures" / fixture_name
                fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

                evaluation = build_weekend_evaluation(
                    fixture["tipRound"],
                    fixture["results"],
                    fixture["submissions"],
                    season_id,
                )
                standings = [
                    {key: standing[key] for key in ("rank", "playerId", "displayName", "weekendPoints")}
                    for standing in evaluation["standings"]
                ]
                points = {
                    item["player"]["id"]: {
                        question["questionId"]: question["points"]
                        for question in item["questionEvaluations"]
                    }
                    for item in evaluation["evaluations"]
                }

                self.assertEqual(standings, fixture["expected"]["standings"])
                self.assertEqual(points, fixture["expected"]["questionPointsByPlayer"])


if __name__ == "__main__":
    unittest.main()
