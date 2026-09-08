"""Run a non-mutating quality gate across all configured race PDFs and evaluations."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from evaluate_submissions import build_weekend_evaluation
from extract_result_list import extract_result_list, summarize as summarize_result
from extract_start_list import extract_start_list, summarize as summarize_start
from storage_paths import resolve_path


VALID_STATUSES = {"CLASSIFIED", "DNS", "DNF", "DSQ"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def flattened(document: dict[str, Any], field: str) -> list[dict[str, Any]]:
    return [item for group in document.get("groups", []) for item in group.get(field, [])]


def duplicate_numbers(items: list[dict[str, Any]]) -> list[int]:
    counts = Counter(item.get("startNumber") for item in items)
    return sorted(number for number, count in counts.items() if number is not None and count > 1)


def validate_start(document: dict[str, Any], label: str, errors: list[str], warnings: list[str]) -> None:
    starters = flattened(document, "starters")
    duplicates = duplicate_numbers(starters)
    if duplicates:
        errors.append(f"{label}: Startnummern mehrfach vorhanden: {duplicates}")
    for group in document.get("groups", []):
        if not group.get("ageClass") or not group.get("competitionCategory"):
            errors.append(f"{label}: unvollständige Gruppendaten in {group.get('label', '?')}")
    for starter in starters:
        if not starter.get("fullName") or not starter.get("displayName") or not starter.get("birthYear"):
            errors.append(f"{label}: unvollständiger Starter bei Startnummer {starter.get('startNumber')}")
    if not document.get("event", {}).get("date"):
        warnings.append(f"{label}: Renndatum fehlt")
    for warning in document.get("warnings", []):
        warnings.append(f"{label}: {warning}")


def validate_result(
    document: dict[str, Any],
    start_document: dict[str, Any],
    label: str,
    errors: list[str],
    warnings: list[str],
) -> None:
    entries = flattened(document, "entries")
    duplicates = duplicate_numbers(entries)
    if duplicates:
        errors.append(f"{label}: Startnummern mehrfach vorhanden: {duplicates}")
    for entry in entries:
        status = entry.get("status")
        if status not in VALID_STATUSES:
            errors.append(f"{label}: ungültiger Status {status!r} bei Startnummer {entry.get('startNumber')}")
        if status == "CLASSIFIED":
            if not isinstance(entry.get("rank"), int) or entry["rank"] <= 0:
                errors.append(f"{label}: ungültiger Rang bei Startnummer {entry.get('startNumber')}")
            if not isinstance(entry.get("officialTimeSeconds"), (int, float)) or entry["officialTimeSeconds"] <= 0:
                errors.append(f"{label}: ungültige Gesamtzeit bei Startnummer {entry.get('startNumber')}")
            if entry.get("percentageGap", 0) < 0:
                errors.append(f"{label}: negativer prozentualer Rückstand bei Startnummer {entry.get('startNumber')}")

    starters = flattened(start_document, "starters")
    start_numbers = {item["startNumber"] for item in starters}
    result_numbers = {item["startNumber"] for item in entries}
    missing = sorted(start_numbers - result_numbers)
    extra = sorted(result_numbers - start_numbers)
    if missing:
        warnings.append(f"{label}: {len(missing)} Starter fehlen im Ergebnis: {missing[:12]}")
    if extra:
        warnings.append(f"{label}: {len(extra)} Nachmelder nur im Ergebnis: {extra[:12]}")
    target_starts = {item["startNumber"] for item in starters if item.get("targetClub")}
    target_results = {item["startNumber"] for item in entries if item.get("targetClub")}
    if target_starts - target_results:
        errors.append(f"{label}: Oberhachinger Starter fehlen: {sorted(target_starts - target_results)}")
    for warning in document.get("warnings", []):
        warnings.append(f"{label}: {warning}")


def evaluate_artifacts(
    workspace: Path,
    config: dict[str, Any],
    fresh_results: list[dict[str, Any]],
    errors: list[str],
    notes: list[str],
) -> None:
    if config.get("status") != "EVALUATED":
        return
    try:
        tip_round = load_json(resolve_path(workspace, config["tipRound"]["output"]))
        results = fresh_results
        if len(results) != len(config.get("results", [])):
            raise ValueError("nicht alle Ergebnis-PDFs konnten für den Ende-zu-Ende-Test frisch gelesen werden")
        submissions_directory = resolve_path(workspace, config["submissionsDir"])
        submissions = [load_json(path) for path in sorted(submissions_directory.glob("*.json"))]
        stored = load_json(resolve_path(workspace, config["weekendEvaluation"]["output"]))
        rebuilt = build_weekend_evaluation(tip_round, results, submissions, config["seasonId"])
        expected = [(item["rank"], item["playerId"], item["weekendPoints"]) for item in stored["standings"]]
        actual = [(item["rank"], item["playerId"], item["weekendPoints"]) for item in rebuilt["standings"]]
        if actual != expected:
            errors.append(f"{config['id']}: gespeicherte Wochenendwertung ist nicht reproduzierbar")
        else:
            notes.append(f"{config['id']}: Wertung mit {len(submissions)} Tippabgaben reproduziert")
    except Exception as error:  # quality report must continue with the remaining weekends
        errors.append(f"{config.get('id', '?')}: Wertungstest fehlgeschlagen: {error}")


def run(workspace: Path, config_directory: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []
    rows: list[dict[str, Any]] = []
    identities: dict[tuple[str, int], set[str]] = defaultdict(set)

    configs = [load_json(path) for path in sorted(config_directory.glob("tip-round-*.json"))]
    for config in configs:
        if not config.get("startLists") and not config.get("results"):
            notes.append(f"{config['id']}: leerer Entwurf übersprungen")
            continue
        starts_by_output: dict[str, dict[str, Any]] = {}
        fresh_results: list[dict[str, Any]] = []
        for item in config.get("startLists", []):
            source = resolve_path(workspace, item["pdf"])
            label = f"{config['id']} / {source.name}"
            if not source.is_file():
                errors.append(f"{label}: konfigurierte Startlisten-PDF fehlt")
                continue
            try:
                document = extract_start_list(source)
                starts_by_output[item["output"]] = document
                validate_start(document, label, errors, warnings)
                summary = summarize_start(document)
                rows.append({"weekend": config["id"], "type": "Start", **summary})
                for starter in flattened(document, "starters"):
                    if starter.get("targetClub") and starter.get("externalAthleteId"):
                        identities[(starter["fullName"].casefold(), starter["birthYear"])].add(str(starter["externalAthleteId"]))
            except Exception as error:
                errors.append(f"{label}: Import fehlgeschlagen: {error}")

        for item in config.get("results", []):
            source = resolve_path(workspace, item["pdf"])
            label = f"{config['id']} / {source.name}"
            if not source.is_file():
                errors.append(f"{label}: konfigurierte Ergebnislisten-PDF fehlt")
                continue
            start_document = starts_by_output.get(item["startList"])
            if start_document is None:
                normalized_start = resolve_path(workspace, item["startList"])
                if normalized_start.is_file():
                    start_document = load_json(normalized_start)
                    warnings.append(f"{label}: Ergebnis nur gegen vorhandenes Startlisten-JSON geprüft")
                else:
                    errors.append(f"{label}: zugeordnete Startliste fehlt")
                    continue
            try:
                document = extract_result_list(source, start_document)
                validate_result(document, start_document, label, errors, warnings)
                rows.append({"weekend": config["id"], "type": "Ergebnis", **summarize_result(document)})
                fresh_results.append(document)
            except Exception as error:
                errors.append(f"{label}: Import fehlgeschlagen: {error}")

        evaluate_artifacts(workspace, config, fresh_results, errors, notes)

    for (name, birth_year), external_ids in identities.items():
        if len(external_ids) > 1:
            errors.append(f"Athletenidentität {name} ({birth_year}) hat mehrere IDs: {sorted(external_ids)}")

    status = "FEHLER" if errors else "WARNUNGEN" if warnings else "BEREIT"
    return {"status": status, "configs": len(configs), "documents": rows, "errors": errors, "warnings": warnings, "notes": notes}


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Parser- und Workflow-Stresstest",
        "",
        f"**Status: {report['status']}**",
        "",
        f"Geprüfte Konfigurationen: {report['configs']}  ",
        f"Erfolgreich gelesene Dokumente: {len(report['documents'])}",
        "",
        "## Dokumente",
        "",
        "| Wochenende | Typ | Datei | Format | Gruppen | Datensätze | Oberhaching | Parserwarnungen |",
        "|---|---|---|---|---:|---:|---:|---:|",
    ]
    for item in report["documents"]:
        records = item.get("starters", item.get("entries", 0))
        target = item.get("targetClubStarters", item.get("targetClubEntries", 0))
        lines.append(
            f"| {item['weekend']} | {item['type']} | {item['file']} | {item['format']} | "
            f"{item['groups']} | {records} | {target} | {item['warnings']} |"
        )
    for heading, key, empty in (
        ("Fehler", "errors", "Keine Fehler."),
        ("Warnungen", "warnings", "Keine Warnungen."),
        ("Hinweise", "notes", "Keine Hinweise."),
    ):
        lines.extend(["", f"## {heading}", ""])
        lines.extend([f"- {value}" for value in report[key]] or [f"- {empty}"])
    lines.append("")
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, default=Path("config/weekends"))
    parser.add_argument("--output", type=Path, default=Path("output/reports/stress-test.md"))
    arguments = parser.parse_args(argv)
    workspace = Path(__file__).resolve().parents[3]
    report = run(workspace, resolve_path(workspace, str(arguments.config_dir)))
    output = resolve_path(workspace, str(arguments.output))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown(report), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "documents": len(report["documents"]),
        "errors": len(report["errors"]),
        "warnings": len(report["warnings"]),
        "output": str(output),
    }, ensure_ascii=False))
    return 2 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
