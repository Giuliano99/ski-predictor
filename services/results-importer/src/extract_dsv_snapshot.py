#!/usr/bin/env python3
"""Extract versioned DSV ranking and race-count snapshots from PDF files.

The DSV documents use visually aligned text instead of embedded table cells.  The
extractor therefore assigns words to columns based on their horizontal position.
This also preserves clubs and first names containing spaces.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pdfplumber


RANKING = "DSV_RANKING"
RACE_COUNT = "DSV_RACE_COUNT"
CLUB_END_LIST = "DSV_CLUB_END_LIST"

TEXT_REPLACEMENTS = {
    "M�dchen": "Mädchen",
    "Sch�ler": "Schüler",
    "S�d": "Süd",
    "W�rttemberg": "Württemberg",
    "Th�ringen": "Thüringen",
    "f�r": "für",
}


def clean_text(value: str) -> str:
    value = " ".join(value.split())
    for broken, repaired in TEXT_REPLACEMENTS.items():
        value = value.replace(broken, repaired)
    return value


def decimal(value: str) -> float:
    return float(value.replace(".", "").replace(",", "."))


def season_for(date_value: datetime) -> str:
    start_year = date_value.year if date_value.month >= 7 else date_value.year - 1
    return f"{start_year}-{start_year + 1}"


def words_by_line(words: Iterable[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    lines: dict[float, list[dict[str, Any]]] = defaultdict(list)
    for word in words:
        lines[round(float(word["top"]), 1)].append(word)
    return [sorted(lines[key], key=lambda item: float(item["x0"])) for key in sorted(lines)]


def column_text(words: Iterable[dict[str, Any]], start: float, end: float | None = None) -> str:
    selected = [
        clean_text(str(word["text"]))
        for word in words
        if float(word["x0"]) >= start and (end is None or float(word["x0"]) < end)
    ]
    return clean_text(" ".join(selected))


def parse_snapshot_heading(text: str) -> tuple[datetime, str]:
    match = re.search(r"vom\s+(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2}(?::\d{2})?)", text)
    if not match:
        match = re.search(r"Stand:.*?(\d{2}\.\d{4})\s+(\d{2}:\d{2})", text)
    if not match:
        # The race-count document includes a weekday between Stand and the date.
        match = re.search(r"Stand:.*?(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})", text)
    if not match:
        raise ValueError("Kein Stichtag mit Uhrzeit im DSV-Dokument erkannt")
    value = datetime.strptime(f"{match.group(1)} {match.group(2)}", "%d.%m.%Y %H:%M:%S" if len(match.group(2)) == 8 else "%d.%m.%Y %H:%M")
    return value, value.isoformat(timespec="seconds")


def document_id(path: Path, text: str) -> str:
    match = re.search(r"(?<![A-Z0-9])(DSVSA\d+)(?!\d)", f"{path.name}\n{text}", re.IGNORECASE)
    return match.group(1).upper() if match else path.stem


def source_metadata(path: Path, source_format: str, page_count: int) -> dict[str, Any]:
    return {
        "fileName": path.name,
        "format": source_format,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "pageCount": page_count,
    }


def ranking_scope(heading: str) -> tuple[str, str, int | None]:
    if "Gesamt" in heading:
        return "OVERALL", "TOP 250 Gesamt", None
    match = re.search(r"TOP\s+100\s+(U1[46])", heading)
    if match:
        return "AGE_CLASS", f"TOP 100 {match.group(1)}", None
    match = re.search(r"TOP\s+50\s+Jg\.?\s*(\d{4})", heading)
    if match:
        year = int(match.group(1))
        return "BIRTH_YEAR", f"TOP 50 Jahrgang {year}", year
    raise ValueError(f"Unbekannter Ranglistenabschnitt: {heading}")


def parse_ranking_row(words: list[dict[str, Any]], scope: str) -> dict[str, Any] | None:
    athlete_id = column_text(words, 70, 110)
    if not re.fullmatch(r"\d{5}", athlete_id):
        return None
    rank_values = [int(value) for value in re.findall(r"\d+", column_text(words, 750))]
    if not rank_values:
        return None
    entry: dict[str, Any] = {
        "externalAthleteId": athlete_id,
        "lastName": column_text(words, 110, 245),
        "firstName": column_text(words, 245, 370),
        "birthYear": int(column_text(words, 370, 415)),
        "club": column_text(words, 415, 570),
        "federation": column_text(words, 570, 645),
        "basePoints": decimal(column_text(words, 645, 700)),
        "listPoints": decimal(column_text(words, 700, 750)),
    }
    # Three-digit ranks start slightly further left than one-digit ranks.
    leading_rank = int(column_text(words, 20, 70))
    if scope == "OVERALL":
        entry.update(overallRank=leading_rank, ageClassRank=rank_values[0], birthYearRank=rank_values[1])
    elif scope == "AGE_CLASS":
        entry.update(ageClassRank=leading_rank, birthYearRank=rank_values[0])
    else:
        entry.update(birthYearRank=leading_rank, ageClassRank=rank_values[0], overallRank=rank_values[1])
    return entry


def extract_ranking(path: Path, target_club: str) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    warnings: list[str] = []
    current_key: tuple[str, str] | None = None
    snapshot_at: datetime | None = None
    first_page_text = ""
    raw_page_texts: list[str] = []

    with pdfplumber.open(path) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""
        raw_page_texts.append(first_page_text)
        for page_number, page in enumerate(pdf.pages[1:], start=2):
            raw_page_text = page.extract_text() or ""
            raw_page_texts.append(raw_page_text)
            page_text = clean_text(raw_page_text)
            lines = page_text.splitlines()
            if not lines or not lines[0].startswith("TOP "):
                warnings.append(f"Seite {page_number}: Ranglistenüberschrift fehlt")
                continue
            heading = lines[0]
            page_snapshot, _ = parse_snapshot_heading(heading)
            snapshot_at = snapshot_at or page_snapshot
            scope, label, birth_year = ranking_scope(heading)
            if "Mädchen" in page_text:
                gender = "FEMALE"
            elif re.search(r"\bBuben\b", page_text):
                gender = "MALE"
            elif current_key and current_key[0] == label:
                gender = current_key[1]
            else:
                warnings.append(f"Seite {page_number}: Geschlecht nicht erkannt")
                continue

            key = (label, gender)
            if current_key != key:
                section: dict[str, Any] = {"scope": scope, "label": label, "gender": gender, "entries": []}
                if scope == "AGE_CLASS":
                    section["ageClass"] = label[-3:]
                if birth_year is not None:
                    section["birthYear"] = birth_year
                sections.append(section)
                current_key = key

            for row in words_by_line(page.extract_words()):
                entry = parse_ranking_row(row, scope)
                if entry:
                    sections[-1]["entries"].append(entry)

    if snapshot_at is None:
        raise ValueError(f"Keine Ranglisteneinträge in {path.name} erkannt")
    all_entries = [entry for section in sections for entry in section["entries"]]
    target = target_club.casefold()
    target_entries = [entry for entry in all_entries if entry["club"].casefold() == target]
    return {
        "schemaVersion": 1,
        "documentType": RANKING,
        "source": source_metadata(path, "DSV_RANKING_PDF", len(raw_page_texts)),
        "rawText": "\n\f\n".join(raw_page_texts),
        "snapshot": {
            "documentId": document_id(path, first_page_text),
            "seasonId": season_for(snapshot_at),
            "publishedAt": snapshot_at.isoformat(timespec="seconds"),
            "timezone": "Europe/Berlin",
        },
        "sections": sections,
        "statistics": {
            "sections": len(sections),
            "entries": len(all_entries),
            "uniqueAthletes": len({entry["externalAthleteId"] for entry in all_entries}),
            "targetClubEntries": len(target_entries),
            "targetClubUniqueAthletes": len({entry["externalAthleteId"] for entry in target_entries}),
        },
        "warnings": warnings,
    }


def parse_club_end_list_row(words: list[dict[str, Any]], club: str) -> dict[str, Any] | None:
    athlete_id = column_text(words, 20, 60)
    if not re.fullmatch(r"\d{5}", athlete_id):
        return None
    gender = column_text(words, 280, 315)
    if gender not in {"F", "M"}:
        return None
    return {
        "externalAthleteId": athlete_id,
        "lastName": column_text(words, 60, 160),
        "firstName": column_text(words, 160, 250),
        "birthYear": int(column_text(words, 250, 280)),
        "gender": "FEMALE" if gender == "F" else "MALE",
        "club": club,
        "federation": None,
        "basePoints": decimal(column_text(words, 315, 395)),
        "listPoints": decimal(column_text(words, 395, 455)),
        "overallRank": int(column_text(words, 455, 505)),
        "ageClassRank": int(column_text(words, 505, 545)),
        "birthYearRank": int(column_text(words, 545)),
    }


def extract_club_end_list(path: Path, target_club: str) -> dict[str, Any]:
    """Extract the DSV end list sorted by clubs as next season's base snapshot."""
    raw_page_texts: list[str] = []
    entries_by_gender: dict[str, list[dict[str, Any]]] = {"FEMALE": [], "MALE": []}
    current_club = ""
    snapshot_at: datetime | None = None
    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            raw_text = page.extract_text() or ""
            raw_page_texts.append(raw_text)
            if snapshot_at is None:
                try:
                    snapshot_at, _ = parse_snapshot_heading(raw_text)
                except ValueError:
                    pass
            for row in words_by_line(page.extract_words()):
                row_text = clean_text(" ".join(str(word["text"]) for word in row))
                entry = parse_club_end_list_row(row, current_club)
                if entry:
                    entries_by_gender[entry["gender"]].append(entry)
                    continue
                if (
                    row_text
                    and not re.search(r"DSV-ID|Liste nach Vereinen|Christian Scholz|Seite \d+", row_text)
                    and not re.fullmatch(r"\d{2}\.\d{2}\.\d{4}.*", row_text)
                    and 55 <= min((float(word["x0"]) for word in row), default=0) <= 90
                    and not any(re.fullmatch(r"\d{5}", str(word["text"])) for word in row)
                ):
                    current_club = row_text
    if snapshot_at is None or not any(entries_by_gender.values()):
        raise ValueError(f"Keine DSV-Vereinsendlisteneinträge in {path.name} erkannt")
    all_entries = entries_by_gender["FEMALE"] + entries_by_gender["MALE"]
    target = target_club.casefold()
    target_entries = [entry for entry in all_entries if entry["club"].casefold() == target]
    return {
        "schemaVersion": 1,
        "documentType": RANKING,
        "source": source_metadata(path, "DSV_CLUB_END_LIST_PDF", len(raw_page_texts)),
        "rawText": "\n\f\n".join(raw_page_texts),
        "snapshot": {
            "documentId": document_id(path, raw_page_texts[0]),
            "seasonId": season_for(snapshot_at),
            "publishedAt": snapshot_at.isoformat(timespec="seconds"),
            "timezone": "Europe/Berlin",
            "snapshotKind": "SEASON_START_BASE",
            "sourceSeasonId": season_for(snapshot_at),
        },
        "sections": [
            {"scope": "OVERALL", "label": "Saison-Startwerte", "gender": gender, "entries": entries}
            for gender, entries in entries_by_gender.items() if entries
        ],
        "statistics": {
            "sections": sum(bool(entries) for entries in entries_by_gender.values()),
            "entries": len(all_entries),
            "uniqueAthletes": len({entry["externalAthleteId"] for entry in all_entries}),
            "targetClubEntries": len(target_entries),
            "targetClubUniqueAthletes": len({entry["externalAthleteId"] for entry in target_entries}),
        },
        "warnings": [],
    }


