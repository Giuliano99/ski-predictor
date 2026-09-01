"""Extract text-based ski race start-list PDFs into normalized local JSON."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pypdf import PdfReader


FORMAT_DSVALPIN = "DSVALPIN"
FORMAT_RACE_CODE = "RACE_HOROLOGY_CODE"
FORMAT_RACE_SIMPLE = "RACE_HOROLOGY_SIMPLE"
TARGET_CLUB = "Skiteam Oberhaching"


@dataclass(frozen=True)
class PersonName:
    full_name: str
    display_name: str


def clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-") or "group"


def normalize_club(value: str) -> str:
    cleaned = clean_space(value).rstrip(".")
    comparison = re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", cleaned).encode("ascii", "ignore").decode("ascii").lower())
    if comparison in {"skiteamoberhaching", "skiteamoberhachingev"}:
        return TARGET_CLUB
    return cleaned


def is_target_club(value: str, target_club: str) -> bool:
    return normalize_club(value).casefold() == normalize_club(target_club).casefold()


def name_from_comma(last_name: str, first_name: str) -> PersonName:
    surname = clean_space(last_name)
    given = clean_space(first_name)
    initial = next((character.upper() for character in surname if character.isalpha()), "?")
    return PersonName(full_name=f"{given} {surname}", display_name=f"{given} {initial}.")


def name_without_comma(raw_name: str) -> PersonName:
    tokens = clean_space(raw_name).split(" ")
    surname_tokens: list[str] = []
    first_name_tokens: list[str] = []

    for index, token in enumerate(tokens):
        letters = "".join(character for character in token if character.isalpha())
        if letters and letters == letters.upper() and not first_name_tokens:
            surname_tokens.append(token)
        else:
            first_name_tokens = tokens[index:]
            break

    if not surname_tokens or not first_name_tokens:
        raise ValueError(f"Name cannot be separated: {raw_name}")

    surname = " ".join(surname_tokens)
    given = " ".join(first_name_tokens)
    initial = next((character.upper() for character in surname if character.isalpha()), "?")
    return PersonName(full_name=f"{given} {surname}", display_name=f"{given} {initial}.")


def extract_pdf_text(path: Path) -> tuple[list[str], str]:
    reader = PdfReader(str(path))
    page_texts = [page.extract_text() or "" for page in reader.pages]
    lines = [clean_space(line) for text in page_texts for line in text.splitlines() if clean_space(line)]
    return lines, "\n".join(page_texts)


def detect_format(text: str) -> str:
    if "DSValpin" in text:
        return FORMAT_DSVALPIN
    if re.search(r"Stnr\s+Code\s+Teilnehmer", text, re.IGNORECASE):
        return FORMAT_RACE_CODE
    return FORMAT_RACE_SIMPLE


def parse_date(value: str) -> str | None:
    for pattern in ("%d-%m-%Y", "%d.%m.%Y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            continue
    return None


def event_metadata(lines: list[str], text: str) -> dict[str, Any]:
    ignored = (
        "seite ", "www.", "copyright", "version ", "ausdruck:", "timing:",
        "startliste", "dsvalpin", "bewerbsnummer", "auswertung:",
    )
    title_candidates: list[str] = []
    for line in lines[:20]:
        lower = line.casefold()
        if lower.startswith(ignored) or re.match(r"^\d{1,2}[./-]\d{1,2}[./-]\d{4}", line):
            continue
        if line.casefold() in {"slalom", "riesenslalom", "laufzeit"}:
            continue
        if any(word in lower for word in ("cup", "pokal", "kidscross", "gedächtnisrennen")):
            title_candidates.append(line)

    event_name = clean_space(" ".join(dict.fromkeys(title_candidates))) or "Unbekannte Veranstaltung"
    event_name = re.sub(r"-\s+", "-", event_name)
    competition_match = re.search(r"Bewerbsnummer\s*:?[ ]*([A-Za-z0-9-]+)", text, re.IGNORECASE)
    run_match = re.search(r"STARTLISTE\s+(\d+)\.?\s*Durchgang", text, re.IGNORECASE)

    date_value: str | None = None
    location: str | None = None
    for index, line in enumerate(lines):
        match = re.match(r"^(\d{1,2}[./-]\d{1,2}[./-]\d{4})(?:\s*/\s*(.+?))?(?:\s+Bewerbsnummer.*)?$", line)
        if not match:
            continue
        date_value = parse_date(match.group(1))
        location = clean_space(match.group(2) or "") or None
        if not location and index + 1 < len(lines):
            candidate = lines[index + 1]
            if not candidate.casefold().startswith(("organisator", "kampfgericht", "stnr")):
                location = candidate
        break

    metadata: dict[str, Any] = {"name": event_name}
    if re.search(r"KidsCross", text, re.IGNORECASE):
        metadata["discipline"] = "KIDS_CROSS"
    elif re.search(r"Riesenslalom|\(RS\)|Gedächtnisrennen RS", text, re.IGNORECASE):
        metadata["discipline"] = "GS"
    elif re.search(r"\bSlalom\b|\bSL\b", text, re.IGNORECASE):
        metadata["discipline"] = "SL"
    else:
        metadata["discipline"] = "OTHER"
    if date_value:
        metadata["date"] = date_value
    if location:
        metadata["location"] = re.sub(r"\s*\(GER\).*$", "", location).strip()
    if competition_match:
        metadata["competitionNumber"] = competition_match.group(1)
    if run_match:
        metadata["run"] = int(run_match.group(1))
    return metadata


def parse_group(line: str) -> dict[str, Any] | None:
    age_match = re.search(r"\b(U\d+)\b", line, re.IGNORECASE)
    if not age_match or not re.search(r"weiblich|männlich|maennlich", line, re.IGNORECASE):
        return None

    age_class = age_match.group(1).upper()
    category = "FEMALE" if re.search(r"weiblich", line, re.IGNORECASE) else "MALE"
    year_match = re.search(r"\b((?:19|20)\d{2})\b", line)
    birth_years = [int(year_match.group(1))] if year_match else []
    group_id_parts = [age_class.lower(), category.lower()]
    if birth_years:
        group_id_parts.append(str(birth_years[0]))

    return {
        "id": slugify("-".join(group_id_parts)),
        "label": clean_space(line),
        "ageClass": age_class,
        "competitionCategory": category,
        "birthYears": birth_years,
        "starters": [],
    }


def parse_dsvalpin_entry(line: str, target_club: str) -> dict[str, Any] | None:
    match = re.match(r"^(\d+)\s+(.+?)\s+(\d{5})\s+(\d{2})\s+(.+?)\s+([A-Z]{3}-[A-Z]+)\s+_+\s+---", line)
    if not match:
        return None
    person = name_without_comma(match.group(2))
    club = normalize_club(match.group(5))
    return {
        "startNumber": int(match.group(1)),
        "externalAthleteId": match.group(3),
        "fullName": person.full_name,
        "displayName": person.display_name,
        "birthYear": 2000 + int(match.group(4)),
        "federation": match.group(6),
        "club": club,
        "targetClub": is_target_club(club, target_club),
    }


def parse_code_entry(line: str, target_club: str) -> dict[str, Any] | None:
    match = re.match(r"^(\d+)\s+(\d+)\s+(.+?),\s*(.+?)\s+((?:19|20)\d{2})\s+(\S+)\s+(.+?)\s+(\d+(?:\.\d+)?)$", line)
    if not match:
        return None
    person = name_from_comma(match.group(3), match.group(4))
    club = normalize_club(match.group(7))
    return {
        "startNumber": int(match.group(1)),
        "externalAthleteId": match.group(2),
        "fullName": person.full_name,
        "displayName": person.display_name,
        "birthYear": int(match.group(5)),
        "federation": match.group(6),
        "club": club,
        "targetClub": is_target_club(club, target_club),
        "seedPoints": float(match.group(8)),
    }


def parse_simple_entry(line: str, target_club: str) -> dict[str, Any] | None:
    match = re.match(r"^(\d+)\s+(.+?),\s*(.+?)\s+((?:19|20)\d{2})\s+(.+)$", line)
    if not match:
        return None
    person = name_from_comma(match.group(2), match.group(3))
    club = normalize_club(match.group(5))
    return {
        "startNumber": int(match.group(1)),
        "fullName": person.full_name,
        "displayName": person.display_name,
        "birthYear": int(match.group(4)),
        "club": club,
        "targetClub": is_target_club(club, target_club),
    }


def parse_entry(line: str, source_format: str, target_club: str) -> dict[str, Any] | None:
    if source_format == FORMAT_DSVALPIN:
        return parse_dsvalpin_entry(line, target_club)
    if source_format == FORMAT_RACE_CODE:
        return parse_code_entry(line, target_club)
    return parse_simple_entry(line, target_club)


def extract_start_list(path: Path, target_club: str = TARGET_CLUB) -> dict[str, Any]:
    lines, text = extract_pdf_text(path)
    source_format = detect_format(text)
    groups: list[dict[str, Any]] = []
    current_group: dict[str, Any] | None = None
    warnings: list[str] = []

    for line in lines:
        group = parse_group(line)
        if group:
            current_group = group
            groups.append(group)
            continue
        if current_group is None:
            continue
        entry = parse_entry(line, source_format, target_club)
        if entry:
            current_group["starters"].append(entry)
        elif re.match(r"^\d+\s+", line) and not re.match(r"^\d{1,2}[./-]\d{1,2}[./-]\d{4}", line):
            warnings.append(f"Nicht erkannte Tabellenzeile in {current_group['label']}: {line[:120]}")

    groups = [group for group in groups if group["starters"]]
    if not groups:
        raise ValueError(f"Keine Startergruppen in {path.name} erkannt")

    return {
        "schemaVersion": 1,
        "documentType": "START_LIST",
        "source": {
            "fileName": path.name,
            "format": source_format,
            "extractedAt": datetime.now(timezone.utc).isoformat(),
        },
        "event": event_metadata(lines, text),
        "groups": groups,
        "warnings": list(dict.fromkeys(warnings)),
    }


def summarize(document: dict[str, Any]) -> dict[str, Any]:
    starters = [starter for group in document["groups"] for starter in group["starters"]]
    return {
        "file": document["source"]["fileName"],
        "format": document["source"]["format"],
        "groups": len(document["groups"]),
        "starters": len(starters),
        "targetClubStarters": sum(1 for starter in starters if starter["targetClub"]),
        "warnings": len(document["warnings"]),
    }


def default_output_path(source_path: Path) -> Path:
    workspace = Path(__file__).resolve().parents[3]
    return workspace / "data" / "result-lists" / "processed" / f"{source_path.stem}.json"


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="Path to a text-based start-list PDF")
    parser.add_argument("--output", type=Path, help="Output JSON path")
    parser.add_argument("--target-club", default=TARGET_CLUB, help="Club used for targetClub classification")
    arguments = parser.parse_args(argv)

    source_path = arguments.pdf.resolve()
    output_path = (arguments.output or default_output_path(source_path)).resolve()
    document = extract_start_list(source_path, arguments.target_club)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**summarize(document), "output": str(output_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
