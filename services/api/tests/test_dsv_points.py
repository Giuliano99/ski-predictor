import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dsv_points import (  # noqa: E402
    MAXIMUM_START_POINTS,
    adjusted_season_base,
    improvement_points,
    season_projection,
)


class DsvPointsTests(unittest.TestCase):
    def test_new_athlete_starts_with_regulation_value(self):
        self.assertEqual(999.0, MAXIMUM_START_POINTS)

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
        result = season_projection(100.0, results, "2025-2026")
        self.assertEqual(60.0, result["slalomPoints"])
        self.assertEqual(70.0, result["giantSlalomPoints"])
        self.assertEqual(65.0, result["overallPoints"])
        self.assertEqual(4, len(result["history"]))
        self.assertEqual("2026-01-01", result["history"][0]["date"])
        self.assertEqual("SEASON_START", result["history"][0]["pointKind"])
        self.assertEqual(100.0, result["history"][0]["overallPoints"])

    def test_uses_commercial_rounding_for_half_cent(self):
        points, formula = improvement_points(131.75, 75.71, 131.62)

        self.assertEqual(103.67, points)
        self.assertEqual("0,5 × (SLbest + RSbest)", formula)

    def test_exposes_every_eligible_formula_and_selected_minimum(self):
        result = season_projection(131.75, [
            {"race": {"id": "sl", "date": "2026-03-29", "discipline": "SL"}, "status": "CLASSIFIED", "federationPoints": 75.71},
            {"race": {"id": "gs", "date": "2026-03-28", "discipline": "GS"}, "status": "CLASSIFIED", "federationPoints": 131.62},
        ], "2025-2026")

        self.assertEqual(6, len(result["formulaCandidates"]))
        selected = [item for item in result["formulaCandidates"] if item["selected"]]
        self.assertEqual([{"formula": "0,5 × (SLbest + RSbest)", "value": 103.67, "selected": True}], selected)

    def test_applies_published_season_correction_to_previous_end_value(self):
        self.assertEqual((131.75, -5.78), adjusted_season_base(137.53, "2025-2026", "MALE"))
        self.assertEqual((100.61, -3.06), adjusted_season_base(103.67, "2026-2027", "MALE"))

    def test_end_list_can_prefer_one_discipline_plus_30_even_with_both_results(self):
        result = season_projection(232.51, [
            {"race": {"id": "sl", "date": "2026-03-29", "discipline": "SL"}, "status": "CLASSIFIED", "federationPoints": 174.43},
            {"race": {"id": "gs", "date": "2026-03-28", "discipline": "GS"}, "status": "CLASSIFIED", "federationPoints": 106.06},
        ], "2025-2026")

        self.assertEqual(136.06, result["projectedEndListPoints"])
        self.assertEqual("RSbest + 30", result["projectedEndListFormula"])


if __name__ == "__main__":
    unittest.main()
