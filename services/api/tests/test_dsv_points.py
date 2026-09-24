import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dsv_points import improvement_points, season_projection  # noqa: E402


class DsvPointsTests(unittest.TestCase):
    def test_improvement_formula_uses_single_result_plus_30_for_new_athlete(self):
        points, formula = improvement_points(9999.0, 80.0, None)
        self.assertEqual(110.0, points)
        self.assertEqual("SLbest + 30", formula)

    def test_projection_tracks_best_sl_gs_and_overall_points(self):
        results = [
            {"race": {"id": "sl-1", "date": "2026-01-01", "discipline": "SL"}, "status": "CLASSIFIED", "federationPoints": 90.0},
            {"race": {"id": "gs-1", "date": "2026-01-02", "discipline": "OTHER", "competitionNumber": "1234MRBR"}, "status": "CLASSIFIED", "federationPoints": 70.0},
            {"race": {"id": "sl-2", "date": "2026-01-03", "discipline": "SL"}, "status": "CLASSIFIED", "federationPoints": 60.0},
        ]
        result = season_projection(100.0, results)
        self.assertEqual(60.0, result["slalomPoints"])
        self.assertEqual(70.0, result["giantSlalomPoints"])
        self.assertEqual(65.0, result["overallPoints"])
        self.assertEqual(3, len(result["history"]))


if __name__ == "__main__":
    unittest.main()