def read_text_file(path: Path) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Zeichenkodierung von {path.name} nicht erkannt")


def parse_text_start_row(line: str) -> dict[str, Any] | None:
    if len(line) < 104 or not re.fullmatch(r"\d{5}", line[0:5]):
        return None
    birth_year = line[44:48].strip()
    points = line[97:103].strip()
    gender = line[105:106].strip()
    if not re.fullmatch(r"\d{4}", birth_year) or not re.fullmatch(r"\d+(?:[.,]\d{2})", points) or gender not in {"F", "M"}:
        return None
    return {
        "externalAthleteId": line[0:5],
        "lastName": clean_text(line[10:30]),
        "firstName": clean_text(line[30:44]),
        "birthYear": int(birth_year),
        "gender": "FEMALE" if gender == "F" else "MALE",
        "club": clean_text(line[54:84]),
        "federation": clean_text(line[84:97]),
        "basePoints": float(points.replace(",", ".")),
        "listPoints": float(points.replace(",", ".")),
        "overallRank": None,
        "ageClassRank": None,
        "birthYearRank": None,
    }


def assign_competition_ranks(entries: list[dict[str, Any]], field: str) -> None:
    previous_points: float | None = None
    current_rank = 0
    for position, entry in enumerate(sorted(entries, key=lambda item: (item["listPoints"], item["lastName"], item["firstName"])), start=1):
        if previous_points is None or entry["listPoints"] != previous_points:
            current_rank = position
            previous_points = entry["listPoints"]
        entry[field] = current_rank


