"""Extract Race Horology result-list PDFs into normalized local JSON."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from extract_start_list import (
    FORMAT_DSVALPIN,
    FORMAT_RACE_CODE,
    FORMAT_RACE_SIMPLE,
    FORMAT_VOLA,
    TARGET_CLUB,
    clean_space,
    detect_format,
    event_metadata,
    extract_pdf_text,
    is_target_club,
    name_from_comma,
    name_surname_first,
    name_without_comma,
    normalize_club,
    slugify,
)


TIME_PATTERN = r"(?:\d+:)?\d{1,2},\d{2}"
NUMBER_PATTERN = r"\d+,\d{2}"
RUN_TOKEN_PATTERN = rf"(?:{TIME_PATTERN}|NAS|NIZ|DIS|---)"
STATUS_CODES = {"NAS": "DNS", "NIZ": "DNF", "DIS": "DSQ"}


def seconds(value: str) -> float:
    normalized = value.replace(",", ".")
    if ":" not in normalized:
        return float(normalized)
    minutes, remainder = normalized.split(":", 1)
    return int(minutes) * 60 + float(remainder)


def decimal_number(value: str) -> float:
    return float(value.replace(".", "").replace(",", "."))


def points_calculations(text: str) -> list[dict[str, Any]]:
    """Keep the official U14/U16 penalty calculation in structured form.

    The full source text is persisted separately. These summary fields make the
    most commonly reused DSV values directly queryable without losing the
    original calculation tables.
    """
    calculations: list[dict[str, Any]] = []
    sections = re.finditer(
        r"Zuschlagsberechnung\s+(Damen|Herren|Mädchen|Maedchen|Buben)(?:/[^\n]*)?\s*(?P<body>.*?)(?=Zuschlagsberechnung\s+(?:Damen|Herren|Mädchen|Maedchen|Buben)|\Z)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    labels = {
        "fValue": r"F-Wert:\s*(\d+(?:[.,]\d+)?)",
        "calculatedPenalty": r"Berechneter Zuschlag:.*?=\s*(\d+(?:[.,]\d+)?)",
        "roundedPenalty": r"Gerundet:.*?(\d+(?:[.,]\d+)?)",
        "listPenalty": r"Punktezuschlag:.*?(\d+(?:[.,]\d+)?)",
        "minimumPenalty": r"Minimumzuschlag:.*?(\d+(?:[.,]\d+)?)",
        "appliedPenalty": r"Angewandter Zuschlag:.*?(\d+(?:[.,]\d+)?)",
    }
    for section in sections:
        body = section.group("body")
        calculation: dict[str, Any] = {
            "competitionCategory": "FEMALE" if section.group(1).casefold() in {"damen", "mädchen", "maedchen"} else "MALE"
        }
        for field, pattern in labels.items():
            match = re.search(pattern, body, re.IGNORECASE | re.DOTALL)
            if match:
                calculation[field] = decimal_number(match.group(1))
        calculations.append(calculation)
    return calculations


def normalize_federation_points(
    groups: list[dict[str, Any]], calculations: list[dict[str, Any]], discipline: str
) -> dict[str, int]:
    """Normalize printed raw or already-final values to final DSV race points."""
    fallback_f = {"SL": 730.0, "GS": 1010.0}.get(discipline)
    by_category = {item["competitionCategory"]: item for item in calculations}
    entries_by_category: dict[str, list[dict[str, Any]]] = {"FEMALE": [], "MALE": []}
    for group in groups:
        category = group.get("competitionCategory")
        if category in entries_by_category:
            entries_by_category[category].extend(
                entry for entry in group.get("entries", [])
                if entry.get("status") == "CLASSIFIED" and entry.get("officialTimeSeconds") is not None
            )

    statistics = {"alreadyIncluded": 0, "penaltyAdded": 0, "calculated": 0, "unverified": 0}
    for category, entries in entries_by_category.items():
        if not entries:
            continue
        calculation = by_category.get(category, {})
        f_value = calculation.get("fValue") or fallback_f
        penalty = calculation.get("appliedPenalty")
        if penalty is None:
            penalty = calculation.get("roundedPenalty")
        if penalty is None and calculation.get("calculatedPenalty") is not None:
            penalty = round(float(calculation["calculatedPenalty"]), 2)
        if f_value is None or penalty is None:
            for entry in entries:
                if entry.get("federationPoints") is not None:
                    entry["pointsSource"] = "PDF_UNVERIFIED"
                    statistics["unverified"] += 1
            continue
        best_time = min(float(entry["officialTimeSeconds"]) for entry in entries)
        for entry in entries:
            raw_points = round((float(entry["officialTimeSeconds"]) / best_time - 1.0) * float(f_value), 2)
            final_points = round(raw_points + float(penalty), 2)
            printed = entry.get("federationPoints")
            entry.update(rawRacePoints=raw_points, appliedPenaltyPoints=round(float(penalty), 2))
            if printed is not None:
                entry["printedFederationPoints"] = round(float(printed), 2)
            if printed is None:
                entry.update(federationPoints=final_points, pointsSource="CALCULATED_FROM_TIME_AND_PENALTY")
                statistics["calculated"] += 1
            elif abs(float(printed) - final_points) <= 0.06:
                entry.update(federationPoints=round(float(printed), 2), pointsSource="PDF_INCLUDES_PENALTY")
                statistics["alreadyIncluded"] += 1
            elif abs(float(printed) - raw_points) <= 0.06:
                entry.update(federationPoints=final_points, pointsSource="PDF_RAW_PLUS_PENALTY")
                statistics["penaltyAdded"] += 1
            else:
                entry.update(federationPoints=round(float(printed), 2), pointsSource="PDF_UNVERIFIED")
                statistics["unverified"] += 1
    return statistics


def competition_statistics(text: str) -> dict[str, int] | None:
    labels = {
        "registered": r"Gemeldete Teilnehmer:\s*(\d+)",
        "classified": r"Gewertete Teilnehmer:\s*(\d+)",
        "notClassified": r"Ausgeschiedene Teilnehmer:\s*(\d+)",
    }
    result = {
        field: int(match.group(1))
        for field, pattern in labels.items()
        if (match := re.search(pattern, text, re.IGNORECASE))
    }
    return result or None


def group_from_line(line: str, event_name: str) -> dict[str, Any] | None:
    normalized = line.casefold()
    birth_years: list[int] = []
    compact_gender = "mädchen" if re.fullmatch(r"m.dchen", normalized) else normalized
    if compact_gender in {"mädchen", "maedchen", "buben"}:
        age_match = re.search(r"\bU(\d+)\b", event_name, re.IGNORECASE)
        age_class = f"U{age_match.group(1)}" if age_match else "OPEN"
        category = "FEMALE" if compact_gender in {"mädchen", "maedchen"} else "MALE"
    else:
        age_match = re.search(r"\bU(\d+)\b", line, re.IGNORECASE)
        gender_match = re.search(r"weiblich|männlich|maennlich|mädchen|maedchen|buben", line, re.IGNORECASE)
        if not age_match or not gender_match:
            return None
        age_class = f"U{age_match.group(1)}"
        year_match = re.search(r"\b((?:19|20)\d{2})\b", line)
        if year_match:
            birth_years = [int(year_match.group(1))]
        category = "FEMALE" if gender_match.group(0).casefold() in {"weiblich", "mädchen", "maedchen"} else "MALE"
    group_id = f"{age_class}-{category}"
    if birth_years:
        group_id += f"-{birth_years[0]}"
    return {
        "id": slugify(group_id),
        "label": line,
        "ageClass": age_class,
        "competitionCategory": category,
        "birthYears": birth_years,
        "classificationMethod": "BEST_VALID_RUN" if age_class in {"U8", "U10"} else "SUM_OF_RUNS",
        "entries": [],
    }


def run_result(run_number: int, token: str) -> dict[str, Any] | None:
    if token == "---":
        return None
    if token in STATUS_CODES:
        return {"runNumber": run_number, "status": STATUS_CODES[token]}
    return {"runNumber": run_number, "status": "CLASSIFIED", "timeSeconds": seconds(token)}


def overall_status(run_tokens: list[str]) -> str:
    statuses = [STATUS_CODES[token] for token in run_tokens if token in STATUS_CODES]
    if "DSQ" in statuses:
        return "DSQ"
    if run_tokens and run_tokens[0] == "NAS":
        return "DNS"
    if "DNF" in statuses:
        return "DNF"
    if "DNS" in statuses:
        return "DNS"
    return "DNF"


def base_entry(start_number: str, last_name: str, first_name: str, birth_year: str, club_value: str, target_club: str) -> dict[str, Any]:
    person = name_from_comma(last_name, first_name)
    club = normalize_club(club_value)
    return {
        "startNumber": int(start_number),
        "fullName": person.full_name,
        "displayName": person.display_name,
        "birthYear": int(birth_year),
        "club": club,
        "targetClub": is_target_club(club, target_club),
    }


def parse_simple_classified(line: str, target_club: str) -> dict[str, Any] | None:
    pattern = rf"^(\d+)\s+(\d+)\s+(.+?),\s*(.+?)\s+((?:19|20)\d{{2}})\s+(.+?)\s+({RUN_TOKEN_PATTERN})\s+({RUN_TOKEN_PATTERN})\s+({TIME_PATTERN})(?:\s+({TIME_PATTERN}))?$"
    match = re.match(pattern, line)
    if not match:
        return None
    entry = base_entry(match.group(2), match.group(3), match.group(4), match.group(5), match.group(6), target_club)
    run_tokens = [match.group(7), match.group(8)]
    entry.update({
        "status": "CLASSIFIED",
        "rank": int(match.group(1)),
        "officialTimeSeconds": seconds(match.group(9)),
        "gapSeconds": seconds(match.group(10)) if match.group(10) else 0.0,
        "runResults": [result for index, token in enumerate(run_tokens, 1) if (result := run_result(index, token))],
    })
    return entry


def parse_code_classified(line: str, target_club: str) -> dict[str, Any] | None:
    pattern = rf"^(\d+)\s+(\d+)\s+(\d+)\s+(.+?),\s*(.+?)\s+((?:19|20)\d{{2}})\s+(\S+)\s+(.+?)\s+({TIME_PATTERN})\s+({TIME_PATTERN})\s+({TIME_PATTERN})(?:\s+({TIME_PATTERN}))?\s+({NUMBER_PATTERN})$"
    match = re.match(pattern, line)
    if not match:
        return None
    entry = base_entry(match.group(2), match.group(4), match.group(5), match.group(6), match.group(8), target_club)
    run_tokens = [match.group(9), match.group(10)]
    entry.update({
        "externalAthleteId": match.group(3),
        "federation": match.group(7),
        "status": "CLASSIFIED",
        "rank": int(match.group(1)),
        "officialTimeSeconds": seconds(match.group(11)),
        "gapSeconds": seconds(match.group(12)) if match.group(12) else 0.0,
        "federationPoints": seconds(match.group(13)),
        "runResults": [run_result(index, token) for index, token in enumerate(run_tokens, 1)],
    })
    return entry


def parse_simple_unclassified(line: str, target_club: str) -> dict[str, Any] | None:
    pattern = rf"^---\s+(\d+)\s+(.+?),\s*(.+?)\s+((?:19|20)\d{{2}})\s+(.+?)\s+({RUN_TOKEN_PATTERN})\s+({RUN_TOKEN_PATTERN})$"
    match = re.match(pattern, line)
    if not match:
        return None
    entry = base_entry(match.group(1), match.group(2), match.group(3), match.group(4), match.group(5), target_club)
    run_tokens = [match.group(6), match.group(7)]
    entry.update({
        "status": overall_status(run_tokens),
        "runResults": [result for index, token in enumerate(run_tokens, 1) if (result := run_result(index, token))],
    })
    return entry


def parse_code_unclassified(line: str, target_club: str) -> dict[str, Any] | None:
    pattern = rf"^---\s+(\d+)\s+(\d+)\s+(.+?),\s*(.+?)\s+((?:19|20)\d{{2}})\s+(\S+)\s+(.+?)\s+({RUN_TOKEN_PATTERN})\s+({RUN_TOKEN_PATTERN})\s+---$"
    match = re.match(pattern, line)
    if not match:
        return None
    entry = base_entry(match.group(1), match.group(3), match.group(4), match.group(5), match.group(7), target_club)
    run_tokens = [match.group(8), match.group(9)]
    entry.update({
        "externalAthleteId": match.group(2),
        "federation": match.group(6),
        "status": overall_status(run_tokens),
        "runResults": [result for index, token in enumerate(run_tokens, 1) if (result := run_result(index, token))],
    })
    return entry


def parse_code_single_classified(line: str, target_club: str) -> dict[str, Any] | None:
    pattern = rf"^(\d+)\s+(\d+)\s+(\d+)\s+(.+?),\s*(.+?)\s+((?:19|20)\d{{2}})\s+(\S+)\s+(.+?)\s+({TIME_PATTERN})\s+({TIME_PATTERN})(?:\s+({TIME_PATTERN}))?\s+({NUMBER_PATTERN})$"
    match = re.match(pattern, line)
    if not match:
        return None
    entry = base_entry(match.group(2), match.group(4), match.group(5), match.group(6), match.group(8), target_club)
    entry.update({
        "externalAthleteId": match.group(3), "federation": match.group(7),
        "status": "CLASSIFIED", "rank": int(match.group(1)),
        "officialTimeSeconds": seconds(match.group(10)),
        "gapSeconds": seconds(match.group(11)) if match.group(11) else 0.0,
        "federationPoints": decimal_number(match.group(12)),
        "runResults": [run_result(1, match.group(9))],
    })
    return entry


def parse_code_single_unclassified(line: str, target_club: str) -> dict[str, Any] | None:
    pattern = rf"^---\s+(\d+)\s+(\d+)\s+(.+?),\s*(.+?)\s+((?:19|20)\d{{2}})\s+(\S+)\s+(.+?)\s+(NAS|NIZ|DIS)\s+---$"
    match = re.match(pattern, line)
    if not match:
        return None
    entry = base_entry(match.group(1), match.group(3), match.group(4), match.group(5), match.group(7), target_club)
    entry.update({
        "externalAthleteId": match.group(2), "federation": match.group(6),
        "status": STATUS_CODES[match.group(8)],
        "runResults": [run_result(1, match.group(8))],
    })
    return entry


def parse_entry(line: str, source_format: str, target_club: str, single_run_table: bool = False) -> dict[str, Any] | None:
    if source_format == FORMAT_RACE_CODE:
        if single_run_table:
            return parse_code_single_classified(line, target_club) or parse_code_single_unclassified(line, target_club)
        return (
            parse_code_classified(line, target_club)
            or parse_code_unclassified(line, target_club)
            or parse_code_single_classified(line, target_club)
            or parse_code_single_unclassified(line, target_club)
        )
    return parse_simple_classified(line, target_club) or parse_simple_unclassified(line, target_club)


def dsvalpin_group_from_start_list(group: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": group["id"],
        "label": group["label"],
        "ageClass": group["ageClass"],
        "competitionCategory": group["competitionCategory"],
        "birthYears": group.get("birthYears", []),
        "classificationMethod": group.get("classificationMethod", "SUM_OF_RUNS"),
        "entries": [],
    }


def vola_group_from_start_list(group: dict[str, Any]) -> dict[str, Any]:
    result = dsvalpin_group_from_start_list(group)
    result["classificationMethod"] = "OFFICIAL_TOTAL"
    return result


def parse_vola(lines: list[str], start_list: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    groups = [vola_group_from_start_list(group) for group in start_list["groups"]]
    groups_by_id = {group["id"]: group for group in groups}
    starter_by_number: dict[int, tuple[dict[str, Any], dict[str, Any]]] = {
        starter["startNumber"]: (groups_by_id[group["id"]], starter)
        for group in start_list["groups"]
        for starter in group["starters"]
    }
    entries_by_number: dict[int, dict[str, Any]] = {}
    warnings: list[str] = []
    current_status: str | None = None
    current_run = 1
    in_results = False
    classified_pattern = re.compile(r"^(\d+)\s+(\d+)\s+(.+?)\s+((?:19|20)\d{2})(?:\s+(.*))?$")
    status_pattern = re.compile(
        r"^(Nicht am Start|Nicht im Ziel|Disqualifiziert)(?:\s*-\s*Lauf\s*(\d+))?",
        re.IGNORECASE,
    )
    time_pattern = re.compile(r"\d+(?:\.\d{2}|:\d{2}[.,]\d{2})$")

    def identity(starter: dict[str, Any]) -> dict[str, Any]:
        return {
            key: starter[key]
            for key in ("startNumber", "externalAthleteId", "fullName", "displayName", "birthYear", "federation", "club", "targetClub")
            if key in starter
        }

    for line in lines:
        if line.startswith("Platz Nr. Name und Vorname"):
            in_results = True
            current_status = None
            continue
        if re.fullmatch(r"(?:weiblich|männlich|maennlich)\s*/\s*(?:19|20)\d{2}", line, re.IGNORECASE):
            current_status = None
            continue
        status_match = status_pattern.match(line)
        if status_match:
            current_status = {
                "nicht am start": "DNS",
                "nicht im ziel": "DNF",
                "disqualifiziert": "DSQ",
            }[status_match.group(1).casefold()]
            current_run = int(status_match.group(2) or 1)
            continue
        if not in_results:
            continue

        if current_status:
            status_entry = re.match(r"^(\d+)\s+.+?\s+(?:19|20)\d{2}(?:\s+.*)?$", line)
            if not status_entry:
                continue
            start_number = int(status_entry.group(1))
            pair = starter_by_number.get(start_number)
            if not pair:
                warnings.append(f"Keine Wertungsgruppe für Startnummer {start_number} gefunden")
                continue
            target_group, starter = pair
            entry = entries_by_number.get(start_number)
            run = {"runNumber": current_run, "status": current_status}
            if entry:
                if run not in entry["runResults"]:
                    entry["runResults"].append(run)
                if current_status == "DSQ" or entry["status"] == "DNS":
                    entry["status"] = current_status
            else:
                entry = {**identity(starter), "status": current_status, "runResults": [run]}
                target_group["entries"].append(entry)
                entries_by_number[start_number] = entry
            continue

        match = classified_pattern.match(line)
        if not match:
            continue
        rank, start_number = int(match.group(1)), int(match.group(2))
        pair = starter_by_number.get(start_number)
        if not pair:
            warnings.append(f"Keine Wertungsgruppe für Startnummer {start_number} gefunden")
            continue
        remainder = (match.group(5) or "").split()
        first_time = next(
            (index for index in range(max(0, len(remainder) - 5), len(remainder) - 2) if all(time_pattern.fullmatch(token) for token in remainder[index:index + 3])),
            None,
        )
        if first_time is None:
            warnings.append(f"Ergebnis für Startnummer {start_number} nicht erkannt: {line[:100]}")
            continue
        values = remainder[first_time:]
        run_one, run_two, total = values[:3]
        gap = values[-1] if len(values) in {4, 5} else None
        target_group, starter = pair
        entry = {
            **identity(starter),
            "status": "CLASSIFIED",
            "rank": rank,
            "officialTimeSeconds": seconds(total),
            "gapSeconds": seconds(gap) if gap else 0.0,
            "runResults": [
                {"runNumber": 1, "status": "CLASSIFIED", "timeSeconds": seconds(run_one)},
                {"runNumber": 2, "status": "CLASSIFIED", "timeSeconds": seconds(run_two)},
            ],
        }
        target_group["entries"].append(entry)
        entries_by_number[start_number] = entry

    return [group for group in groups if group["entries"]], list(dict.fromkeys(warnings))


def parse_dsvalpin_detail(detail: str, previous_entry: dict[str, Any] | None, position: int) -> dict[str, Any] | None:
    tokens = re.sub(r"^\.+\s*", "", detail).split()
    rank_index = next((index for index, token in enumerate(tokens) if re.fullmatch(r"\d+\.", token)), None)

    if rank_index is not None:
        if rank_index == 0 or rank_index + 2 >= len(tokens):
            return None
        rank = int(tokens[rank_index].rstrip("."))
        total = tokens[rank_index - 1]
        run_tokens = tokens[rank_index + 1:rank_index + 3]
    else:
        time_tokens = [token for token in tokens if re.fullmatch(TIME_PATTERN, token)]
        if len(time_tokens) < 3:
            return None
        total = time_tokens[-3]
        run_tokens = time_tokens[-2:]
        previous_total = previous_entry.get("officialTimeSeconds") if previous_entry else None
        rank = previous_entry["rank"] if previous_total == seconds(total) else position

    if not re.fullmatch(TIME_PATTERN, total):
        return None
    if len(run_tokens) != 2 or not all(re.fullmatch(RUN_TOKEN_PATTERN, token) for token in run_tokens):
        return None
    total_seconds = seconds(total)
    return {
        "status": "CLASSIFIED",
        "rank": rank,
        "officialTimeSeconds": total_seconds,
        "runResults": [result for index, token in enumerate(run_tokens, 1) if (result := run_result(index, token))],
    }


def parse_dsvalpin_single_line(line: str, status: str | None, target_club: str) -> dict[str, Any] | None:
    """Parse compact DSValpin results where each athlete occupies one line."""
    match = re.match(r"^(\d+)\s+(.+?)\s+\.{3,}\s+(\d{2})\s+(.+)$", line)
    if not match:
        return None

    start_number, raw_name, short_birth_year, remainder = match.groups()
    tokens = remainder.split()
    if status:
        club_value = remainder
        result = {
            "status": status,
            "runResults": [{"runNumber": 1, "status": status}],
        }
    else:
        if len(tokens) < 3 or not re.fullmatch(r"\d+\.", tokens[-1]) or not re.fullmatch(TIME_PATTERN, tokens[-2]):
            return None
        rank = int(tokens.pop().rstrip("."))
        total = tokens.pop()
        gap = tokens.pop() if tokens and re.fullmatch(TIME_PATTERN, tokens[-1]) else None
        club_value = " ".join(tokens)
        if not club_value:
            return None
        result = {
            "status": "CLASSIFIED",
            "rank": rank,
            "officialTimeSeconds": seconds(total),
            "gapSeconds": seconds(gap) if gap else 0.0,
            "runResults": [{"runNumber": 1, "status": "CLASSIFIED", "timeSeconds": seconds(total)}],
        }

    person = name_without_comma(raw_name)
    club = normalize_club(club_value)
    return {
        "startNumber": int(start_number),
        "fullName": person.full_name,
        "displayName": person.display_name,
        "birthYear": 2000 + int(short_birth_year),
        "club": club,
        "targetClub": is_target_club(club, target_club),
        **result,
    }


def parse_dsvalpin(lines: list[str], start_list: dict[str, Any], target_club: str) -> tuple[list[dict[str, Any]], list[str]]:
    groups = [dsvalpin_group_from_start_list(group) for group in start_list["groups"]]
    groups_by_id = {group["id"]: group for group in groups}
    group_by_start_number = {
        starter["startNumber"]: groups_by_id[group["id"]]
        for group in start_list["groups"]
        for starter in group["starters"]
    }
    current_group: dict[str, Any] | None = None
    current_status: str | None = None
    current_run = 1
    warnings: list[str] = []
    person_pattern = re.compile(r"^(\d+)\s+(.+?)\s+\.{3,}\s+(\d{2})$")
    status_pattern = re.compile(r"^(Nicht am Start|Nicht im Ziel|Disqualifiziert)(?:\s+(\d+)\.\s+Durchgang)?$", re.IGNORECASE)
    index = 0

    while index < len(lines):
        line = lines[index]
        start_group = group_from_line(line, start_list["event"]["name"])
        if start_group:
            current_group = groups_by_id.get(start_group["id"])
            current_status = None
            index += 1
            continue

        status_match = status_pattern.match(line)
        if status_match:
            current_status = {
                "nicht am start": "DNS",
                "nicht im ziel": "DNF",
                "disqualifiziert": "DSQ",
            }[status_match.group(1).casefold()]
            current_run = int(status_match.group(2) or 1)
            index += 1
            continue

        compact_entry = parse_dsvalpin_single_line(line, current_status, target_club)
        if compact_entry:
            target_group = group_by_start_number.get(compact_entry["startNumber"]) or current_group
            if target_group is None:
                warnings.append(f"Keine Wertungsgruppe für Startnummer {compact_entry['startNumber']} gefunden")
            else:
                if current_status:
                    compact_entry["runResults"][0]["runNumber"] = current_run
                target_group["entries"].append(compact_entry)
            index += 1
            continue

        person_match = person_pattern.match(line)
        if not person_match or index + 2 >= len(lines):
            index += 1
            continue

        start_number = int(person_match.group(1))
        raw_name = person_match.group(2)
        birth_year = 2000 + int(person_match.group(3))
        club = normalize_club(lines[index + 1])
        detail = lines[index + 2]
        target_group = group_by_start_number.get(start_number) or current_group
        if target_group is None:
            warnings.append(f"Keine Wertungsgruppe für Startnummer {start_number} gefunden")
            index += 3
            continue

        try:
            person = name_without_comma(raw_name)
        except ValueError:
            person = name_surname_first(raw_name)
        entry: dict[str, Any] = {
            "startNumber": start_number,
            "fullName": person.full_name,
            "displayName": person.display_name,
            "birthYear": birth_year,
            "club": club,
            "targetClub": is_target_club(club, target_club),
        }
        if current_status:
            entry["status"] = current_status
            entry["runResults"] = [{"runNumber": current_run, "status": current_status}]
        else:
            classified = parse_dsvalpin_detail(detail, target_group["entries"][-1] if target_group["entries"] else None, len(target_group["entries"]) + 1)
            if not classified:
                warnings.append(f"Ergebnis für Startnummer {start_number} nicht erkannt: {detail[:100]}")
                index += 3
                continue
            entry.update(classified)
        target_group["entries"].append(entry)
        index += 3

    return [group for group in groups if group["entries"]], warnings


def group_for_start_number(groups: list[dict[str, Any]], start_number: int) -> dict[str, Any] | None:
    """Infer a group from the contiguous start-number blocks in a result list."""
    ranges = []
    for group in groups:
        numbers = [entry["startNumber"] for entry in group["entries"]]
        if numbers:
            ranges.append((min(numbers), max(numbers), group))
    containing = [item for item in ranges if item[0] <= start_number <= item[1]]
    if containing:
        return min(containing, key=lambda item: item[1] - item[0])[2]
    if not ranges:
        return None
    return min(ranges, key=lambda item: min(abs(start_number - item[0]), abs(start_number - item[1])))[2]


def parse_dsvalpin_without_start_list(lines: list[str], event: dict[str, Any], target_club: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Read current DSValpin result tables without a separate start list."""
    groups: list[dict[str, Any]] = []
    current_group: dict[str, Any] | None = None
    current_status: str | None = None
    current_run = 1
    unassigned: list[dict[str, Any]] = []
    warnings: list[str] = []
    person_pattern = re.compile(r"^(\d+)\s+(.+?)\s+(\d{4,6})\s+(\d{2})$")
    status_pattern = re.compile(r"^(Nicht am Start|Nicht im Ziel|Disqualifiziert)(?:\s+(\d+)\.\s+Durchgang)?$", re.IGNORECASE)
    detail_pattern = re.compile(rf"^(\S+)\s+({NUMBER_PATTERN})\s+({TIME_PATTERN})(?:\s+(\d+)\.)?\s+({RUN_TOKEN_PATTERN})\s+({RUN_TOKEN_PATTERN})(?:\s+.*)?$")
    compact_classified_pattern = re.compile(rf"^(\d+)\s+(.+?)\s+(\d{{4,6}})\s+(\d{{2}})\s+(.+?)\s+((?:BSV|SSV|SVS|LSS)-\S+)\s+({NUMBER_PATTERN})\s+({TIME_PATTERN})(?:\s+(\d+)\.)?$")
    compact_status_pattern = re.compile(r"^(\d+)\s+(.+?)\s+(\d{4,6})\s+(\d{2})\s+((?:BSV|SSV|SVS|LSS)-\S+)\s+(.+)$")
    index = 0
    while index < len(lines):
        line = lines[index]
        detected_group = group_from_line(line, event["name"])
        if detected_group:
            current_group = next((group for group in groups if group["id"] == detected_group["id"]), None)
            if current_group is None:
                current_group = detected_group
                groups.append(current_group)
            current_status = None
            index += 1
            continue
        status_match = status_pattern.match(line)
        if status_match:
            current_status = {"nicht am start": "DNS", "nicht im ziel": "DNF", "disqualifiziert": "DSQ"}[status_match.group(1).casefold()]
            current_run = int(status_match.group(2) or 1)
            index += 1
            continue
        compact_classified = compact_classified_pattern.match(line) if not current_status else None
        compact_status = compact_status_pattern.match(line) if current_status else None
        if compact_classified or compact_status:
            if compact_classified:
                start_number, raw_name, external_id, short_year, club_value, federation, points, total, rank_value = compact_classified.groups()
            else:
                start_number, raw_name, external_id, short_year, federation, club_value = compact_status.groups()
            try:
                person = name_without_comma(raw_name)
            except ValueError:
                person = name_surname_first(raw_name)
            entry = {
                "startNumber": int(start_number), "externalAthleteId": external_id,
                "fullName": person.full_name, "displayName": person.display_name,
                "birthYear": 2000 + int(short_year), "federation": federation,
                "club": normalize_club(club_value),
                "targetClub": is_target_club(club_value, target_club),
            }
            if compact_status:
                entry.update(status=current_status, runResults=[{"runNumber": current_run, "status": current_status}])
                unassigned.append(entry)
            elif current_group:
                total_seconds = seconds(total)
                previous = current_group["entries"][-1] if current_group["entries"] else None
                rank = int(rank_value) if rank_value else previous["rank"] if previous and previous.get("officialTimeSeconds") == total_seconds else len(current_group["entries"]) + 1
                entry.update({
                    "status": "CLASSIFIED", "rank": rank,
                    "officialTimeSeconds": total_seconds,
                    "federationPoints": decimal_number(points),
                    "runResults": [{"runNumber": 1, "status": "CLASSIFIED", "timeSeconds": total_seconds}],
                })
                current_group["entries"].append(entry)
            index += 1
            continue
        person_match = person_pattern.match(line)
        if not person_match or index + 2 >= len(lines):
            index += 1
            continue
        start_number, raw_name, external_id, short_year = person_match.groups()
        club = normalize_club(lines[index + 1])
        detail = lines[index + 2]
        try:
            person = name_without_comma(raw_name)
        except ValueError:
            person = name_surname_first(raw_name)
        entry: dict[str, Any] = {
            "startNumber": int(start_number), "externalAthleteId": external_id,
            "fullName": person.full_name, "displayName": person.display_name,
            "birthYear": 2000 + int(short_year), "club": club,
            "targetClub": is_target_club(club, target_club),
        }
        if current_status:
            federation = detail.split()[0] if detail else None
            if federation:
                entry["federation"] = federation
            entry.update(status=current_status, runResults=[{"runNumber": current_run, "status": current_status}])
            unassigned.append(entry)
        else:
            match = detail_pattern.match(detail)
            if not match or current_group is None:
                warnings.append(f"Ergebnis für Startnummer {start_number} nicht erkannt: {detail[:100]}")
                index += 3
                continue
            federation, points, total, rank_value, run_one, run_two = match.groups()
            total_seconds = seconds(total)
            previous = current_group["entries"][-1] if current_group["entries"] else None
            rank = int(rank_value) if rank_value else previous["rank"] if previous and previous.get("officialTimeSeconds") == total_seconds else len(current_group["entries"]) + 1
            entry.update({
                "federation": federation, "federationPoints": decimal_number(points),
                "status": "CLASSIFIED", "rank": rank, "officialTimeSeconds": total_seconds,
                "runResults": [result for number, token in enumerate((run_one, run_two), 1) if (result := run_result(number, token))],
            })
            current_group["entries"].append(entry)
        index += 3
    for entry in unassigned:
        target = group_for_start_number(groups, entry["startNumber"])
        if target:
            target["entries"].append(entry)
        else:
            warnings.append(f"Keine Wertungsgruppe für Startnummer {entry['startNumber']} gefunden")
    return [group for group in groups if group["entries"]], list(dict.fromkeys(warnings))


