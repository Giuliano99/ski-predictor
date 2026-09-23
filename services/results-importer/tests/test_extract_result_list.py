import sys
import unittest
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(MODULE_ROOT))

from extract_result_list import (  # noqa: E402
    finalize_group,
    group_from_line,
    parse_code_classified,
    parse_code_single_classified,
    parse_code_single_unclassified,
    parse_code_unclassified,
    parse_dsvalpin_detail,
    parse_dsvalpin_single_line,
    parse_dsvalpin_without_start_list,
    parse_official_dsv_table,
    points_calculations,
    competition_statistics,
    parse_simple_classified,
    parse_simple_unclassified,
    parse_vola,
    seconds,
)


class ExtractResultListTests(unittest.TestCase):
    def test_preserves_dsv_points_calculation_summary(self) -> None:
        text = """Bewerbsstatistik
Gemeldete Teilnehmer: 142
Gewertete Teilnehmer: 96
Ausgeschiedene Teilnehmer: 46
Zuschlagsberechnung Damen/Mädchen
F-Wert: 1010,00
Berechneter Zuschlag: ( 220,8 + 199,79 - 85,47 ) : 10 = 33,512
Gerundet: 33,51
Punktezuschlag: 33,51
Minimumzuschlag: 25,00
Angewandter Zuschlag: 33,51
Zuschlagsberechnung Herren/Buben
F-Wert: 1010,00
Punktezuschlag: 12,78
Angewandter Zuschlag: 25,00"""

        calculations = points_calculations(text)

        self.assertEqual(calculations[0]["competitionCategory"], "FEMALE")
        self.assertEqual(calculations[0]["calculatedPenalty"], 33.512)
        self.assertEqual(calculations[1]["appliedPenalty"], 25.0)
        self.assertEqual(competition_statistics(text), {
            "registered": 142, "classified": 96, "notClassified": 46,
        })

    def test_vola_result_uses_official_total_and_start_list_identity(self) -> None:
        start_list = {
            "groups": [{
                "id": "u10-female-2016", "label": "weiblich / 2016", "ageClass": "U10",
                "competitionCategory": "FEMALE", "birthYears": [2016],
                "starters": [
                    {"startNumber": 33, "fullName": "Lena Spöttl", "displayName": "Lena S.",
                     "birthYear": 2016, "club": "TSV Vaterstetten", "targetClub": False},
                    {"startNumber": 34, "fullName": "Chiara Huber", "displayName": "Chiara H.",
                     "birthYear": 2016, "club": "TSV Tengling", "targetClub": False},
                ],
            }],
        }
        groups, warnings = parse_vola([
            "Platz Nr. Name und Vorname Jahrgang Verein Lauf 1 Lauf 2 Zeit Strafe Abstand",
            "weiblich / 2016",
            "1 33 Spöttl Lena 2016 TSV Vaterstetten 18.45 18.49 36.94",
            "Nicht am Start - Lauf 1 (1)",
            "34 Huber Chiara 2016 TSV Tengling",
            "Nicht am Start - Lauf 2 (1)",
            "34 Huber Chiara 2016 TSV Tengling",
        ], start_list)

        self.assertEqual(warnings, [])
        self.assertEqual(groups[0]["classificationMethod"], "OFFICIAL_TOTAL")
        self.assertEqual(groups[0]["entries"][0]["officialTimeSeconds"], 36.94)
        self.assertEqual(groups[0]["entries"][0]["fullName"], "Lena Spöttl")
        self.assertEqual(groups[0]["entries"][1]["status"], "DNS")
        self.assertEqual(len(groups[0]["entries"][1]["runResults"]), 2)

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

    def test_simple_classified_entry_allows_one_disqualified_run(self):
        entry = parse_simple_classified(
            "3 5 MUSTERMANN, Anna 2019 Skiteam Oberhaching DIS 59,70 59,70 2,48",
            "Skiteam Oberhaching",
        )
        self.assertEqual(entry["status"], "CLASSIFIED")
        self.assertEqual(entry["runResults"][0]["status"], "DSQ")
        self.assertAlmostEqual(entry["officialTimeSeconds"], 59.70)

    def test_year_specific_youth_group(self):
        group = group_from_line("U8 2019 Mädchen", "U8/U10 Cup")
        self.assertEqual(group["id"], "u8-female-2019")
        self.assertEqual(group["birthYears"], [2019])
        self.assertEqual(group["classificationMethod"], "BEST_VALID_RUN")

    def test_dsvalpin_group_accepts_prefixes_and_slashes(self):
        group = group_from_line("Schüler U10 / männlich / Jg. 2013", "U8/U10 Cup")

        self.assertEqual(group["id"], "u10-male-2013")
        self.assertEqual(group["birthYears"], [2013])

    def test_year_specific_group_accepts_dsvalpin_jg_label(self):
        group = group_from_line("U8 Jg 2016 weiblich", "ROSSIGNOL HERO Kids Cup")
        self.assertEqual(group["id"], "u8-female-2016")
        self.assertEqual(group["birthYears"], [2016])
        self.assertEqual(group["classificationMethod"], "BEST_VALID_RUN")

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

    def test_code_entries_support_single_run_results(self):
        classified = parse_code_single_classified(
            "1 2 32530 HOURLE, Louisa 2013 BSV-MU TSV 1860 Muenchen 55,30 55,30 73,52",
            "Skiteam Oberhaching",
        )
        dnf = parse_code_single_unclassified(
            "--- 27 28219 REICHWALD, Lea 2012 BSV-MU Skiteam Oberhaching NIZ ---",
            "Skiteam Oberhaching",
        )
        self.assertEqual(classified["rank"], 1)
        self.assertEqual(classified["federationPoints"], 73.52)
        self.assertEqual(len(classified["runResults"]), 1)
        self.assertEqual(dnf["status"], "DNF")
        self.assertTrue(dnf["targetClub"])

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

    def test_dsvalpin_detail_with_and_without_difference(self):
        winner = parse_dsvalpin_detail("........... 1:26,33 1. 42,00 44,33", None, 1)
        second = parse_dsvalpin_detail("........... 1,90 1:28,23 2. 43,46 44,77", winner, 2)
        tied = parse_dsvalpin_detail("........... 1,90 1:28,23 43,46 44,77", second, 3)
        self.assertEqual(winner["rank"], 1)
        self.assertAlmostEqual(second["officialTimeSeconds"], 88.23)
        self.assertEqual(tied["rank"], 2)

    def test_dsvalpin_best_run_accepts_a_failed_other_run(self):
        entry = parse_dsvalpin_detail("............ 11,25 1:10,79 5. DIS 1:10,79", None, 5)

        self.assertEqual(entry["status"], "CLASSIFIED")
        self.assertAlmostEqual(entry["officialTimeSeconds"], 70.79)
        self.assertEqual(entry["runResults"][0]["status"], "DSQ")
        self.assertEqual(entry["runResults"][1]["status"], "CLASSIFIED")

    def test_dsvalpin_compact_single_run_result(self):
        winner = parse_dsvalpin_single_line(
            "7 HOURLE Lara .................. 16 TSV 1860 Muenchen 1:00,25 1.",
            None,
            "Skiteam Oberhaching",
        )
        second = parse_dsvalpin_single_line(
            "4 NITZSCHE Annika .................. 16 WSV Glonn 1,45 1:01,70 2.",
            None,
            "Skiteam Oberhaching",
        )
        dns = parse_dsvalpin_single_line(
            "16 ECKEL Theresa .................. 15 Skiteam Oberhaching",
            "DNS",
            "Skiteam Oberhaching",
        )

        self.assertEqual(winner["rank"], 1)
        self.assertAlmostEqual(winner["officialTimeSeconds"], 60.25)
        self.assertAlmostEqual(second["gapSeconds"], 1.45)
        self.assertEqual(dns["status"], "DNS")
        self.assertTrue(dns["targetClub"])

    def test_dsvalpin_result_can_be_read_without_start_list(self):
        groups, warnings = parse_dsvalpin_without_start_list([
            "U14 weiblich",
            "32 ECKEL Marlene 29887 12",
            "Skiteam Oberhaching",
            "BSV-MU 99,41 1:43,87 5. 50,75 53,12",
            "Nicht im Ziel 1. Durchgang",
            "29 WEYEL Marlene 32303 12",
            "Skiteam Oberhaching",
            "BSV-MU",
        ], {"name": "Skiliga Bayern"}, "Skiteam Oberhaching")

        self.assertEqual(warnings, [])
        self.assertEqual(groups[0]["ageClass"], "U14")
        self.assertEqual(groups[0]["entries"][0]["externalAthleteId"], "29887")
        self.assertEqual(groups[0]["entries"][0]["federationPoints"], 99.41)
        self.assertEqual(groups[0]["entries"][1]["status"], "DNF")

    def test_dsvalpin_compact_one_run_table_without_start_list(self):
        groups, warnings = parse_dsvalpin_without_start_list([
            "U14 weiblich Jg 2012",
            "26 FELL Mara 32025 12 SC GARMISCH BSV-WF 0,00 46,97 1.",
            "25 ECKEL Marlene 29887 12 Skiteam Oberhaching BSV-MU 79,78 50,68 8.",
            "Nicht am Start",
            "33 HAIDER Julia 31967 12 BSV-OL SC LENGGRIES",
        ], {"name": "Skiliga Bayern"}, "Skiteam Oberhaching")

        self.assertEqual(warnings, [])
        self.assertEqual(len(groups[0]["entries"]), 3)
        self.assertEqual(groups[0]["entries"][1]["federationPoints"], 79.78)
        self.assertTrue(groups[0]["entries"][1]["targetClub"])
        self.assertEqual(groups[0]["entries"][2]["status"], "DNS")

    def test_official_dsv_table_can_be_read_without_start_list(self):
        groups, warnings = parse_official_dsv_table([
            "Mädchen",
            "1. 24 32059 SMEJKAL Lea 2012 BSV-WF 00:48.14 00:51.44 01:39.58 26,26",
            "SC Garmisch",
            "33. 5 27983 SCHLAGBÖHMER Clara 2013 BSV-MU 00:54.39 00:56.79 01:51.18 143,91",
            "Skiteam Oberhaching",
            "Nicht im Ziel 1. Durchgang",
            "17 32685 KERL Henny 2013 BSV-MU",
            "SC Starnberg",
        ], {"name": "DSV Schülercup U14"}, "Skiteam Oberhaching")

        self.assertEqual(warnings, [])
        self.assertEqual(groups[0]["ageClass"], "U14")
        self.assertEqual(groups[0]["entries"][1]["externalAthleteId"], "27983")
        self.assertEqual(groups[0]["entries"][1]["federationPoints"], 143.91)
        self.assertEqual(groups[0]["entries"][2]["status"], "DNF")


if __name__ == "__main__":
    unittest.main()