def add_text_start_ranks(entries: list[dict[str, Any]], season_end_year: int) -> None:
    for gender in {entry["gender"] for entry in entries}:
        gender_entries = [entry for entry in entries if entry["gender"] == gender]
        assign_competition_ranks(gender_entries, "overallRank")
        for birth_year in {entry["birthYear"] for entry in gender_entries}:
            birth_year_entries = [entry for entry in gender_entries if entry["birthYear"] == birth_year]
            assign_competition_ranks(birth_year_entries, "birthYearRank")
        for age_class, ages in (("U14", {13, 14}), ("U16", {15, 16})):
            age_class_entries = [entry for entry in gender_entries if season_end_year - entry["birthYear"] in ages]
            if age_class_entries:
                assign_competition_ranks(age_class_entries, "ageClassRank")
                for entry in age_class_entries:
                    entry["ageClass"] = age_class


def extract_text_start_list(path: Path, target_club: str) -> dict[str, Any]:
    raw_text = read_text_file(path)
    entries_by_gender: dict[str, list[dict[str, Any]]] = {"FEMALE": [], "MALE": []}
    for line in raw_text.splitlines():
        entry = parse_text_start_row(line)
        if entry:
            entries_by_gender[entry["gender"]].append(entry)
    all_entries = entries_by_gender["FEMALE"] + entries_by_gender["MALE"]
    if not all_entries:
        raise ValueError(f"Keine DSV-Startwerte in {path.name} erkannt")
    identifier = document_id(path, raw_text)
    year_match = re.fullmatch(r"DSVSA(\d{2})\d+", identifier, re.IGNORECASE)
    if not year_match:
        raise ValueError(f"Keine DSV-Saison in {path.name} erkannt")
    end_year = 2000 + int(year_match.group(1))
    add_text_start_ranks(all_entries, end_year + 1)
    target = target_club.casefold()
    target_entries = [entry for entry in all_entries if entry["club"].casefold() == target]
    return {
        "schemaVersion": 1,
        "documentType": RANKING,
        "source": source_metadata(path, "DSV_SEASON_START_TXT", 1),
        "rawText": raw_text,
        "snapshot": {
            "documentId": identifier,
            "seasonId": f"{end_year}-{end_year + 1}",
            "publishedAt": f"{end_year}-07-01T00:00:00",
            "timezone": "Europe/Berlin",
            "snapshotKind": "SEASON_START_BASE",
            "sourceSeasonId": f"{end_year - 1}-{end_year}",
        },
        "sections": [
            {"scope": "OVERALL", "label": "Saison-Startwerte", "gender": gender, "entries": entries}
            for gender, entries in entries_by_gender.items() if entries
        ],
        "statistics": {
            "sections": sum(bool(entries) for entries in entries_by_gender.values()),
            "entries": len(all_entries),
            "uniqueAthletes": len({entry["externalAthleteId"] for entry in all_entries}),
            "targetClubEntries": len(target_entries),
            "targetClubUniqueAthletes": len({entry["externalAthleteId"] for entry in target_entries}),
        },
        "warnings": [],
    }