def parse_official_dsv_table(lines: list[str], event: dict[str, Any], target_club: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse DSV result rows containing rank, start number and DSV ID on one line."""
    groups: list[dict[str, Any]] = []
    current_group: dict[str, Any] | None = None
    current_status: str | None = None
    current_run = 1
    unassigned: list[dict[str, Any]] = []
    warnings: list[str] = []
    dot_time = r"(?:\d+:)?\d{1,2}[.,]\d{2}"
    classified_pattern = re.compile(rf"^(?:(\d+)\.\s+)?(\d+)\s+(\d{{4,6}})\s+(.+?)\s+((?:19|20)\d{{2}})\s+(\S+)\s+({dot_time})\s+({dot_time})\s+({dot_time})\s+({NUMBER_PATTERN})$")
    status_pattern = re.compile(r"^(Nicht am Start|Nicht im Ziel|Disqualifiziert)(?:\s+(\d+)\.\s+Durchgang)?$", re.IGNORECASE)
    status_entry_pattern = re.compile(r"^(\d+)\s+(\d{4,6})\s+(.+?)\s+((?:19|20)\d{2})\s+(\S+)$")
    index = 0
    while index < len(lines):
        line = lines[index]
        compact_line = line.casefold()
        gender_only = compact_line in {"mädchen", "maedchen", "buben"} or bool(re.fullmatch(r"m.dchen", compact_line))
        group_event_name = "U14 " + event["name"] if gender_only else event["name"]
        detected_group = group_from_line(line, group_event_name)
        if detected_group:
            current_group = next((group for group in groups if group["id"] == detected_group["id"]), None)
            if current_group is None:
                current_group = detected_group
                groups.append(current_group)
            current_status = None
            index += 1
            continue
        status_match = status_pattern.match(line)
        if status_match:
            current_status = {"nicht am start": "DNS", "nicht im ziel": "DNF", "disqualifiziert": "DSQ"}[status_match.group(1).casefold()]
            current_run = int(status_match.group(2) or 1)
            index += 1
            continue
        match = classified_pattern.match(line)
        status_entry = status_entry_pattern.match(line) if current_status else None
        if not match and not status_entry:
            index += 1
            continue
        if index + 1 >= len(lines):
            break
        club = normalize_club(lines[index + 1])
        if match:
            rank_value, start_number, external_id, raw_name, birth_year, federation, run_one, run_two, total, points = match.groups()
        else:
            start_number, external_id, raw_name, birth_year, federation = status_entry.groups()
        try:
            person = name_without_comma(raw_name)
        except ValueError:
            person = name_surname_first(raw_name)
        entry: dict[str, Any] = {
            "startNumber": int(start_number), "externalAthleteId": external_id,
            "fullName": person.full_name, "displayName": person.display_name,
            "birthYear": int(birth_year), "federation": federation, "club": club,
            "targetClub": is_target_club(club, target_club),
        }
        if current_status:
            entry.update(status=current_status, runResults=[{"runNumber": current_run, "status": current_status}])
            unassigned.append(entry)
        elif current_group:
            total_seconds = seconds(total.replace(".", ","))
            previous = current_group["entries"][-1] if current_group["entries"] else None
            rank = int(rank_value) if rank_value else previous["rank"] if previous and previous.get("officialTimeSeconds") == total_seconds else len(current_group["entries"]) + 1
            entry.update({
                "status": "CLASSIFIED", "rank": rank, "officialTimeSeconds": total_seconds,
                "federationPoints": decimal_number(points),
                "runResults": [
                    {"runNumber": 1, "status": "CLASSIFIED", "timeSeconds": seconds(run_one.replace(".", ","))},
                    {"runNumber": 2, "status": "CLASSIFIED", "timeSeconds": seconds(run_two.replace(".", ","))},
                ],
            })
            current_group["entries"].append(entry)
        index += 2
    for entry in unassigned:
        target = group_for_start_number(groups, entry["startNumber"])
        if target:
            target["entries"].append(entry)
        else:
            warnings.append(f"Keine Wertungsgruppe für Startnummer {entry['startNumber']} gefunden")
    return [group for group in groups if group["entries"]], list(dict.fromkeys(warnings))


def finalize_group(group: dict[str, Any]) -> None:
    classified = [entry for entry in group["entries"] if entry["status"] == "CLASSIFIED"]
    if not classified:
        return
    winner = min(entry["officialTimeSeconds"] for entry in classified)
    slowest = max(entry["officialTimeSeconds"] for entry in classified)
    group["winnerTimeSeconds"] = winner
    group["slowestClassifiedTimeSeconds"] = slowest
    for entry in classified:
        entry["percentageGap"] = round((entry["officialTimeSeconds"] - winner) / winner * 100, 6)


def race_id_for(start_list: dict[str, Any] | None, result_path: Path, event: dict[str, Any]) -> str:
    if start_list:
        start_event = start_list["event"]
        return f"race-{slugify(start_event.get('competitionNumber') or Path(start_list['source']['fileName']).stem)}"
    return f"race-{slugify(event.get('competitionNumber') or result_path.stem)}"


def extract_result_list(path: Path, start_list: dict[str, Any] | None = None, target_club: str = TARGET_CLUB) -> dict[str, Any]:
    lines, text = extract_pdf_text(path)
    source_format = detect_format(text)
    if source_format not in {FORMAT_DSVALPIN, FORMAT_RACE_CODE, FORMAT_RACE_SIMPLE, FORMAT_VOLA}:
        raise ValueError(f"Unsupported result format in {path.name}")
    event = event_metadata(lines, text)
    groups: list[dict[str, Any]] = []
    current_group: dict[str, Any] | None = None
    in_results = False
    warnings: list[str] = []
    single_run_table = bool(re.search(r"Zeit-1\s+Laufzeit\s+(?:Diff\s*\[s\]\s+)?Punkte", text, re.IGNORECASE))

    if source_format == FORMAT_DSVALPIN:
        if start_list:
            groups, warnings = parse_dsvalpin(lines, start_list, target_club)
        else:
            groups, warnings = parse_dsvalpin_without_start_list(lines, event, target_club)
    elif source_format == FORMAT_VOLA:
        if not start_list:
            raise ValueError("Vola result lists require --start-list for group assignment")
        groups, warnings = parse_vola(lines, start_list)
    elif any("Rang Stnr DSV-ID Teilnehmer + Verein" in line for line in lines):
        groups, warnings = parse_official_dsv_table(lines, event, target_club)
    else:
        for line in lines:
            group = group_from_line(line, event["name"])
            if group:
                current_group = group
                groups.append(group)
                in_results = True
                continue
            if in_results and line.startswith(("Nicht am Start", "Nicht im Ziel", "Disqualifiziert", "Bewerbsstatistik")):
                break
            if not in_results or current_group is None:
                continue
            entry = parse_entry(line, source_format, target_club, single_run_table)
            if entry:
                current_group["entries"].append(entry)
            elif re.match(r"^(?:---|\d+)\s+\d+\s+", line):
                warnings.append(f"Nicht erkannte Ergebniszeile in {current_group['label']}: {line[:140]}")

    groups = [group for group in groups if group["entries"]]
    if not groups:
        raise ValueError(f"Keine Ergebnisgruppen in {path.name} erkannt")
    for group in groups:
        finalize_group(group)

    document = {
        "schemaVersion": 1,
        "documentType": "RACE_RESULT",
        "raceId": race_id_for(start_list, path, event),
        "source": {
            "fileName": path.name,
            "format": source_format,
            "extractedAt": datetime.now(timezone.utc).isoformat(),
        },
        "event": event,
        "official": True,
        "groups": groups,
        "warnings": list(dict.fromkeys(warnings)),
    }
    if calculations := points_calculations(text):
        document["pointsCalculations"] = calculations
        document["pointsNormalization"] = normalize_federation_points(groups, calculations, event.get("discipline", "OTHER"))
    if statistics := competition_statistics(text):
        document["competitionStatistics"] = statistics

    if start_list:
        expected = {
            starter["startNumber"]
            for group in start_list["groups"]
            for starter in group["starters"]
            if starter["targetClub"]
        }
        actual = {
            entry["startNumber"]
            for group in groups
            for entry in group["entries"]
            if entry["targetClub"]
        }
        for number in sorted(expected - actual):
            document["warnings"].append(f"Oberhachinger Startnummer {number} fehlt im Ergebnis")
        for number in sorted(actual - expected):
            document["warnings"].append(f"Oberhachinger Startnummer {number} fehlt in der Startliste")
        document["matchedStartList"] = start_list["source"]["fileName"]
    return document


def summarize(document: dict[str, Any]) -> dict[str, Any]:
    entries = [entry for group in document["groups"] for entry in group["entries"]]
    target_entries = [entry for entry in entries if entry["targetClub"]]
    statuses: dict[str, int] = {}
    for entry in target_entries:
        statuses[entry["status"]] = statuses.get(entry["status"], 0) + 1
    return {
        "file": document["source"]["fileName"],
        "format": document["source"]["format"],
        "raceId": document["raceId"],
        "groups": len(document["groups"]),
        "entries": len(entries),
        "targetClubEntries": len(target_entries),
        "targetClubStatuses": statuses,
        "warnings": len(document["warnings"]),
    }


def default_output_path(source_path: Path) -> Path:
    workspace = Path(__file__).resolve().parents[3]
    return workspace / "data" / "result-lists" / "processed" / f"{source_path.stem}.json"


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="Path to a text-based result-list PDF")
    parser.add_argument("--start-list", type=Path, help="Normalized start-list JSON used for pairing and validation")
    parser.add_argument("--output", type=Path, help="Output JSON path")
    parser.add_argument("--target-club", default=TARGET_CLUB)
    arguments = parser.parse_args(argv)

    source_path = arguments.pdf.resolve()
    start_list = json.loads(arguments.start_list.read_text(encoding="utf-8")) if arguments.start_list else None
    output_path = (arguments.output or default_output_path(source_path)).resolve()
    document = extract_result_list(source_path, start_list, arguments.target_club)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**summarize(document), "output": str(output_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
