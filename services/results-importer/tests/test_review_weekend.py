import sys
import unittest
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(MODULE_ROOT))

from review_weekend import question_scope_is_clear  # noqa: E402


class ReviewWeekendTests(unittest.TestCase):
    def setUp(self):
        self.races = {
            "race-saturday": {"id": "race-saturday", "name": "Sechzger-Pokal", "day": "Samstag", "discipline": "Riesenslalom"},
            "race-sunday": {"id": "race-sunday", "name": "Gürteler Cup", "day": "Sonntag", "discipline": "Slalom"},
        }

    def test_whole_weekend_scope_is_clear(self):
        question = {"prompt": "Wer ist über alle Rennen des Wochenendes am besten?", "raceIds": list(self.races)}
        self.assertTrue(question_scope_is_clear(question, self.races, set(self.races)))

    def test_specific_race_requires_day_race_and_discipline(self):
        clear = {"prompt": "Wer ist am Samstag im Riesenslalom des Sechzger-Pokals besser?", "raceIds": ["race-saturday"]}
        unclear = {"prompt": "Wer ist besser?", "raceIds": ["race-saturday"]}
        self.assertTrue(question_scope_is_clear(clear, self.races, set(self.races)))
        self.assertFalse(question_scope_is_clear(unclear, self.races, set(self.races)))


if __name__ == "__main__":
    unittest.main()
