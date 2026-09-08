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

    def test_start_list_creation_date_may_precede_race_date(self):
        results = [
            {
                "path": "result-rs.pdf",
                "event": {
                    "name": "SVM ROSSIGNOL HERO Kids Cup U8 U10",
                    "date": "2023-02-18",
                    "discipline": "GS",
                },
            },
            {
                "path": "result-sl.pdf",
                "event": {
                    "name": "SVM ROSSIGNOL HERO Kids Cup U8 U10",
                    "date": "2023-02-19",
                    "discipline": "SL",
                },
            },
        ]
        starts = [
            {
                "path": "start-rs.json",
                "event": {
                    "name": "SVM ROSSIGNOL HERO Kids Cup U8 U10",
                    "date": "2023-02-15",
                    "discipline": "GS",
                },
            },
            {
                "path": "start-sl.json",
                "event": {
                    "name": "SVM ROSSIGNOL HERO Kids Cup U8 U10",
                    "date": "2023-02-15",
                    "discipline": "SL",
                },
            },
        ]

        matches, errors = match_metadata(results, starts)

        self.assertEqual(errors, [])
        self.assertEqual([item["startList"] for item in matches], ["start-rs.json", "start-sl.json"])

    def test_different_disciplines_never_match_despite_same_name_and_date(self):
        self.assertIsNone(candidate_score(
            {"name": "SVM Cup U10", "date": "2026-03-07", "discipline": "GS"},
            {"name": "SVM Cup U10", "date": "2026-03-07", "discipline": "SL"},
        ))


if __name__ == "__main__":
    unittest.main()
