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
    TARGET_CLUB,
    clean_space,
    detect_format,
    event_metadata,
    extract_pdf_text,
    is_target_club,
    name_from_comma,
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


def group_from_line(line: str, event_name: str) -> dict[str, Any] | None:
    normalized = line.casefold()
    birth_years: list[int] = []
    if normalized in {"mädchen", "maedchen", "buben"}:
        age_match = re.search(r"\bU(\d+)\b", event_name, re.IGNORECASE)
        age_class = f"U{age_match.group(1)}" if age_match else "OPEN"
        category = "FEMALE" if normalized in {"mädchen", "maedchen"} else "MALE"
    else:
        age_match = re.fullmatch(r"U(\d+)(?:\s+((?:19|20)\d{2}))?\s+(weiblich|männlich|maennlich|mädchen|maedchen|buben)", line, re.IGNORECASE)
        if not age_match:
            return None
        age_class = f"U{age_match.group(1)}"
        if age_match.group(2):
            birth_years = [int(age_match.group(2))]
        category = "FEMALE" if age_match.group(3).casefold() in {"weiblich", "mädchen", "maedchen"} else "MALE"
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


def parse_entry(line: str, source_format: str, target_club: str) -> dict[str, Any] | None:
    if source_format == FORMAT_RACE_CODE:
        return parse_code_classified(line, target_club) or parse_code_unclassified(line, target_club)
    return parse_simple_classified(line, target_club) or parse_simple_unclassified(line, target_club)


def dsvalpin_group_from_start_list(group: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": group["id"],
        "label": group["label"],
        "ageClass": group["ageClass"],
        "competitionCategory": group["competitionCategory"],
        "birthYears": group.get("birthYears", []),
        "classificationMethod": "SUM_OF_RUNS",
        "entries": [],
    }


def parse_dsvalpin_detail(detail: str, previous_entry: dict[str, Any] | None, position: int) -> dict[str, Any] | None:
    tokens = re.sub(r"^\.+\s*", "", detail).split()
    rank_index = next((index for index, token in enumerate(tokens) if re.fullmatch(r"\d+\.", token)), None)
    time_tokens = [token for token in tokens if re.fullmatch(TIME_PATTERN, token)]
    if len(time_tokens) < 3:
        return None

    if rank_index is not None:
        rank = int(tokens[rank_index].rstrip("."))
        total = tokens[rank_index - 1]
        run_tokens = tokens[rank_index + 1:rank_index + 3]
    else:
        total = time_tokens[-3]
        run_tokens = time_tokens[-2:]
        previous_total = previous_entry.get("officialTimeSeconds") if previous_entry else None
        rank = previous_entry["rank"] if previous_total == seconds(total) else position

    if len(run_tokens) != 2 or not all(re.fullmatch(TIME_PATTERN, token) for token in run_tokens):
        return None
    total_seconds = seconds(total)
    return {
        "status": "CLASSIFIED",
        "rank": rank,
        "officialTimeSeconds": total_seconds,
        "runResults": [run_result(index, token) for index, token in enumerate(run_tokens, 1)],
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
    status_pattern = re.compile(r"^(Nicht am Start|Nicht im Ziel|Disqualifiziert)\s+(\d+)\.\s+Durchgang$", re.IGNORECASE)
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
            current_run = int(status_match.group(2))
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

        person = name_without_comma(raw_name)
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
    if source_format not in {FORMAT_DSVALPIN, FORMAT_RACE_CODE, FORMAT_RACE_SIMPLE}:
        raise ValueError(f"Unsupported result format in {path.name}")
    event = event_metadata(lines, text)
    groups: list[dict[str, Any]] = []
    current_group: dict[str, Any] | None = None
    in_results = False
    warnings: list[str] = []

    if source_format == FORMAT_DSVALPIN:
        if not start_list:
            raise ValueError("DSValpin result lists require --start-list for group assignment")
        groups, warnings = parse_dsvalpin(lines, start_list, target_club)
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
            entry = parse_entry(line, source_format, target_club)
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