def parse_count_row(words: list[dict[str, Any]]) -> dict[str, Any] | None:
    athlete_id = column_text(words, 60, 100)
    if not re.fullmatch(r"\d{5}", athlete_id):
        return None
    source_gender = column_text(words, 535, 575)
    if source_gender not in {"F", "M"}:
        raise ValueError(f"Unbekanntes Geschlecht '{source_gender}' bei DSV-ID {athlete_id}")
    return {
        "externalAthleteId": athlete_id,
        "lastName": column_text(words, 100, 205),
        "firstName": column_text(words, 205, 270),
        "birthYear": int(column_text(words, 270, 305)),
        "club": column_text(words, 305, 425),
        "federation": column_text(words, 425, 485),
        "basePoints": decimal(column_text(words, 485, 535)),
        "gender": "FEMALE" if source_gender == "F" else "MALE",
        "listPoints": decimal(column_text(words, 575, 635)),
        "raceCount": int(column_text(words, 635)),
    }


def extract_race_count(path: Path, target_club: str) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    warnings: list[str] = []
    current_age_class: str | None = None
    snapshot_at: datetime | None = None
    full_text_parts: list[str] = []
    raw_page_texts: list[str] = []
    limits = {"U14": 20, "U16": 25}

    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            raw_page_text = page.extract_text() or ""
            raw_page_texts.append(raw_page_text)
            page_text = clean_text(raw_page_text)
            full_text_parts.append(page_text)
            heading_match = re.search(r"Rennanzahl\s+(U1[46]).*?Anz\. Rennen >=(\d+)\).*?Stand:.*?(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})", page_text)
            if heading_match:
                current_age_class = heading_match.group(1)
                parsed_at = datetime.strptime(f"{heading_match.group(3)} {heading_match.group(4)}", "%d.%m.%Y %H:%M")
                snapshot_at = snapshot_at or parsed_at
                sections.append({
                    "ageClass": current_age_class,
                    "minimumIncludedRaces": int(heading_match.group(2)),
                    "maximumRaces": limits[current_age_class],
                    "entries": [],
                })
            if current_age_class is None:
                warnings.append(f"Seite {page_number}: Altersklasse nicht erkannt")
                continue
            for row in words_by_line(page.extract_words()):
                entry = parse_count_row(row)
                if entry:
                    sections[-1]["entries"].append(entry)

    if snapshot_at is None:
        raise ValueError(f"Keine Rennanzahl-Gruppen in {path.name} erkannt")
    all_entries = [entry for section in sections for entry in section["entries"]]
    target = target_club.casefold()
    target_entries = [entry for entry in all_entries if entry["club"].casefold() == target]
    return {
        "schemaVersion": 1,
        "documentType": RACE_COUNT,
        "source": source_metadata(path, "DSV_RACE_COUNT_PDF", len(raw_page_texts)),
        "rawText": "\n\f\n".join(raw_page_texts),
        "snapshot": {
            "documentId": document_id(path, "\n".join(full_text_parts)),
            "seasonId": season_for(snapshot_at),
            "observedAt": snapshot_at.isoformat(timespec="seconds"),
            "timezone": "Europe/Berlin",
        },
        "coverage": {
            "isCompleteSeasonField": False,
            "note": "Die Quelle enthält nur Athleten ab dem je Altersklasse angegebenen Mindestwert.",
        },
        "sections": sections,
        "statistics": {
            "sections": len(sections),
            "entries": len(all_entries),
            "uniqueAthletes": len({entry["externalAthleteId"] for entry in all_entries}),
            "targetClubEntries": len(target_entries),
            "targetClubUniqueAthletes": len({entry["externalAthleteId"] for entry in target_entries}),
        },
        "warnings": warnings,
    }


