import sys
import unittest
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(MODULE_ROOT))

from extract_result_list import (  # noqa: E402
    finalize_group,
    parse_code_classified,
    parse_code_unclassified,
    parse_simple_classified,
    parse_simple_unclassified,
    seconds,
)


class ExtractResultListTests(unittest.TestCase):
    def test_time_conversion(self):
        self.assertEqual(seconds("50,64"), 50.64)
        self.assertEqual(seconds("2:13,06"), 133.06)

    def test_simple_classified_entry(self):
        entry = parse_simple_classified(
            "8 120 SCHLAGBOEHMER, Clara 2013 Skiteam Oberhaching 50,02 50,64 1:40,66 6,90",
            "Skiteam Oberhaching",
        )
        self.assertEqual(entry["status"], "CLASSIFIED")
        self.assertEqual(entry["rank"], 8)
        self.assertAlmostEqual(entry["officialTimeSeconds"], 100.66)

    def test_simple_statuses_are_normalized(self):
        dns = parse_simple_unclassified("--- 162 HERRMANN, Markus 2013 Skiteam Oberhaching NAS NAS", "Skiteam Oberhaching")
        dsq = parse_simple_unclassified("--- 163 PURUNCAJAS, Simon 2013 Skiteam Oberhaching 54,78 DIS", "Skiteam Oberhaching")
        self.assertEqual(dns["status"], "DNS")
        self.assertEqual(dsq["status"], "DSQ")

    def test_code_entries_support_points_and_dnf(self):
        classified = parse_code_classified(
            "5 12 27983 SCHLAGBOEHMER, Clara 2013 BSV-MU Skiteam Oberhaching 1:04,68 1:08,38 2:13,06 3,04 115,66",
            "Skiteam Oberhaching",
        )
        dnf = parse_code_unclassified(
            "--- 29 28219 REICHWALD, Lea 2012 BSV-MU Skiteam Oberhaching 1:09,17 NIZ ---",
            "Skiteam Oberhaching",
        )
        self.assertEqual(classified["externalAthleteId"], "27983")
        self.assertEqual(classified["federationPoints"], 115.66)
        self.assertEqual(dnf["status"], "DNF")

    def test_group_percentages_use_official_total(self):
        group = {
            "entries": [
                {"status": "CLASSIFIED", "officialTimeSeconds": 100.0},
                {"status": "CLASSIFIED", "officialTimeSeconds": 105.0},
                {"status": "DNF"},
            ]
        }
        finalize_group(group)
        self.assertEqual(group["winnerTimeSeconds"], 100.0)
        self.assertEqual(group["slowestClassifiedTimeSeconds"], 105.0)
        self.assertEqual(group["entries"][1]["percentageGap"], 5.0)


if __name__ == "__main__":
    unittest.main()
