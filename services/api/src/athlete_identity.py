"""Persistent athlete identity registry shared by extracted race documents."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


class AthleteIdentityError(RuntimeError):
    pass


def normalized_text(value: Any) -> str:
    folded = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").casefold()
    return re.sub(r"[^a-z0-9]+", " ", folded).strip()


def identity_key(person: dict[str, Any]) -> str:
    return "|".join((normalized_text(person.get("fullName")), str(person.get("birthYear", "")), normalized_text(person.get("club"))))


def athlete_id_for(person: dict[str, Any]) -> str:
    return f"athlete-{hashlib.sha256(identity_key(person).encode('utf-8')).hexdigest()[:16]}"


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


class AthleteIdentityRegistry:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()

    def _empty(self) -> dict[str, Any]:
        return {"schemaVersion": 1, "athletes": [], "redirects": {}}

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return self._empty()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise AthleteIdentityError("Die Athletenkartei ist beschädigt.") from error
        if value.get("schemaVersion") != 1 or not isinstance(value.get("athletes"), list) or not isinstance(value.get("redirects"), dict):
            raise AthleteIdentityError("Die Athletenkartei hat ein unbekanntes Format.")
        return value

    def canonical_id(self, athlete_id: str, registry: dict[str, Any] | None = None) -> str:
        redirects = (registry or self._load()).get("redirects", {})
        seen = set()
        while athlete_id in redirects and athlete_id not in seen:
            seen.add(athlete_id)
            athlete_id = redirects[athlete_id]
        return athlete_id

    def resolve(self, person: dict[str, Any]) -> dict[str, Any]:
        registry = self._load()
        athletes = registry["athletes"]
        key = identity_key(person)
        external_id = str(person.get("externalAthleteId", "")).strip() or None
        external_matches = [item for item in athletes if external_id and external_id in item.get("externalIds", [])]
        exact_matches = [item for item in athletes if key in item.get("identityKeys", [])]

        if external_matches and exact_matches and self.canonical_id(external_matches[0]["id"], registry) != self.canonical_id(exact_matches[0]["id"], registry):
            return {"athleteId": self.canonical_id(external_matches[0]["id"], registry), "match": "CONFLICT", "confidence": 1.0, "warning": f"Verbandscode {external_id} und Name/Geburtsjahr zeigen auf unterschiedliche Athleten."}
        if external_matches:
            return {"athleteId": self.canonical_id(external_matches[0]["id"], registry), "match": "EXTERNAL_ID", "confidence": 1.0}
        if exact_matches:
            return {"athleteId": self.canonical_id(exact_matches[0]["id"], registry), "match": "EXACT", "confidence": 1.0}

        name = normalized_text(person.get("fullName"))
        birth_year = person.get("birthYear")
        club = normalized_text(person.get("club"))
        candidates = []
        for athlete in athletes:
            if athlete.get("birthYear") != birth_year or normalized_text(athlete.get("club")) != club:
                continue
            ratio = SequenceMatcher(None, name, normalized_text(athlete.get("fullName"))).ratio()
            if ratio >= 0.9:
                candidates.append((ratio, athlete))
        candidates.sort(key=lambda item: item[0], reverse=True)
        if candidates and (len(candidates) == 1 or candidates[0][0] - candidates[1][0] >= 0.05):
            ratio, athlete = candidates[0]
            return {
                "athleteId": self.canonical_id(athlete["id"], registry),
                "match": "FUZZY_REVIEW",
                "confidence": round(ratio, 4),
                "warning": f"{person.get('displayName') or person.get('fullName')} wurde ähnlich zu {athlete.get('displayName')} erkannt. Bitte Identität prüfen.",
            }
        return {"athleteId": athlete_id_for(person), "match": "NEW", "confidence": 1.0}

    def register_artifact(self, artifact: dict[str, Any]) -> None:
        with self._lock:
            registry = self._load()
            by_id = {item["id"]: item for item in registry["athletes"]}
            participant_key = "starters" if artifact.get("documentType") == "START_LIST" else "entries"
            for group in artifact.get("groups", []):
                for person in group.get(participant_key, []):
                    athlete_id = self.canonical_id(str(person["athleteId"]), registry)
                    athlete = by_id.get(athlete_id)
                    if not athlete:
                        athlete = {
                            "id": athlete_id,
                            "fullName": person.get("fullName"),
                            "displayName": person.get("displayName"),
                            "birthYear": person.get("birthYear"),
                            "club": person.get("club"),
                            "externalIds": [],
                            "identityKeys": [],
                            "aliases": [],
                            "sourceDocumentIds": [],
                        }
                        registry["athletes"].append(athlete)
                        by_id[athlete_id] = athlete
                    external_id = str(person.get("externalAthleteId", "")).strip()
                    if external_id and external_id not in athlete["externalIds"]:
                        athlete["externalIds"].append(external_id)
                    key = identity_key(person)
                    if key not in athlete["identityKeys"]:
                        athlete["identityKeys"].append(key)
                    alias = {field: person.get(field) for field in ("fullName", "displayName", "birthYear", "club")}
                    if alias not in athlete["aliases"]:
                        athlete["aliases"].append(alias)
                    document_id = artifact.get("documentId")
                    if document_id and document_id not in athlete["sourceDocumentIds"]:
                        athlete["sourceDocumentIds"].append(document_id)
            atomic_json(self.path, registry)

    def public_athletes(self, target_club: bool | None = None) -> list[dict[str, Any]]:
        registry = self._load()
        athletes = []
        for item in registry["athletes"]:
            canonical = self.canonical_id(item["id"], registry)
            if canonical != item["id"]:
                continue
            is_target = normalized_text(item.get("club")) == "skiteam oberhaching"
            if target_club is not None and is_target != target_club:
                continue
            athletes.append({key: value for key, value in item.items() if key != "identityKeys"} | {"targetClub": is_target})
        return sorted(athletes, key=lambda item: (item.get("displayName") or "").casefold())

    def athlete(self, athlete_id: str) -> dict[str, Any]:
        registry = self._load()
        canonical = self.canonical_id(athlete_id, registry)
        item = next((item for item in self.public_athletes() if item["id"] == canonical), None)
        if not item:
            raise AthleteIdentityError("Der Athlet wurde nicht gefunden.")
        return item | {"requestedAthleteId": athlete_id, "canonicalAthleteId": canonical}

    def merge(self, source_id: str, target_id: str) -> dict[str, Any]:
        with self._lock:
            registry = self._load()
            source_id = self.canonical_id(source_id, registry)
            target_id = self.canonical_id(target_id, registry)
            if source_id == target_id:
                raise AthleteIdentityError("Beide Kennungen gehören bereits zum selben Athleten.")
            by_id = {item["id"]: item for item in registry["athletes"]}
            if source_id not in by_id or target_id not in by_id:
                raise AthleteIdentityError("Mindestens eine Athletenkennung wurde nicht gefunden.")
            source, target = by_id[source_id], by_id[target_id]
            for field in ("externalIds", "identityKeys", "aliases", "sourceDocumentIds"):
                for value in source.get(field, []):
                    if value not in target.setdefault(field, []):
                        target[field].append(value)
            registry["redirects"][source_id] = target_id
            atomic_json(self.path, registry)
        return self.athlete(target_id)

    def redirects(self) -> dict[str, str]:
        return dict(self._load().get("redirects", {}))
