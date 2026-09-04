"""Validate a prepared weekend and write a human-readable game-master report."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from storage_paths import resolve_path


@dataclass
class Review:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.errors:
            return "FEHLER"
        if self.warnings:
            return "WARNUNGEN"
        return "BEREIT"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_workspace_path(workspace: Path, value: str) -> Path:
    return resolve_path(workspace, value)


def distinctive_race_name(name: str) -> str:
    match = re.search(r"([\wÄÖÜäöüß]+-(?:Pokal|Cup)|[\wÄÖÜäöüß]+\s+Cup)", name, re.IGNORECASE)
    return match.group(1) if match else name.split(" - ", 1)[0]


def question_scope_is_clear(question: dict[str, Any], races_by_id: dict[str, dict[str, Any]], all_race_ids: set[str]) -> bool:
    race_ids = set(question.get("raceIds", []))
    combined = f"{question.get('prompt', '')} {question.get('hint', '')}".casefold()
    if race_ids == all_race_ids and ("wochenende" in combined or ("alle" in combined and "rennen" in combined)):
        return True
    for race_id in race_ids:
        race = races_by_id.get(race_id)
        if not race:
            return False
        day = str(race.get("day", "")).casefold()
        discipline = str(race.get("discipline", "")).casefold()
        race_reference = distinctive_race_name(str(race.get("name", ""))).casefold()
        if not day or day not in combined or not discipline or discipline not in combined or race_reference not in combined:
            return False
    return True


def review_weekend(workspace: Path, config_path: Path) -> tuple[Review, dict[str, Any] | None]:
    review = Review()
    config = load_json(config_path)
    start_lists = config.get("startLists", [])
    if not start_lists:
        review.errors.append("Keine Startlisten konfiguriert.")
    if not config.get("questionsFile"):
        review.errors.append("Keine Fragendatei konfiguriert.")

    for item in start_lists:
        source = resolve_workspace_path(workspace, item["pdf"])
        normalized = resolve_workspace_path(workspace, item["output"])
        if not source.is_file():
            review.errors.append(f"Startlisten-PDF fehlt: {item['pdf']}")
        if not normalized.is_file():
            review.errors.append(f"Normalisierte Startliste fehlt: {item['output']}")

    tip_round_path = resolve_workspace_path(workspace, config["tipRound"]["output"])
    if not tip_round_path.is_file():
        review.errors.append(f"Erzeugte Tipprunde fehlt: {config['tipRound']['output']}")
        return review, None

    tip_round = load_json(tip_round_path)
    races = tip_round.get("races", [])
    athletes = tip_round.get("athletes", [])
    questions = tip_round.get("questions", [])
    races_by_id = {race["id"]: race for race in races}
    athlete_ids = {athlete["id"] for athlete in athletes}
    all_race_ids = set(races_by_id)

    if not 6 <= len(questions) <= 10:
        review.errors.append(f"Die Tipprunde benötigt 6 bis 10 Fragen, gefunden: {len(questions)}.")
    if not races:
        review.errors.append("Die Tipprunde enthält keine Rennen.")
    if not athletes:
        review.errors.append("Keine Oberhachinger Starter erkannt.")

    question_ids = [question.get("id") for question in questions]
    if len(question_ids) != len(set(question_ids)):
        review.errors.append("Frage-IDs sind nicht eindeutig.")

    display_names: dict[str, int] = {}
    for athlete in athletes:
        display_names[athlete["displayName"]] = display_names.get(athlete["displayName"], 0) + 1
    duplicates = sorted(name for name, count in display_names.items() if count > 1)
    if duplicates:
        review.warnings.append(f"Doppeldeutige Anzeigenamen: {', '.join(duplicates)}")

    for index, question in enumerate(questions, 1):
        label = f"Frage {index} ({question.get('id', 'ohne ID')})"
        race_ids = set(question.get("raceIds", []))
        if not race_ids:
            review.errors.append(f"{label}: kein Rennen zugeordnet.")
        unknown_races = race_ids - all_race_ids
        if unknown_races:
            review.errors.append(f"{label}: unbekannte Rennen: {', '.join(sorted(unknown_races))}")
        referenced_athletes = set(question.get("athleteIds", []))
        if question.get("athleteId"):
            referenced_athletes.add(question["athleteId"])
        unknown_athletes = referenced_athletes - athlete_ids
        if unknown_athletes:
            review.errors.append(f"{label}: unbekannte Athleten: {', '.join(sorted(unknown_athletes))}")
        if not question_scope_is_clear(question, races_by_id, all_race_ids):
            review.errors.append(f"{label}: Tag, Rennen und Disziplin sind im Fragetext oder Hinweis nicht eindeutig.")
        if not question.get("raceLabel"):
            review.errors.append(f"{label}: sichtbare Rennzuordnung fehlt.")

    for item in start_lists:
        normalized = resolve_workspace_path(workspace, item["output"])
        if normalized.is_file():
            document = load_json(normalized)
            for warning in document.get("warnings", []):
                review.warnings.append(f"{normalized.name}: {warning}")

    if races:
        dates = sorted(datetime.fromisoformat(race["date"]).date() for race in races)
        if (dates[-1] - dates[0]).days > 3:
            review.errors.append("Die Rennen liegen mehr als drei Tage auseinander.")
        closes_at = datetime.fromisoformat(tip_round["closesAt"])
        if closes_at.weekday() != 5 or closes_at.hour != 0 or closes_at.minute != 0:
            review.errors.append("Der Abgabeschluss ist nicht Samstag um 00:00 Uhr.")
        if closes_at.date() > dates[0]:
            review.errors.append("Der Abgabeschluss liegt nach dem ersten Renntag.")

    results = config.get("results", [])
    if not results:
        review.notes.append("Ergebnislisten sind noch nicht konfiguriert. Das ist vor dem Rennwochenende normal.")
    submissions_dir = resolve_workspace_path(workspace, config["submissionsDir"])
    if not submissions_dir.is_dir():
        review.errors.append(f"Ordner für Tippabgaben fehlt: {config['submissionsDir']}")

    review.notes.append(f"{len(races)} Rennen, {len(start_lists)} Startlisten, {len(athletes)} Oberhachinger Starter und {len(questions)} Fragen geprüft.")
    return review, tip_round


def markdown_report(config: dict[str, Any], review: Review, tip_round: dict[str, Any] | None) -> str:
    lines = [
        f"# Prüfbericht {config['id']}",
        "",
        f"**Status: {review.status}**",
        "",
    ]
    for title, items, empty in (
        ("Fehler", review.errors, "Keine blockierenden Fehler."),
        ("Warnungen", review.warnings, "Keine Warnungen."),
        ("Hinweise", review.notes, "Keine Hinweise."),
    ):
        lines.extend([f"## {title}", ""])
        lines.extend([f"- {item}" for item in items] or [f"- {empty}"])
        lines.append("")

    if tip_round:
        lines.extend(["## Rennen", "", "| Tag | Datum | Rennen | Disziplin | Quelle |", "|---|---|---|---|---|"])
        for race in tip_round.get("races", []):
            lines.append(f"| {race.get('day', '')} | {race.get('date', '')} | {race.get('name', '')} | {race.get('discipline', '')} | {race.get('sourceFile', '')} |")
        lines.extend(["", "## Fragen", "", "| Nr. | Frage | Gültig für |", "|---:|---|---|"])
        for index, question in enumerate(tip_round.get("questions", []), 1):
            lines.append(f"| {index} | {question.get('prompt', '')} | {question.get('raceLabel', '')} |")
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
    review, tip_round = review_weekend(workspace, config_path)
    output = arguments.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown_report(config, review, tip_round) + "\n", encoding="utf-8")
    print(json.dumps({"status": review.status, "errors": len(review.errors), "warnings": len(review.warnings), "output": str(output)}, ensure_ascii=False))
    return 2 if review.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