def detect_document_type(path: Path) -> str:
    if path.suffix.casefold() == ".txt":
        return CLUB_END_LIST
    with pdfplumber.open(path) as pdf:
        sample = clean_text("\n".join((page.extract_text() or "") for page in pdf.pages[:2]))
    if "Rennanzahl U14" in sample or "AnzRen" in sample:
        return RACE_COUNT
    if "Liste nach Gauen/Regionen" in sample or "Liste nach Vereinen" in sample:
        return CLUB_END_LIST
    if "TOP 250 Gesamt" in sample and "Ranglisten" in sample:
        return RANKING
    raise ValueError(f"DSV-Dokumenttyp für {path.name} nicht erkannt")


def extract(path: Path, requested_type: str, target_club: str) -> dict[str, Any]:
    detected_type = detect_document_type(path) if requested_type in {"AUTO", RANKING} else requested_type
    document_type = detected_type if requested_type == "AUTO" or detected_type == CLUB_END_LIST else requested_type
    if document_type == RANKING:
        return extract_ranking(path, target_club)
    if document_type == RACE_COUNT:
        return extract_race_count(path, target_club)
    if document_type == CLUB_END_LIST:
        if path.suffix.casefold() == ".txt":
            return extract_text_start_list(path, target_club)
        return extract_club_end_list(path, target_club)
    raise ValueError(f"Nicht unterstützter DSV-Dokumenttyp: {document_type}")


def main() -> int:
    parser = argparse.ArgumentParser(description="DSV Ranglisten- oder Rennanzahl-PDF als JSON importieren")
    parser.add_argument("source", type=Path)
    parser.add_argument("--type", choices=["AUTO", RANKING, RACE_COUNT], default="AUTO")
    parser.add_argument("--target-club", default="Skiteam Oberhaching")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    output = arguments.output or Path("data/result-lists/processed") / f"{arguments.source.stem}.json"
    document = extract(arguments.source, arguments.type, arguments.target_club)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "file": arguments.source.name,
        "documentType": document["documentType"],
        "seasonId": document["snapshot"]["seasonId"],
        **document["statistics"],
        "warnings": len(document["warnings"]),
        "output": str(output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
