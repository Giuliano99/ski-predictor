import sys
import unittest
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(MODULE_ROOT))

from match_result_lists import candidate_score, match_metadata  # noqa: E402


class ResultAssistantTests(unittest.TestCase):
    def test_date_disambiguates_same_race_on_two_days(self):
        results = [{"path": "result-sunday.pdf", "event": {"name": "Stumbaum Hausfreund CUP U12", "date": "2026-03-08", "discipline": "OTHER"}}]
        starts = [
            {"path": "start-saturday.json", "event": {"name": "Stumbaum Hausfreunde Cup U12", "date": "2026-03-07", "discipline": "SL"}},
            {"path": "start-sunday.json", "event": {"name": "Stumbaum Hausfreunde Cup U12", "date": "2026-03-08", "discipline": "GS"}},
        ]

        matches, errors = match_metadata(results, starts)

        self.assertEqual(errors, [])
        self.assertEqual(matches[0]["startList"], "start-sunday.json")

    def test_ambiguous_metadata_is_rejected(self):
        results = [{"path": "result.pdf", "event": {"name": "SVM Cup U12", "date": "", "discipline": "GS"}}]
        starts = [
            {"path": "start-a.json", "event": {"name": "SVM Cup U12", "date": "2026-03-07", "discipline": "GS"}},
            {"path": "start-b.json", "event": {"name": "SVM Cup U12", "date": "2026-03-08", "discipline": "GS"}},
        ]

        matches, errors = match_metadata(results, starts)

        self.assertEqual(matches, [])
        self.assertIn("nicht eindeutig", errors[0])

    def test_mismatching_dates_cannot_be_paired(self):
        self.assertIsNone(candidate_score(
            {"name": "SVM Cup", "date": "2026-03-07"},
            {"name": "SVM Cup", "date": "2026-03-08"},
        ))


if __name__ == "__main__":
    unittest.main()
