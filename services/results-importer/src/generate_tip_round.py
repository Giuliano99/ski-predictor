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
            "sourceFile": source_path.name,
        }
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


def resolve_race_scope(value: str, races: list[dict[str, Any]], question_number: int) -> tuple[list[str], str]:
    if not value:
        raise ValueError(f"Question {question_number}: Rennen is required")
    if value.strip().upper() in {"ALL", "ALLE"}:
        race_ids = [race["id"] for race in races]
        label = races[0]["name"] if len(races) == 1 else f"Alle {len(races)} Rennen des Wochenendes"
        return race_ids, label

    by_reference: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for race in races:
        by_reference[race["id"].casefold()].append(race)
        by_reference[race["name"].casefold()].append(race)

    selected: list[dict[str, Any]] = []
    for reference in (part.strip() for part in value.split("|")):
        matches = by_reference.get(reference.casefold(), [])
        if not matches:
            raise ValueError(f"Question {question_number}: race '{reference}' was not found in the weekend")
        unique_matches = {race["id"]: race for race in matches}
        if len(unique_matches) > 1:
            raise ValueError(f"Question {question_number}: race '{reference}' is ambiguous")
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

        identifier = f"manual-{index:02d}-{slugify(question_prompt)}"
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
        race_ids, race_label = resolve_race_scope(fields.get("rennen", fields.get("races", "")), races, index)
        question["raceIds"] = race_ids
        question["raceLabel"] = race_label

        if question_type == "NUMBER":
            question["minimum"] = int(fields.get("minimum", "0"))
            question["maximum"] = int(fields.get("maximum", "60"))
            if question["maximum"] <= question["minimum"]:
                raise ValueError(f"Question {index}: maximum must be greater than minimum")
        elif question_type == "PLACEMENT":
            person = fields.get("person", "")
            athlete_ids = resolve_athlete_names(person, athletes, index)
            if len(athlete_ids) != 1:
                raise ValueError(f"Question {index}: PLATZIERUNG requires exactly one Person")
            question.update({"athleteId": athlete_ids[0], "minimum": int(fields.get("minimum", "1")), "maximum": int(fields.get("maximum", "60"))})
        else:
            athlete_ids = resolve_athlete_names(fields.get("personen", "ALLE"), athletes, index)
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


def generate_tip_round(source_paths: list[Path], title: str | None = None, questions_path: Path | None = None, test_weekend_date: date | None = None) -> dict[str, Any]:
    documents = [(path, load_start_list(path)) for path in source_paths]
    event_dates = sorted(date.fromisoformat(document["event"]["date"]) for _, document in documents)
    if not test_weekend_date and (event_dates[-1] - event_dates[0]).days > 3:
        raise ValueError("Start lists are more than three days apart and cannot form one tip round")

    athletes, races, groups = build_snapshot(documents)
    if not athletes:
        raise ValueError("No target-club athletes found in the provided start lists")

    if test_weekend_date:
        for race in races:
            race["originalDate"] = race["date"]
            race["date"] = test_weekend_date.isoformat()
            race["day"] = weekday_de(test_weekend_date)
        event_dates = [test_weekend_date]

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
        "status": "DRAFT",
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
    if questions_path:
        document["questionsSource"] = questions_path.name
    if test_weekend_date:
        document["testFixture"] = True
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
    parser.add_argument("--test-weekend-date", type=date.fromisoformat, help="Fixture only: treat all sources as races on this ISO date")
    arguments = parser.parse_args(argv)

    source_paths = [path.resolve() for path in arguments.start_lists]
    output_path = (arguments.output or default_output_path(source_paths)).resolve()
    questions_path = arguments.questions.resolve() if arguments.questions else None
    document = generate_tip_round(source_paths, arguments.title, questions_path, arguments.test_weekend_date)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**summary(document), "output": str(output_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
