import sys
import unittest
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(MODULE_ROOT))

from aggregate_season import aggregate_season  # noqa: E402
from evaluate_submissions import latest_submissions, ranked  # noqa: E402


class LeaderboardTests(unittest.TestCase):
    def test_latest_submission_per_player_wins(self):
        submissions = [
            {"id": "old", "submittedAt": "2026-01-01T10:00:00Z", "player": {"id": "max"}},
            {"id": "lena", "submittedAt": "2026-01-01T10:30:00Z", "player": {"id": "lena"}},
            {"id": "new", "submittedAt": "2026-01-01T11:00:00Z", "player": {"id": "max"}},
        ]
        selected = {submission["player"]["id"]: submission["id"] for submission in latest_submissions(submissions)}
        self.assertEqual(selected, {"max": "new", "lena": "lena"})

    def test_equal_points_share_a_rank(self):
        standings = ranked([
            {"displayName": "C", "weekendPoints": 700},
            {"displayName": "B", "weekendPoints": 900},
            {"displayName": "A", "weekendPoints": 900},
        ], "weekendPoints")
        self.assertEqual([(item["displayName"], item["rank"]) for item in standings], [("A", 1), ("B", 1), ("C", 3)])

    def test_season_points_are_summed_without_discarded_rounds(self):
        bundles = [
            {"seasonId": "2026-2027", "tipRoundId": "round-1", "tipRoundVersion": "sha256-" + "a" * 64, "standings": [
                {"playerId": "max", "displayName": "Max M.", "weekendPoints": 800},
                {"playerId": "lena", "displayName": "Lena B.", "weekendPoints": 900},
            ]},
            {"seasonId": "2026-2027", "tipRoundId": "round-2", "tipRoundVersion": "sha256-" + "b" * 64, "standings": [
                {"playerId": "max", "displayName": "Max M.", "weekendPoints": 700},
            ]},
        ]
        season = aggregate_season(bundles)
        max_standing = next(item for item in season["standings"] if item["playerId"] == "max")
        self.assertEqual(max_standing["seasonPoints"], 1500)
        self.assertEqual(max_standing["rounds"], 2)
        self.assertEqual(max_standing["averagePoints"], 750)
        self.assertEqual(max_standing["rank"], 1)
        self.assertEqual(season["tipRoundVersions"]["round-1"], "sha256-" + "a" * 64)


if __name__ == "__main__":
    unittest.main()
