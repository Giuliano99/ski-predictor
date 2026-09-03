"""Validate normalized weekend results before evaluating submitted tips."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from storage_paths import resolve_path


@dataclass
class ResultReview:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.errors:
            return "FEHLER"
        if self.warnings:
            return "WARNUNGEN"
        return "BEREIT"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def target_numbers(document: dict[str, Any], collection: str) -> set[int]:
    return {
        entry["startNumber"]
        for group in document.get("groups", [])
        for entry in group.get(collection, [])
        if entry.get("targetClub")
    }


def review_results(workspace: Path, config_path: Path) -> ResultReview:
    review = ResultReview()
    config = load_json(config_path)
    configured_results = config.get("results", [])
    configured_starts = config.get("startLists", [])
    if not configured_results:
        review.errors.append("Keine Ergebnislisten konfiguriert.")
        return review
    if len(configured_results) != len(configured_starts):
        review.errors.append(f"Erwartet werden {len(configured_starts)} Ergebnislisten, konfiguriert sind {len(configured_results)}.")

    expected_race_ids: set[str] = set()
    tip_round_path = resolve_path(workspace, config["tipRound"]["output"])
    if tip_round_path.is_file():
        expected_race_ids = {race["id"] for race in load_json(tip_round_path).get("races", [])}
    else:
        review.errors.append(f"Tipprunde fehlt: {config['tipRound']['output']}")

    actual_race_ids: list[str] = []
    used_start_lists: list[str] = []
    total_statuses: Counter[str] = Counter()
    for item in configured_results:
        pdf_path = resolve_path(workspace, item["pdf"])
        start_path = resolve_path(workspace, item["startList"])
        result_path = resolve_path(workspace, item["output"])
        if not pdf_path.is_file():
            review.errors.append(f"Ergebnis-PDF fehlt: {item['pdf']}")
            continue
        if not start_path.is_file():
            review.errors.append(f"Normalisierte Startliste fehlt: {item['startList']}")
            continue
        if not result_path.is_file():
            review.errors.append(f"Normalisiertes Ergebnis fehlt: {item['output']}")
            continue

        start = load_json(start_path)
        result = load_json(result_path)
        race_id = result.get("raceId", "")
        actual_race_ids.append(race_id)
        used_start_lists.append(str(start_path).casefold())
        if not result.get("official"):
            review.errors.append(f"Ergebnis ist nicht als offiziell markiert: {item['output']}")
        if result.get("matchedStartList") != start.get("source", {}).get("fileName"):
            review.errors.append(f"Startlistenzuordnung stimmt nicht: {Path(item['pdf']).name}")

        expected = target_numbers(start, "starters")
        actual = target_numbers(result, "entries")
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        if missing:
            review.errors.append(f"{Path(item['pdf']).name}: Oberhachinger Startnummern fehlen im Ergebnis: {', '.join(map(str, missing))}")
        if extra:
            review.warnings.append(f"{Path(item['pdf']).name}: zusätzliche Oberhachinger Startnummern: {', '.join(map(str, extra))}")

        seen_numbers: set[int] = set()
        statuses: Counter[str] = Counter()
        for group in result.get("groups", []):
            for entry in group.get("entries", []):
                number = entry["startNumber"]
                if number in seen_numbers:
                    review.errors.append(f"{Path(item['pdf']).name}: Startnummer {number} kommt mehrfach vor.")
                seen_numbers.add(number)
                if entry.get("targetClub"):
                    status = entry.get("status", "UNBEKANNT")
                    statuses[status] += 1
                    total_statuses[status] += 1
                if entry.get("status") == "CLASSIFIED":
                    if not isinstance(entry.get("rank"), int) or entry["rank"] < 1:
                        review.errors.append(f"{Path(item['pdf']).name}: ungültige Platzierung bei Startnummer {number}.")
                    if not isinstance(entry.get("officialTimeSeconds"), (int, float)) or entry["officialTimeSeconds"] <= 0:
                        review.errors.append(f"{Path(item['pdf']).name}: ungültige Gesamtzeit bei Startnummer {number}.")

        for warning in result.get("warnings", []):
            if "Oberhachinger Startnummer" not in warning:
                review.warnings.append(f"{Path(item['pdf']).name}: {warning}")
        review.rows.append({
            "result": Path(item["pdf"]).name,
            "start": Path(item["startList"]).name,
            "race": result.get("event", {}).get("name", ""),
            "date": result.get("event", {}).get("date", ""),
            "targetCount": len(actual),
            "statuses": statuses,
        })

    duplicates = sorted(race_id for race_id, count in Counter(actual_race_ids).items() if race_id and count > 1)
    if duplicates:
        review.errors.append(f"Rennen wurden mehrfach importiert: {', '.join(duplicates)}")
    missing_races = expected_race_ids - set(actual_race_ids)
    unknown_races = set(actual_race_ids) - expected_race_ids
    if missing_races:
        review.errors.append(f"Ergebnisse fehlen für Rennen: {', '.join(sorted(missing_races))}")
    if unknown_races:
        review.errors.append(f"Unbekannte Ergebnis-Rennen: {', '.join(sorted(unknown_races))}")
    if len(used_start_lists) != len(set(used_start_lists)):
        review.errors.append("Mindestens eine Startliste ist mehreren Ergebnislisten zugeordnet.")

    submissions_dir = resolve_path(workspace, config["submissionsDir"])
    submissions = list(submissions_dir.glob("*.json")) if submissions_dir.is_dir() else []
    if not submissions:
        review.errors.append("Keine Tippabgaben für die Auswertung gefunden.")
    review.notes.append(
        f"{len(review.rows)} Ergebnislisten und {len(submissions)} Tippabgaben geprüft. "
        + ", ".join(f"{status}: {count}" for status, count in sorted(total_statuses.items()))
    )
    return review


def markdown_report(config: dict[str, Any], review: ResultReview) -> str:
    lines = [f"# Ergebnis-Prüfbericht {config['id']}", "", f"**Status: {review.status}**", ""]
    for title, items, empty in (
        ("Fehler", review.errors, "Keine blockierenden Fehler."),
        ("Warnungen", review.warnings, "Keine Warnungen."),
        ("Hinweise", review.notes, "Keine Hinweise."),
    ):
        lines.extend([f"## {title}", ""])
        lines.extend([f"- {item}" for item in items] or [f"- {empty}"])
        lines.append("")
    lines.extend([
        "## Erkannte Ergebnisse",
        "",
        "| Ergebnisliste | Zugeordnete Startliste | Rennen | Datum | Oberhaching | Status |",
        "|---|---|---|---|---:|---|",
    ])
    for row in review.rows:
        statuses = ", ".join(f"{status}: {count}" for status, count in sorted(row["statuses"].items()))
        lines.append(f"| {row['result']} | {row['start']} | {row['race']} | {row['date']} | {row['targetCount']} | {statuses} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    workspace = Path(__file__).resolve().parents[3]
    config_path = arguments.config.resolve()
    config = load_json(config_path)
    review = review_results(workspace, config_path)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(markdown_report(config, review) + "\n", encoding="utf-8")
    print(json.dumps({"status": review.status, "errors": len(review.errors), "warnings": len(review.warnings), "output": str(arguments.output)}, ensure_ascii=False))
    return 2 if review.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
