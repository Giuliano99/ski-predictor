import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo


MODULE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(MODULE_ROOT))

from generate_tip_round import (  # noqa: E402
    athlete_id,
    build_snapshot,
    content_version,
    deadline_for_event,
    generate_questions,
    parse_question_markdown,
)


class GenerateTipRoundTests(unittest.TestCase):
    def test_content_version_protects_questions_but_not_lifecycle_status(self):
        document = {
            "id": "round-1",
            "status": "DRAFT",
            "opensAt": "2027-01-11T08:00:00+01:00",
            "closesAt": "2027-01-16T00:00:00+01:00",
            "athletes": [{"id": "athlete-1"}],
            "races": [{"id": "race-1"}],
            "groups": [],
            "questions": [{"id": "question-1", "prompt": "Wer gewinnt?"}],
        }
        draft_version = content_version(document)
        document["status"] = "OPEN"
        self.assertEqual(content_version(document), draft_version)
        document["questions"][0]["prompt"] = "Wer gewinnt das Rennen?"
        self.assertNotEqual(content_version(document), draft_version)

    def test_external_id_is_preferred_for_stable_id(self):
        starter = {
            "externalAthleteId": "12345",
            "fullName": "Anna Mustermann",
            "birthYear": 2014,
            "club": "Skiteam Oberhaching",
        }
        self.assertEqual(athlete_id(starter), "athlete-ext-12345")

    def test_fallback_id_does_not_expose_name(self):
        starter = {
            "fullName": "Anna Mustermann",
            "birthYear": 2014,
            "club": "Skiteam Oberhaching",
        }
        identifier = athlete_id(starter)
        self.assertTrue(identifier.startswith("athlete-local-"))
        self.assertNotIn("anna", identifier)

    def test_deadline_is_saturday_midnight(self):
        zone = ZoneInfo("Europe/Berlin")
        deadline = deadline_for_event(date(2027, 1, 17), zone)
        self.assertEqual(deadline.isoformat(), "2027-01-16T00:00:00+01:00")

    def test_same_athlete_with_later_external_id_is_merged(self):
        starter_without_id = {"startNumber": 1, "fullName": "Anna Mustermann", "displayName": "Anna M.", "birthYear": 2014, "club": "Skiteam Oberhaching", "targetClub": True}
        starter_with_id = {**starter_without_id, "startNumber": 2, "externalAthleteId": "12345"}
        documents = []
        for index, starter in enumerate((starter_without_id, starter_with_id), start=1):
            documents.append((Path(f"start-{index}.json"), {
                "event": {"name": f"Rennen {index}", "date": f"2027-01-{16 + index}", "discipline": "GS"},
                "groups": [{"id": "u12-female", "label": "U12 weiblich", "ageClass": "U12", "competitionCategory": "FEMALE", "starters": [starter]}],
            }))
        athletes, _, _ = build_snapshot(documents)
        self.assertEqual(len(athletes), 1)
        self.assertEqual(athletes[0]["id"], "athlete-ext-12345")
        self.assertEqual(len(athletes[0]["starts"]), 2)

    def test_question_generator_creates_six_to_ten_questions(self):
        athletes = [
            {"id": f"athlete-{index}", "displayName": f"Demo {index}.", "ageClass": "U12"}
            for index in range(1, 6)
        ]
        groups = [{
            "id": "race-demo-u12-female",
            "label": "U12 weiblich",
            "athleteIds": [athlete["id"] for athlete in athletes],
        }]
        questions = generate_questions(athletes, groups)
        self.assertGreaterEqual(len(questions), 6)
        self.assertLessEqual(len(questions), 10)

    def test_manual_markdown_questions_are_parsed(self):
        athletes = [
            {"id": "athlete-anna", "displayName": "Anna M.", "ageClass": "U12"},
            {"id": "athlete-lea", "displayName": "Lea K.", "ageClass": "U12"},
            {"id": "athlete-emilia", "displayName": "Emilia S.", "ageClass": "U12"},
        ]
        races = [{"id": "race-demo", "name": "SVM U12 Cup"}]
        content = """# Fragen

## Wie viele Podiumsplätze gibt es?
ID: podium-count-stable
Typ: ANZAHL
Auswertung: PODIUMSPLAETZE
Rennen: ALLE
Hinweis: Alle Rennen
Minimum: 0
Maximum: 10

## Wer gewinnt den Vergleich?
Typ: DUELL
Rennen: SVM U12 Cup
Hinweis: Offizielles Ergebnis
Personen: Anna M. | Lea K.

## Wer fährt am besten?
Typ: PERSON
Auswertung: BESTES_ERGEBNIS
Rennen: ALLE
Hinweis: Offizielles Ergebnis
Personen: ALLE

## Wie lautet die Reihenfolge?
Typ: REIHENFOLGE
Rennen: ALLE
Hinweis: Offizielles Ergebnis
Personen: ALLE
Positionen: 3

## Wie sieht das Podium aus?
Typ: PODIUM
Rennen: ALLE
Hinweis: Prozentualer Rückstand
Personen: ALLE
Positionen: 3

## Welche Platzierung erreicht Anna M.?
Typ: PLATZIERUNG
Rennen: SVM U12 Cup
Hinweis: Offizielles Ergebnis
Person: Anna M.
Minimum: 1
Maximum: 40
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "questions.md"
            path.write_text(content, encoding="utf-8")
            questions = parse_question_markdown(path, athletes, races)

        self.assertEqual(len(questions), 6)
        self.assertEqual(questions[0]["id"], "podium-count-stable")
        self.assertEqual(questions[1]["athleteIds"], ["athlete-anna", "athlete-lea"])
        self.assertEqual(questions[5]["athleteId"], "athlete-anna")
        self.assertTrue(all(question["raceIds"] == ["race-demo"] for question in questions))

    def test_manual_markdown_requires_six_to_ten_questions(self):
        athletes = [{"id": "athlete-anna", "displayName": "Anna M.", "ageClass": "U12"}]
        races = [{"id": "race-demo", "name": "SVM U12 Cup"}]
        content = "## Eine Frage\nTyp: ANZAHL\nMinimum: 0\nMaximum: 5\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "questions.md"
            path.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "between 6 and 10"):
                parse_question_markdown(path, athletes, races)

    def test_manual_question_can_be_limited_to_age_class(self):
        athletes = [
            {"id": "athlete-u10", "displayName": "Anna M.", "ageClass": "U10"},
            {"id": "athlete-u12", "displayName": "Lea K.", "ageClass": "U12"},
        ]
        races = [{"id": "race-demo", "name": "SVM Cup"}]
        blocks = []
        for index in range(1, 7):
            blocks.append(
                f"## Frage {index}\nTyp: ANZAHL\nAuswertung: TOP_10\nRennen: SVM Cup\n"
                "Altersklasse: U10\nMinimum: 0\nMaximum: 10"
            )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "questions.md"
            path.write_text("\n\n".join(blocks), encoding="utf-8")
            questions = parse_question_markdown(path, athletes, races)

        self.assertEqual(questions[0]["athleteIds"], ["athlete-u10"])
        self.assertEqual(questions[0]["ageClasses"], ["U10"])
        self.assertEqual(questions[0]["raceLabel"], "SVM Cup · U10")

    def test_race_date_disambiguates_repeated_race_name(self):
        athletes = [{"id": "athlete-u12", "displayName": "Anna M.", "ageClass": "U12"}]
        races = [
            {"id": "race-saturday", "name": "Hausfreunde Cup U12", "date": "2027-01-16"},
            {"id": "race-sunday", "name": "Hausfreunde Cup U12", "date": "2027-01-17"},
        ]
        content = "\n\n".join(
            f"## Frage {index}\nTyp: ANZAHL\nAuswertung: TOP_10\nRennen: Hausfreunde Cup U12\n"
            "Renndatum: 2027-01-17\nMinimum: 0\nMaximum: 10"
            for index in range(1, 7)
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "questions.md"
            path.write_text(content, encoding="utf-8")
            questions = parse_question_markdown(path, athletes, races)

        self.assertEqual(questions[0]["raceIds"], ["race-sunday"])

    def test_race_name_tolerates_spacing_around_hyphen_and_umlauts(self):
        athletes = [{"id": "athlete-u14", "displayName": "Clara S.", "ageClass": "U14"}]
        races = [{"id": "race-mini", "name": "MINI München Cup 2 Willi-Wein- Gedächtnisrennen RS", "date": "2026-01-03"}]
        content = "\n\n".join(
            f"## Frage {index}\nTyp: ANZAHL\nAuswertung: TOP_10\n"
            "Rennen: MINI Munchen Cup 2 Willi-Wein-Gedachtnisrennen RS\nMinimum: 0\nMaximum: 10"
            for index in range(1, 7)
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "questions.md"
            path.write_text(content, encoding="utf-8")
            questions = parse_question_markdown(path, athletes, races)

        self.assertTrue(all(question["raceIds"] == ["race-mini"] for question in questions))

    def test_manual_markdown_requires_race_scope(self):
        athletes = [{"id": "athlete-anna", "displayName": "Anna M.", "ageClass": "U12"}]
        races = [{"id": "race-demo", "name": "SVM U12 Cup"}]
        content = "\n\n".join(
            f"## Frage {index}\nTyp: ANZAHL\nAuswertung: PODIUMSPLAETZE\nMinimum: 0\nMaximum: 5"
            for index in range(1, 7)
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "questions.md"
            path.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Rennen is required"):
                parse_question_markdown(path, athletes, races)


if __name__ == "__main__":
    unittest.main()
