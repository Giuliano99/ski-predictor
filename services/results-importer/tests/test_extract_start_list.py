import sys
import unittest
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(MODULE_ROOT))

from extract_start_list import (  # noqa: E402
    FORMAT_DSVALPIN,
    FORMAT_RACE_CODE,
    FORMAT_RACE_SIMPLE,
    FORMAT_RECONSTRUCTED,
    detect_format,
    name_from_comma,
    name_without_comma,
    normalize_club,
    parse_code_entry,
    parse_dsvalpin_entry,
    parse_group,
    parse_reconstructed,
    parse_simple_entry,
)


class ExtractStartListTests(unittest.TestCase):
    def test_display_name_from_comma_format(self):
        person = name_from_comma("MUSTERMANN", "Anna Maria")
        self.assertEqual(person.display_name, "Anna Maria M.")

    def test_display_name_from_dsvalpin_format(self):
        person = name_without_comma("VON MUSTERMANN Anna")
        self.assertEqual(person.display_name, "Anna V.")

    def test_club_variants_are_normalized(self):
        self.assertEqual(normalize_club("Skiteam Oberhaching e.V."), "Skiteam Oberhaching")
        self.assertNotEqual(normalize_club("TSV Oberhaching"), "Skiteam Oberhaching")

    def test_group_variants(self):
        first = parse_group("U12 Jg. 2014 weiblich")
        second = parse_group("U14 männlich Jg 2013")
        self.assertEqual(first["competitionCategory"], "FEMALE")
        self.assertEqual(first["birthYears"], [2014])
        self.assertEqual(second["competitionCategory"], "MALE")
        third = parse_group("U8 2019 Mädchen | 5 Starter")
        self.assertEqual(third["competitionCategory"], "FEMALE")
        self.assertEqual(third["birthYears"], [2019])
        self.assertEqual(third["label"], "U8 2019 Mädchen")

    def test_format_detection(self):
        self.assertEqual(detect_format("DSValpin V6.1.0"), FORMAT_DSVALPIN)
        self.assertEqual(detect_format("Stnr Code Teilnehmer"), FORMAT_RACE_CODE)
        self.assertEqual(detect_format("Stnr Teilnehmer JG Verein"), FORMAT_RACE_SIMPLE)
        self.assertEqual(
            detect_format("Aus der offiziellen Ergebnisliste rekonstruiert - Laufzeiten bleiben leer"),
            FORMAT_RECONSTRUCTED,
        )

    def test_reconstructed_rows(self):
        groups, warnings = parse_reconstructed([
            "U14 weiblich | 2 Starter",
            "Stnr", "Code", "Teilnehmer", "JG", "VB", "Verein", "Laufzeit",
            "1", "12345", "MUSTERMANN, Anna", "2013", "BSV-MU", "Skiteam Oberhaching",
            "2", "67890", "BEISPIEL, Lea", "2013", "BSV-MU", "WSV Glonn",
        ], "Skiteam Oberhaching")
        self.assertEqual(warnings, [])
        self.assertEqual(len(groups[0]["starters"]), 2)
        self.assertEqual(groups[0]["starters"][0]["displayName"], "Anna M.")
        self.assertTrue(groups[0]["starters"][0]["targetClub"])

    def test_dsvalpin_row(self):
        row = parse_dsvalpin_entry(
            "21 MUSTERMANN Anna 29885 14 Skiteam Oberhaching BSV-MU ______ ---",
            "Skiteam Oberhaching",
        )
        self.assertEqual(row["externalAthleteId"], "29885")
        self.assertEqual(row["displayName"], "Anna M.")
        self.assertTrue(row["targetClub"])

    def test_race_horology_code_row(self):
        row = parse_code_entry(
            "12 27983 MUSTERMANN, Anna 2013 BSV-MU Skiteam Oberhaching 123.45",
            "Skiteam Oberhaching",
        )
        self.assertEqual(row["seedPoints"], 123.45)
        self.assertTrue(row["targetClub"])

    def test_race_horology_simple_row(self):
        row = parse_simple_entry(
            "120 MUSTERMANN, Anna Maria 2013 Skiteam Oberhaching",
            "Skiteam Oberhaching",
        )
        self.assertEqual(row["displayName"], "Anna Maria M.")
        self.assertTrue(row["targetClub"])


if __name__ == "__main__":
    unittest.main()
