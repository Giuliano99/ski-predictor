"""Generate a reviewable tip-round draft from normalized start-list JSON files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo


TIME_ZONE = "Europe/Berlin"
QUESTION_LIMITS = (6, 10)
QUESTION_TYPE_ALIASES = {
    "ANZAHL": "NUMBER",
    "PERSON": "ATHLETE",
    "REIHENFOLGE": "INTERNAL_RANKING",
    "PLATZIERUNG": "PLACEMENT",
    "DUELL": "HEAD_TO_HEAD",
    "DIREKTVERGLEICH": "HEAD_TO_HEAD",
    "PODIUM": "PODIUM",
    "NUMBER": "NUMBER",
    "ATHLETE": "ATHLETE",
    "INTERNAL_RANKING": "INTERNAL_RANKING",
    "PLACEMENT": "PLACEMENT",
    "HEAD_TO_HEAD": "HEAD_TO_HEAD",
}
EVALUATION_ALIASES = {
    "PODIUMSPLAETZE": "PODIUM_COUNT",
    "TOP_10": "TOP_N_COUNT",
    "GEWERTETE": "CLASSIFIED_COUNT",
    "BESTES_ERGEBNIS": "BEST_RESULT",
    "GERINGSTER_RUECKSTAND": "LOWEST_PERCENTAGE_GAP",
    "INTERNE_REIHENFOLGE": "INTERNAL_ORDER",
    "PLATZIERUNG": "EXACT_PLACEMENT",
    "DIREKTVERGLEICH": "DIRECT_COMPARISON",
    "INTERNES_PODIUM": "PODIUM_ORDER",
}
DEFAULT_EVALUATION_BY_TYPE = {
    "INTERNAL_RANKING": "INTERNAL_ORDER",
    "PLACEMENT": "EXACT_PLACEMENT",
    "HEAD_TO_HEAD": "DIRECT_COMPARISON",
    "PODIUM": "PODIUM_ORDER",
}


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-") or "item"


def load_start_list(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("documentType") != "START_LIST":
        raise ValueError(f"{path.name} is not a normalized START_LIST document")
    if not document.get("groups"):
        raise ValueError(f"{path.name} contains no start groups")
    return document


def athlete_key(starter: dict[str, Any]) -> str:
    external_id = starter.get("externalAthleteId")
    if external_id:
        return f"external:{external_id}"
    identity = "|".join((starter["fullName"].casefold(), str(starter["birthYear"]), starter["club"].casefold()))
    return f"fallback:{identity}"


def natural_athlete_key(starter: dict[str, Any]) -> str:
    return "|".join((starter["fullName"].casefold(), str(starter["birthYear"]), starter["club"].casefold()))


def athlete_id(starter: dict[str, Any]) -> str:
    external_id = starter.get("externalAthleteId")
    if external_id:
        return f"athlete-ext-{slugify(str(external_id))}"
    digest = hashlib.sha256(athlete_key(starter).encode("utf-8")).hexdigest()[:12]
    return f"athlete-local-{digest}"


def deadline_for_event(event_date: date, zone: ZoneInfo) -> datetime:
    days_since_saturday = (event_date.weekday() - 5) % 7
    saturday = event_date - timedelta(days=days_since_saturday)
    return datetime.combine(saturday, time.min, zone)


def opening_for_deadline(deadline: datetime) -> datetime:
    return deadline - timedelta(days=5) + timedelta(hours=8)


def weekday_de(value: date) -> str:
    return ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")[value.weekday()]


def discipline_label(value: str) -> str:
    return {
        "SL": "Slalom",
        "GS": "Riesenslalom",
        "SG": "Super-G",
        "DH": "Abfahrt",
        "KIDS_CROSS": "Kids Cross",
        "OTHER": "Sonstiges",
    }.get(value, value)


def build_snapshot(documents: list[tuple[Path, dict[str, Any]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    athletes: dict[str, dict[str, Any]] = {}
    races: list[dict[str, Any]] = []
    group_snapshots: list[dict[str, Any]] = []
    external_ids_by_identity: dict[str, set[str]] = defaultdict(set)
    for _, document in documents:
        for group in document["groups"]:
            for starter in group["starters"]:
                if starter.get("targetClub") and starter.get("externalAthleteId"):
                    external_ids_by_identity[natural_athlete_key(starter)].add(str(starter["externalAthleteId"]))

    def snapshot_athlete_id(starter: dict[str, Any]) -> str:
        external_ids = external_ids_by_identity.get(natural_athlete_key(starter), set())
        if external_ids:
            return f"athlete-ext-{slugify(sorted(external_ids)[0])}"
        return athlete_id(starter)

    for source_path, document in documents:
        event = document["event"]
        race_id = f"race-{slugify(event.get('competitionNumber') or source_path.stem)}"
        event_date = date.fromisoformat(event["date"])
        race = {
            "id": race_id,
            "name": event["name"],
            "discipline": discipline_label(event.get("discipline", "OTHER")),
            "day": weekday_de(event_date),
            "date": event["date"],
            "sourceFile": document.get("source", {}).get("fileName", source_path.name),
        }
        if event.get("location"):
            race["location"] = event["location"]
        if event.get("competitionNumber"):
            race["competitionNumber"] = event["competitionNumber"]
        races.append(race)

        for group in document["groups"]:
            group_athlete_ids: list[str] = []
            for starter in group["starters"]:
                if not starter.get("targetClub"):
                    continue
                identifier = snapshot_athlete_id(starter)
                group_athlete_ids.append(identifier)
                snapshot = athletes.setdefault(identifier, {
                    "id": identifier,
                    "displayName": starter["displayName"],
                    "ageClass": group["ageClass"],
                    "birthYear": starter["birthYear"],
                    "starts": [],
                })
                snapshot["starts"].append({
                    "raceId": race_id,
                    "groupId": f"{race_id}-{group['id']}",
                    "ageClass": group["ageClass"],
                    "startNumber": starter["startNumber"],
                })

            if group_athlete_ids:
                group_snapshots.append({
                    "id": f"{race_id}-{group['id']}",
                    "raceId": race_id,
                    "label": group["label"],
                    "ageClass": group["ageClass"],
                    "competitionCategory": group["competitionCategory"],
                    "birthYears": group.get("birthYears", []),
                    "athleteIds": group_athlete_ids,
                })

    athlete_list = sorted(athletes.values(), key=lambda item: (item["ageClass"], item["displayName"], item["id"]))
    return athlete_list, races, group_snapshots


def choose_group(groups: list[dict[str, Any]], minimum: int, excluded_ids: set[str] | None = None) -> dict[str, Any] | None:
    excluded_ids = excluded_ids or set()
    eligible = [group for group in groups if len(group["athleteIds"]) >= minimum and group["id"] not in excluded_ids]
    return max(eligible, key=lambda group: (len(group["athleteIds"]), group["id"]), default=None)


def resolve_athlete_names(value: str, athletes: list[dict[str, Any]], question_number: int) -> list[str]:
    if value.strip().upper() in {"ALL", "ALLE"}:
        return [athlete["id"] for athlete in athletes]

    by_display_name: dict[str, list[str]] = defaultdict(list)
    for athlete in athletes:
        by_display_name[athlete["displayName"].casefold()].append(athlete["id"])

    resolved: list[str] = []
    for display_name in (part.strip() for part in value.split("|")):
        matches = by_display_name.get(display_name.casefold(), [])
        if not matches:
            raise ValueError(f"Question {question_number}: athlete '{display_name}' was not found in the start list")
        if len(matches) > 1:
            raise ValueError(f"Question {question_number}: display name '{display_name}' is ambiguous")
        resolved.append(matches[0])
    return resolved


def resolve_race_scope(
    value: str,
    races: list[dict[str, Any]],
    question_number: int,
    race_date: str = "",
    question_context: str = "",
) -> tuple[list[str], str]:
    if not value:
        raise ValueError(f"Question {question_number}: Rennen is required")
    if value.strip().upper() in {"ALL", "ALLE"}:
        race_ids = [race["id"] for race in races]
        label = races[0]["name"] if len(races) == 1 else f"Alle {len(races)} Rennen des Wochenendes"
        return race_ids, label

    by_reference: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for race in races:
        by_reference[slugify(race["id"])].append(race)
        by_reference[slugify(race["name"])].append(race)

    selected: list[dict[str, Any]] = []
    for reference in (part.strip() for part in value.split("|")):
        matches = by_reference.get(slugify(reference), [])
        if race_date:
            matches = [race for race in matches if race.get("date") == race_date]
        if not matches:
            suffix = f" am {race_date}" if race_date else ""
            known = ", ".join(dict.fromkeys(race["name"] for race in races))
            raise ValueError(f"Frage {question_number}: Rennen '{reference}'{suffix} wurde nicht gefunden. Erkannte Rennen: {known}")
        unique_matches = {race["id"]: race for race in matches}
        if len(unique_matches) > 1 and question_context:
            context_words = set(slugify(question_context).split("-"))
            discipline_matches = {
                race_id: race for race_id, race in unique_matches.items()
                if slugify(str(race.get("discipline", ""))) in context_words
            }
            if len(discipline_matches) == 1:
                unique_matches = discipline_matches
        if len(unique_matches) > 1:
            raise ValueError(f"Frage {question_number}: Rennen '{reference}' ist nicht eindeutig. Bitte zusätzlich Renndatum angeben.")
        selected.append(next(iter(unique_matches.values())))
    return [race["id"] for race in selected], " · ".join(race["name"] for race in selected)


def parse_question_markdown(path: Path, athletes: list[dict[str, Any]], races: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
    blocks: list[tuple[str, dict[str, str]]] = []
    prompt: str | None = None
    fields: dict[str, str] = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            if prompt:
                blocks.append((prompt, fields))
            prompt = line[3:].strip()
            fields = {}
        elif prompt and ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip().casefold()] = value.strip()
    if prompt:
        blocks.append((prompt, fields))

    if not QUESTION_LIMITS[0] <= len(blocks) <= QUESTION_LIMITS[1]:
        raise ValueError(f"{path.name} must contain between {QUESTION_LIMITS[0]} and {QUESTION_LIMITS[1]} questions; found {len(blocks)}")

    questions: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for index, (question_prompt, fields) in enumerate(blocks, start=1):
        raw_type = fields.get("typ", fields.get("type", "")).upper()
        question_type = QUESTION_TYPE_ALIASES.get(raw_type)
        if not question_type:
            raise ValueError(f"Question {index}: unknown or missing type '{raw_type}'")

        identifier = fields.get("id") or f"manual-{index:02d}-{slugify(question_prompt)}"
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", identifier):
            raise ValueError(f"Question {index}: ID must only contain lowercase letters, numbers and hyphens")
        if identifier in used_ids:
            raise ValueError(f"Question {index}: duplicate question '{question_prompt}'")
        used_ids.add(identifier)
        question: dict[str, Any] = {
            "id": identifier,
            "type": question_type,
            "prompt": question_prompt,
            "hint": fields.get("hinweis", fields.get("hint", "Es zählt das offizielle Gesamtergebnis")),
        }
        raw_evaluation = fields.get("auswertung", "").upper()
        evaluation_metric = EVALUATION_ALIASES.get(raw_evaluation) or DEFAULT_EVALUATION_BY_TYPE.get(question_type)
        if not evaluation_metric:
            raise ValueError(f"Question {index}: Auswertung is required for type {raw_type}")
        question["evaluationMetric"] = evaluation_metric
        if evaluation_metric == "TOP_N_COUNT":
            question["threshold"] = int(fields.get("grenze", "10"))
        race_ids, race_label = resolve_race_scope(
            fields.get("rennen", fields.get("races", "")),
            races,
            index,
            fields.get("renndatum", fields.get("race date", "")),
            f"{question_prompt} {question['hint']}",
        )
        question["raceIds"] = race_ids
        question["raceLabel"] = race_label

        raw_age_classes = fields.get("altersklassen", fields.get("altersklasse", ""))
        age_class_athlete_ids: list[str] | None = None
        if raw_age_classes:
            age_classes = [value.strip().upper() for value in re.split(r"[|,]", raw_age_classes) if value.strip()]
            age_class_athlete_ids = [athlete["id"] for athlete in athletes if str(athlete.get("ageClass", "")).upper() in age_classes]
            if not age_class_athlete_ids:
                raise ValueError(f"Question {index}: no athletes found for Altersklasse {raw_age_classes}")
            question["ageClasses"] = age_classes
            question["raceLabel"] = f"{race_label} · {' / '.join(age_classes)}"

        if question_type == "NUMBER":
            question["minimum"] = int(fields.get("minimum", "0"))
            question["maximum"] = int(fields.get("maximum", "60"))
            if question["maximum"] <= question["minimum"]:
                raise ValueError(f"Question {index}: maximum must be greater than minimum")
            if age_class_athlete_ids is not None:
                question["athleteIds"] = age_class_athlete_ids
        elif question_type == "PLACEMENT":
            person = fields.get("person", "")
            athlete_ids = resolve_athlete_names(person, athletes, index)
            if len(athlete_ids) != 1:
                raise ValueError(f"Question {index}: PLATZIERUNG requires exactly one Person")
            if age_class_athlete_ids is not None and athlete_ids[0] not in age_class_athlete_ids:
                raise ValueError(f"Question {index}: Person does not belong to Altersklasse {raw_age_classes}")
            question.update({"athleteId": athlete_ids[0], "minimum": int(fields.get("minimum", "1")), "maximum": int(fields.get("maximum", "60"))})
        else:
            raw_people = fields.get("personen", "ALLE")
            athlete_ids = age_class_athlete_ids if raw_people.upper() == "ALLE" and age_class_athlete_ids is not None else resolve_athlete_names(raw_people, athletes, index)
            if age_class_athlete_ids is not None and any(athlete_id not in age_class_athlete_ids for athlete_id in athlete_ids):
                raise ValueError(f"Question {index}: not all Personen belong to Altersklasse {raw_age_classes}")
            if question_type == "HEAD_TO_HEAD" and len(athlete_ids) != 2:
                raise ValueError(f"Question {index}: DUELL requires exactly two Personen separated by |")
            if question_type in {"INTERNAL_RANKING", "PODIUM"}:
                positions = int(fields.get("positionen", "3"))
                if positions < 2 or positions > len(athlete_ids):
                    raise ValueError(f"Question {index}: Positionen must be between 2 and the number of Personen")
                question["positions"] = positions
            question["athleteIds"] = athlete_ids
        questions.append(question)

    return questions


def generate_questions(athletes: list[dict[str, Any]], groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    athlete_ids = [athlete["id"] for athlete in athletes]
    if len(athlete_ids) < 2:
        raise ValueError("At least two target-club athletes are required for a tip round")

    total_starts = sum(len(group["athleteIds"]) for group in groups)
    maximum_podiums = sum(min(3, len(group["athleteIds"])) for group in groups)
    questions: list[dict[str, Any]] = [
        {
            "id": "podium-count",
            "type": "NUMBER",
            "prompt": "Wie viele Podiumsplätze erreicht das Skiteam am gesamten Rennwochenende?",
            "hint": "Alle Wertungsgruppen der ausgewählten Rennen zusammen",
            "minimum": 0,
            "maximum": max(1, maximum_podiums),
            "evaluationMetric": "PODIUM_COUNT",
        },
        {
            "id": "top-ten-count",
            "type": "NUMBER",
            "prompt": "Wie viele Top-10-Ergebnisse erzielt Oberhaching?",
            "hint": "Maßgeblich ist jeweils das offizielle Gesamtergebnis",
            "minimum": 0,
            "maximum": max(1, total_starts),
            "evaluationMetric": "TOP_N_COUNT",
            "threshold": 10,
        },
        {
            "id": "best-result",
            "type": "ATHLETE",
            "prompt": "Wer erzielt das beste Ergebnis des Rennwochenendes?",
            "hint": "Verglichen wird zunächst die offizielle Platzierung",
            "athleteIds": athlete_ids,
            "evaluationMetric": "BEST_RESULT",
        },
        {
            "id": "lowest-gap",
            "type": "ATHLETE",
            "prompt": "Wer hat den geringsten prozentualen Rückstand?",
            "hint": "Der prozentuale Rückstand macht unterschiedliche Rennen vergleichbar",
            "athleteIds": athlete_ids,
            "evaluationMetric": "LOWEST_PERCENTAGE_GAP",
        },
    ]

    ranking_group = choose_group(groups, minimum=3)
    if ranking_group:
        questions.append({
            "id": f"ranking-{slugify(ranking_group['id'])}",
            "type": "INTERNAL_RANKING",
            "prompt": f"Wie lautet die interne Reihenfolge in {ranking_group['label']}?",
            "hint": "Ordne die Oberhachinger Starter nach dem offiziellen Gesamtergebnis",
            "positions": min(5, len(ranking_group["athleteIds"])),
            "athleteIds": ranking_group["athleteIds"],
            "groupId": ranking_group["id"],
            "evaluationMetric": "INTERNAL_ORDER",
        })

    head_to_head_group = choose_group(groups, minimum=2, excluded_ids={ranking_group["id"]} if ranking_group else set()) or choose_group(groups, minimum=2)
    if head_to_head_group:
        duel_ids = sorted(head_to_head_group["athleteIds"])[:2]
        questions.append({
            "id": f"head-to-head-{slugify(head_to_head_group['id'])}",
            "type": "HEAD_TO_HEAD",
            "prompt": f"Wer gewinnt den direkten Vergleich in {head_to_head_group['label']}?",
            "hint": "Es zählt das offizielle Gesamtergebnis",
            "athleteIds": duel_ids,
            "groupId": head_to_head_group["id"],
            "evaluationMetric": "DIRECT_COMPARISON",
        })

    placement_athlete = athletes[len(athletes) // 2]
    questions.append({
        "id": f"placement-{placement_athlete['id']}",
        "type": "PLACEMENT",
        "prompt": f"Welche Platzierung erreicht {placement_athlete['displayName']}?",
        "hint": "Tippe die offizielle Platzierung in der Wertungsgruppe",
        "athleteId": placement_athlete["id"],
        "minimum": 1,
        "maximum": 60,
        "evaluationMetric": "EXACT_PLACEMENT",
    })

    if len(athlete_ids) >= 3:
        questions.append({
            "id": "internal-podium",
            "type": "PODIUM",
            "prompt": "Wie sieht das interne Oberhachinger Podium aus?",
            "hint": "Über alle Rennen nach bestem prozentualen Rückstand",
            "positions": 3,
            "athleteIds": athlete_ids,
            "evaluationMetric": "PODIUM_ORDER",
        })

    if len(questions) < QUESTION_LIMITS[0]:
        raise ValueError(f"Only {len(questions)} questions could be generated; at least {QUESTION_LIMITS[0]} are required")
    return questions[: QUESTION_LIMITS[1]]


def generate_question_suggestions_markdown(
    athletes: list[dict[str, Any]],
    races: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    title: str,
) -> str:
    """Create an editable, immediately valid question sheet from start-list data."""
    athlete_by_id = {athlete["id"]: athlete for athlete in athletes}
    name_counts: dict[str, int] = defaultdict(int)
    for athlete in athletes:
        name_counts[athlete["displayName"].casefold()] += 1

    def race_groups(race_id: str) -> list[dict[str, Any]]:
        return [group for group in groups if group["raceId"] == race_id]

    def preferred_age_class(race: dict[str, Any]) -> tuple[str, int]:
        counts: dict[str, set[str]] = defaultdict(set)
        for group in race_groups(race["id"]):
            counts[group["ageClass"]].update(group["athleteIds"])
        if not counts:
            raise ValueError(f"Keine Oberhachinger Altersklasse für {race['name']} gefunden")
        age_class = max(counts, key=lambda value: (len(counts[value]), value))
        return age_class, len(counts[age_class])

    def race_scope(race: dict[str, Any]) -> str:
        return f"am {race['day']} im {race['discipline']} beim Rennen „{race['name']}“"

    def block(prompt: str, fields: list[tuple[str, Any]]) -> str:
        return "\n".join([f"## {prompt}", *(f"{key}: {value}" for key, value in fields)])

    maximum_podiums = sum(min(3, len(group["athleteIds"])) for group in groups)
    suggestions = [
        block(
            f"Wie viele Podiumsplätze erreicht Oberhaching in allen {len(races)} Rennen des Wochenendes?",
            [
                ("ID", "weekend-podium-count"), ("Typ", "ANZAHL"),
                ("Auswertung", "PODIUMSPLAETZE"), ("Rennen", "ALLE"),
                ("Hinweis", "Alle Rennen und offiziellen Wertungsgruppen des Wochenendes zählen zusammen."),
                ("Minimum", 0), ("Maximum", max(1, maximum_podiums)),
            ],
        ),
        block(
            "Wer erzielt das beste Ergebnis in allen Rennen des Wochenendes?",
            [
                ("ID", "weekend-best-result"), ("Typ", "PERSON"),
                ("Auswertung", "BESTES_ERGEBNIS"), ("Rennen", "ALLE"),
                ("Hinweis", "Pro Person zählt nur das beste offizielle Ergebnis des Wochenendes."),
                ("Personen", "ALLE"),
            ],
        ),
    ]

    selected_races = races[:4]
    for race in selected_races:
        age_class, starter_count = preferred_age_class(race)
        suggestions.append(block(
            f"Wie viele Top-10-Ergebnisse erzielt Oberhaching {race_scope(race)} in der {age_class}?",
            [
                ("ID", f"{race['id'].removeprefix('race-')}-{age_class.lower()}-top-ten"),
                ("Typ", "ANZAHL"), ("Auswertung", "TOP_10"), ("Grenze", 10),
                ("Rennen", race["id"]), ("Renndatum", race["date"]),
                ("Altersklasse", age_class),
                ("Hinweis", f"Es zählt ausschließlich {race_scope(race)} in allen offiziellen {age_class}-Wertungsgruppen."),
                ("Minimum", 0), ("Maximum", max(1, starter_count)),
            ],
        ))

    for race in selected_races[:1]:
        age_class, _ = preferred_age_class(race)
        suggestions.append(block(
            f"Wer hat {race_scope(race)} in der {age_class} den geringsten prozentualen Rückstand?",
            [
                ("ID", f"{race['id'].removeprefix('race-')}-{age_class.lower()}-lowest-gap"),
                ("Typ", "PERSON"), ("Auswertung", "GERINGSTER_RUECKSTAND"),
                ("Rennen", race["id"]), ("Renndatum", race["date"]),
                ("Altersklasse", age_class),
                ("Hinweis", "Verglichen wird der prozentuale Rückstand auf den Sieger oder die Siegerin der jeweiligen offiziellen Wertungsgruppe."),
                ("Personen", "ALLE"),
            ],
        ))

    first_race = races[0]
    first_groups = race_groups(first_race["id"])
    unique_name_ids = {
        athlete_id for athlete_id, athlete in athlete_by_id.items()
        if name_counts[athlete["displayName"].casefold()] == 1
    }
    placement_group = next((group for group in first_groups if any(item in unique_name_ids for item in group["athleteIds"])), None)
    if placement_group:
        athlete_id_value = next(item for item in placement_group["athleteIds"] if item in unique_name_ids)
        display_name = athlete_by_id[athlete_id_value]["displayName"]
        suggestions.append(block(
            f"Welche Platzierung erreicht {display_name} {race_scope(first_race)} in {placement_group['label']}?",
            [
                ("ID", f"{first_race['id'].removeprefix('race-')}-{slugify(display_name)}-placement"),
                ("Typ", "PLATZIERUNG"), ("Auswertung", "PLATZIERUNG"),
                ("Rennen", first_race["id"]), ("Renndatum", first_race["date"]),
                ("Altersklasse", placement_group["ageClass"]),
                ("Hinweis", "Es zählt die offizielle Platzierung in der genannten Wertungsgruppe."),
                ("Person", display_name), ("Minimum", 1), ("Maximum", 60),
            ],
        ))

    duel_group = next((group for group in groups if len([item for item in group["athleteIds"] if item in unique_name_ids]) >= 2), None)
    if duel_group:
        race = next(item for item in races if item["id"] == duel_group["raceId"])
        duel_ids = [item for item in duel_group["athleteIds"] if item in unique_name_ids][:2]
        names = [athlete_by_id[item]["displayName"] for item in duel_ids]
        suggestions.append(block(
            f"Wer ist {race_scope(race)} in {duel_group['label']} besser: {names[0]} oder {names[1]}?",
            [
                ("ID", f"{race['id'].removeprefix('race-')}-{slugify('-'.join(names))}-duel"),
                ("Typ", "DUELL"), ("Auswertung", "DIREKTVERGLEICH"),
                ("Rennen", race["id"]), ("Renndatum", race["date"]),
                ("Hinweis", "Es zählt das offizielle Gesamtergebnis derselben Wertungsgruppe."),
                ("Personen", " | ".join(names)),
            ],
        ))

    ranking_group = next((group for group in groups if len([item for item in group["athleteIds"] if item in unique_name_ids]) >= 3), None)
    if ranking_group:
        race = next(item for item in races if item["id"] == ranking_group["raceId"])
        ranking_ids = [item for item in ranking_group["athleteIds"] if item in unique_name_ids]
        names = [athlete_by_id[item]["displayName"] for item in ranking_ids]
        suggestions.append(block(
            f"Wie lautet {race_scope(race)} die interne Oberhachinger Reihenfolge in {ranking_group['label']}?",
            [
                ("ID", f"{race['id'].removeprefix('race-')}-{slugify(ranking_group['label'])}-ranking"),
                ("Typ", "REIHENFOLGE"), ("Auswertung", "INTERNE_REIHENFOLGE"),
                ("Rennen", race["id"]), ("Renndatum", race["date"]),
                ("Hinweis", "Alle genannten Personen fahren in derselben offiziellen Wertungsgruppe."),
                ("Personen", " | ".join(names)), ("Positionen", min(3, len(names))),
            ],
        ))

    age_class, starter_count = preferred_age_class(first_race)
    suggestions.append(block(
        f"Wie viele Oberhachinger Starter kommen {race_scope(first_race)} in der {age_class} in die Wertung?",
        [
            ("ID", f"{first_race['id'].removeprefix('race-')}-{age_class.lower()}-classified"),
            ("Typ", "ANZAHL"), ("Auswertung", "GEWERTETE"),
            ("Rennen", first_race["id"]), ("Renndatum", first_race["date"]),
            ("Altersklasse", age_class),
            ("Hinweis", "DNS, DNF und DSQ zählen nicht als offiziell gewertet."),
            ("Minimum", 0), ("Maximum", max(1, starter_count)),
        ],
    ))

    suggestions = suggestions[: QUESTION_LIMITS[1]]
    if len(suggestions) < QUESTION_LIMITS[0]:
        raise ValueError("Aus den Startlisten konnten nicht genügend konkrete Fragen erzeugt werden")
    return f"# Fragen für {title}\n\n> Automatisch aus den Startlisten vorgeschlagen. Vor dem Öffnen prüfen und bei Bedarf anpassen.\n\n" + "\n\n".join(suggestions) + "\n"


def write_question_suggestions(
    source_paths: list[Path],
    output_path: Path,
    title: str,
    test_weekend_date: date | None = None,
) -> None:
    documents = [(path, load_start_list(path)) for path in source_paths]
    athletes, races, groups = build_snapshot(documents)
    if test_weekend_date:
        remap_race_dates(races, test_weekend_date)
    content = generate_question_suggestions_markdown(athletes, races, groups, title)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def content_version(document: dict[str, Any]) -> str:
    protected_content = {
        "id": document["id"],
        "opensAt": document["opensAt"],
        "closesAt": document["closesAt"],
        "athletes": document["athletes"],
        "races": document["races"],
        "groups": document["groups"],
        "questions": document["questions"],
    }
    canonical = json.dumps(protected_content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"sha256-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def remap_race_dates(races: list[dict[str, Any]], test_weekend_date: date) -> list[date]:
    original_start = min(date.fromisoformat(race["date"]) for race in races)
    remapped_dates: set[date] = set()
    for race in races:
        original_date = date.fromisoformat(race["date"])
        remapped_date = test_weekend_date + (original_date - original_start)
        race["originalDate"] = race["date"]
        race["date"] = remapped_date.isoformat()
        race["day"] = weekday_de(remapped_date)
        remapped_dates.add(remapped_date)
    return sorted(remapped_dates)


def generate_tip_round(source_paths: list[Path], title: str | None = None, questions_path: Path | None = None, test_weekend_date: date | None = None, season_id: str | None = None, status: str = "DRAFT") -> dict[str, Any]:
    documents = [(path, load_start_list(path)) for path in source_paths]
    event_dates = sorted(date.fromisoformat(document["event"]["date"]) for _, document in documents)
    if not test_weekend_date and (event_dates[-1] - event_dates[0]).days > 3:
        raise ValueError("Start lists are more than three days apart and cannot form one tip round")

    athletes, races, groups = build_snapshot(documents)
    if not athletes:
        raise ValueError("No target-club athletes found in the provided start lists")

    if test_weekend_date:
        event_dates = remap_race_dates(races, test_weekend_date)

    zone = ZoneInfo(TIME_ZONE)
    closes_at = deadline_for_event(event_dates[0], zone)
    opens_at = opening_for_deadline(closes_at)
    generated_title = title or (races[0]["name"] if len(races) == 1 else f"Rennwochenende {event_dates[0].strftime('%d.%m.%Y')}")

    if questions_path:
        questions = parse_question_markdown(questions_path, athletes, races)
    else:
        questions = generate_questions(athletes, groups)
        races_by_id = {race["id"]: race for race in races}
        groups_by_id = {group["id"]: group for group in groups}
        for question in questions:
            group = groups_by_id.get(question.get("groupId"))
            scoped_races = [races_by_id[group["raceId"]]] if group else races
            question["raceIds"] = [race["id"] for race in scoped_races]
            question["raceLabel"] = scoped_races[0]["name"] if len(scoped_races) == 1 else f"Alle {len(scoped_races)} Rennen des Wochenendes"
    document = {
        "schemaVersion": 1,
        "id": f"tip-round-{event_dates[0].isoformat()}",
        "status": status,
        "title": generated_title,
        "subtitle": f"{len(races)} Rennen · {len(athletes)} Oberhachinger Starter",
        "opensAt": opens_at.isoformat(),
        "closesAt": closes_at.isoformat(),
        "timeZone": TIME_ZONE,
        "generatedFrom": [path.name for path in source_paths],
        "athletes": athletes,
        "races": races,
        "groups": groups,
        "questions": questions,
        "review": {
            "required": True,
            "checks": [
                "Veranstaltung und Rennen prüfen",
                "Oberhachinger Starter prüfen",
                "Anzeigenamen prüfen",
                "Fragen und Zahlenbereiche prüfen",
                "Abgabeschluss prüfen",
            ],
        },
    }
    if season_id:
        document["seasonId"] = season_id
    if questions_path:
        document["questionsSource"] = questions_path.name
    if test_weekend_date:
        document["testFixture"] = True
    document["contentVersion"] = content_version(document)
    return document


def default_output_path(source_paths: list[Path]) -> Path:
    workspace = Path(__file__).resolve().parents[3]
    joined_stems = "-".join(path.stem for path in source_paths)
    return workspace / "data" / "result-lists" / "processed" / f"tip-round-{joined_stems}.json"


def summary(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": document["id"],
        "status": document["status"],
        "races": len(document["races"]),
        "groups": len(document["groups"]),
        "athletes": len(document["athletes"]),
        "questions": len(document["questions"]),
        "closesAt": document["closesAt"],
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("start_lists", nargs="+", type=Path, help="Normalized start-list JSON files from the PDF extractor")
    parser.add_argument("--output", type=Path, help="Output path for the tip-round draft")
    parser.add_argument("--title", help="Optional title override")
    parser.add_argument("--questions", type=Path, help="Markdown file containing six to ten manually selected questions")
    parser.add_argument("--suggest-questions-output", type=Path, help="Replace a placeholder question sheet with concrete suggestions")
    parser.add_argument("--test-weekend-date", type=date.fromisoformat, help="Fixture only: treat all sources as races on this ISO date")
    parser.add_argument("--season-id", help="Season identifier copied into the generated tip round")
    parser.add_argument("--status", choices=["DRAFT", "OPEN", "CLOSED", "EVALUATED", "ARCHIVED", "CANCELLED"], default="DRAFT")
    arguments = parser.parse_args(argv)

    source_paths = [path.resolve() for path in arguments.start_lists]
    output_path = (arguments.output or default_output_path(source_paths)).resolve()
    questions_path = arguments.questions.resolve() if arguments.questions else None
    if arguments.suggest_questions_output:
        suggestions_path = arguments.suggest_questions_output.resolve()
        write_question_suggestions(
            source_paths,
            suggestions_path,
            arguments.title or f"Rennwochenende {arguments.test_weekend_date or ''}".strip(),
            arguments.test_weekend_date,
        )
        questions_path = suggestions_path
    document = generate_tip_round(source_paths, arguments.title, questions_path, arguments.test_weekend_date, arguments.season_id, arguments.status)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**summary(document), "output": str(output_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
