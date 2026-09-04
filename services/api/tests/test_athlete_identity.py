from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from athlete_identity import AthleteIdentityRegistry  # noqa: E402


def person(name: str, external_id: str | None = None) -> dict:
    value = {"fullName": name, "displayName": f"{name.split()[0]} {name.split()[-1][0]}.", "birthYear": 2017, "club": "Skiteam Oberhaching"}
    if external_id:
        value["externalAthleteId"] = external_id
    return value


def artifact(document_id: str, people: list[dict]) -> dict:
    entries = []
    for item in people:
        entries.append(dict(item))
    return {"documentId": document_id, "documentType": "START_LIST", "groups": [{"starters": entries}]}


class AthleteIdentityRegistryTests(unittest.TestCase):
    def test_matches_exact_external_and_similar_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = AthleteIdentityRegistry(Path(directory) / "athletes.json")
            original = person("Victoria Beispiel", "10042")
            first = registry.resolve(original)
            stored = artifact("doc-one", [original | {"athleteId": first["athleteId"]}])
            registry.register_artifact(stored)
            exact = registry.resolve(person("Victoria Beispiel"))
            external = registry.resolve(person("Viktoria Beispiel", "10042"))
            fuzzy = registry.resolve(person("Viktoria Beispiel"))

        self.assertEqual(first["match"], "NEW")
        self.assertEqual(exact["match"], "EXACT")
        self.assertEqual(external["match"], "EXTERNAL_ID")
        self.assertEqual(fuzzy["match"], "FUZZY_REVIEW")
        self.assertEqual({first["athleteId"], exact["athleteId"], external["athleteId"], fuzzy["athleteId"]}, {first["athleteId"]})

    def test_merge_keeps_redirect_to_canonical_athlete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = AthleteIdentityRegistry(Path(directory) / "athletes.json")
            first_person = person("Anna Beispiel")
            second_person = person("Anna Muster")
            first = registry.resolve(first_person)
            second = registry.resolve(second_person)
            registry.register_artifact(artifact("doc-one", [first_person | {"athleteId": first["athleteId"]}, second_person | {"athleteId": second["athleteId"]}]))
            merged = registry.merge(second["athleteId"], first["athleteId"])
            canonical = registry.canonical_id(second["athleteId"])
            athlete_count = len(registry.public_athletes())

        self.assertEqual(merged["id"], first["athleteId"])
        self.assertEqual(canonical, first["athleteId"])
        self.assertEqual(athlete_count, 1)


if __name__ == "__main__":
    unittest.main()
