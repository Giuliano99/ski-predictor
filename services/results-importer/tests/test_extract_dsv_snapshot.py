import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "extract_dsv_snapshot.py"
SPEC = importlib.util.spec_from_file_location("extract_dsv_snapshot", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def words(*values):
    return [{"text": text, "x0": x, "top": 100.0} for text, x in values]


class ExtractDsvSnapshotTests(unittest.TestCase):
    def test_ranking_overall_row_keeps_multi_word_fields(self):
        row = words(
            ("118", 41), ("27983", 77), ("SCHLAGBOEHMER", 114), ("Clara", 248),
            ("Maria", 278), ("2012", 383), ("Skiteam", 418), ("Oberhaching", 451),
            ("BSV-MU", 574), ("106,71", 654), ("106,71", 703), ("96", 759), ("46", 800),
        )
        result = MODULE.parse_ranking_row(row, "OVERALL")
        self.assertEqual("27983", result["externalAthleteId"])
        self.assertEqual("Clara Maria", result["firstName"])
        self.assertEqual("Skiteam Oberhaching", result["club"])
        self.assertEqual(118, result["overallRank"])
        self.assertEqual(96, result["ageClassRank"])
        self.assertEqual(46, result["birthYearRank"])
        self.assertEqual(106.71, result["listPoints"])

    def test_ranking_age_class_row_maps_ranks(self):
        row = words(
            ("27", 46), ("27983", 77), ("SCHLAGBOEHMER", 117), ("Clara", 248),
            ("2012", 383), ("Skiteam", 418), ("Oberhaching", 451), ("BSV-MU", 574),
            ("106,71", 654), ("106,71", 703), ("27", 791),
        )
        result = MODULE.parse_ranking_row(row, "AGE_CLASS")
        self.assertEqual(27, result["ageClassRank"])
        self.assertEqual(27, result["birthYearRank"])
        self.assertNotIn("overallRank", result)

    def test_race_count_row_keeps_club_and_points_separate(self):
        row = words(
            ("33759", 66), ("GAUDLITZ", 105), ("Julian", 209), ("2012", 274),
            ("Skiteam", 310), ("Oberhaching", 349), ("BSV-MU", 428),
            ("131,75", 504), ("M", 553), ("103,66", 609), ("20", 652),
        )
        result = MODULE.parse_count_row(row)
        self.assertEqual("Skiteam Oberhaching", result["club"])
        self.assertEqual("MALE", result["gender"])
        self.assertEqual(20, result["raceCount"])
        self.assertEqual(131.75, result["basePoints"])
        self.assertEqual(103.66, result["listPoints"])

    def test_club_end_list_row_keeps_start_points_and_ranks(self):
        row = words(
            ("33759", 25), ("GAUDLITZ", 62), ("Julian", 164), ("2012", 253),
            ("M", 294), ("999,00", 341), ("137,53", 411), ("233", 477),
            ("93", 523), ("38", 561),
        )
        result = MODULE.parse_club_end_list_row(row, "Skiteam Oberhaching")
        self.assertEqual("33759", result["externalAthleteId"])
        self.assertEqual(137.53, result["listPoints"])
        self.assertEqual(93, result["ageClassRank"])
        self.assertEqual(38, result["birthYearRank"])

    def test_season_is_derived_from_snapshot_date(self):
        self.assertEqual("2025-2026", MODULE.season_for(datetime(2026, 4, 12)))
        self.assertEqual("2026-2027", MODULE.season_for(datetime(2026, 9, 13)))

    def test_repairs_known_pdf_encoding_errors(self):
        self.assertEqual("Mädchen SSV-Süd", MODULE.clean_text("M�dchen SSV-S�d"))

    def test_document_id_is_found_before_filename_separator(self):
        path = Path("DSVSA2616_ Anzahl Rennen.pdf")
        self.assertEqual("DSVSA2616", MODULE.document_id(path, ""))

    def test_extracts_season_start_values_from_dsv_text_list(self):
        line = "32924     AFFOLTER            Jakob         2012      Skiteam Oberhaching           BSV-MU       999.00  M"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DSVSA2639.txt"
            path.write_text(line + "\n", encoding="utf-8")
            result = MODULE.extract(path, "DSV_RANKING", "Skiteam Oberhaching")

        self.assertEqual("2026-2027", result["snapshot"]["seasonId"])
        self.assertEqual("SEASON_START_BASE", result["snapshot"]["snapshotKind"])
        self.assertEqual(1, result["statistics"]["targetClubUniqueAthletes"])
        entry = result["sections"][0]["entries"][0]
        self.assertEqual("32924", entry["externalAthleteId"])
        self.assertEqual(999.0, entry["listPoints"])
        self.assertEqual("Skiteam Oberhaching", entry["club"])
        self.assertEqual("U16", entry["ageClass"])
        self.assertEqual(1, entry["ageClassRank"])
        self.assertEqual(1, entry["birthYearRank"])

    def test_text_start_ranks_are_split_by_gender_age_class_and_birth_year(self):
        entries = [
            {"gender": "FEMALE", "birthYear": 2013, "listPoints": 50.0, "lastName": "A", "firstName": "A"},
            {"gender": "FEMALE", "birthYear": 2014, "listPoints": 60.0, "lastName": "B", "firstName": "B"},
            {"gender": "FEMALE", "birthYear": 2013, "listPoints": 60.0, "lastName": "C", "firstName": "C"},
            {"gender": "MALE", "birthYear": 2013, "listPoints": 40.0, "lastName": "D", "firstName": "D"},
        ]
        MODULE.add_text_start_ranks(entries, 2027)
        self.assertEqual([1, 2, 2], [entry["ageClassRank"] for entry in entries[:3]])
        self.assertEqual([1, 1, 2], [entry["birthYearRank"] for entry in entries[:3]])
        self.assertEqual(1, entries[3]["ageClassRank"])


if __name__ == "__main__":
    unittest.main()
