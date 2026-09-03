"""Match result-list PDFs to normalized start lists using event metadata."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from extract_start_list import detect_format, event_metadata, extract_pdf_text
from storage_paths import storage_root


def normalized_text(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(re.findall(r"[a-z0-9]+", ascii_value.casefold()))


def normalized_discipline(value: str) -> str:
    token = normalized_text(value)
    if token in {"gs", "rs", "riesenslalom", "giant slalom"}:
        return "GS"
    if token in {"sl", "slalom"}:
        return "SL"
    return ""


def age_classes(value: str) -> set[str]:
    return {match.upper() for match in re.findall(r"\bU\d+\b", value, re.IGNORECASE)}


def candidate_score(result_event: dict[str, Any], start_event: dict[str, Any]) -> tuple[float, list[str]] | None:
    result_date = str(result_event.get("date", ""))
    start_date = str(start_event.get("date", ""))
    reasons: list[str] = []
    score = 0.0
    if result_date and start_date:
        if result_date != start_date:
            return None
        score += 60
        reasons.append("Datum stimmt überein")

    result_name = normalized_text(str(result_event.get("name", "")))
    start_name = normalized_text(str(start_event.get("name", "")))
    similarity = SequenceMatcher(None, result_name, start_name).ratio() if result_name and start_name else 0.0
    score += similarity * 30
    if similarity >= 0.75:
        reasons.append("Rennname stimmt weitgehend überein")

    result_discipline = normalized_discipline(str(result_event.get("discipline", "")))
    start_discipline = normalized_discipline(str(start_event.get("discipline", "")))
    if result_discipline and start_discipline:
        if result_discipline == start_discipline:
            score += 5
            reasons.append("Disziplin stimmt überein")
        else:
            score -= 10

    result_ages = age_classes(str(result_event.get("name", "")))
    start_ages = age_classes(str(start_event.get("name", "")))
    if result_ages and start_ages and result_ages & start_ages:
        score += 5
        reasons.append("Altersklasse stimmt überein")

    minimum = 65 if result_date and start_date else 20
    return (round(score, 2), reasons) if score >= minimum else None


def match_metadata(result_items: list[dict[str, Any]], start_items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    matches: list[dict[str, Any]] = []
    errors: list[str] = []
    used_start_paths: set[str] = set()
    for result in result_items:
        candidates: list[tuple[float, list[str], dict[str, Any]]] = []
        for start in start_items:
            scored = candidate_score(result["event"], start["event"])
            if scored:
                candidates.append((scored[0], scored[1], start))
        candidates.sort(key=lambda item: (-item[0], item[2]["path"]))
        if not candidates:
            errors.append(f"Keine passende Startliste für {Path(result['path']).name} gefunden.")
            continue
        if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < 5:
            errors.append(
                f"Zuordnung für {Path(result['path']).name} ist nicht eindeutig: "
                f"{Path(candidates[0][2]['path']).name} oder {Path(candidates[1][2]['path']).name}."
            )
            continue
        score, reasons, start = candidates[0]
        if start["path"] in used_start_paths:
            errors.append(f"Mehrere Ergebnislisten wurden {Path(start['path']).name} zugeordnet.")
            continue
        used_start_paths.add(start["path"])
        matches.append({"result": result["path"], "startList": start["path"], "score": score, "reasons": reasons})
    return matches, errors


def workspace_relative(workspace: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(workspace.resolve()).as_posix()
    except ValueError:
        try:
            return "storage://" + resolved.relative_to(storage_root(workspace).resolve()).as_posix()
        except ValueError as error:
            raise ValueError(f"Datei liegt außerhalb des Repositories und des Datenspeichers: {path}") from error


def markdown_report(matches: list[dict[str, Any]], errors: list[str]) -> str:
    status = "FEHLER" if errors else "BEREIT"
    lines = ["# Prüfbericht Ergebniszuordnung", "", f"**Status: {status}**", "", "## Fehler", ""]
    lines.extend([f"- {error}" for error in errors] or ["- Keine blockierenden Fehler."])
    lines.extend(["", "## Zuordnungen", "", "| Ergebnisliste | Startliste | Sicherheit | Grundlage |", "|---|---|---:|---|"])
    for item in matches:
        lines.append(
            f"| {Path(item['result']).name} | {Path(item['startList']).name} | {item['score']:.0f}/100 | {', '.join(item['reasons'])} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--start-lists", type=Path, nargs="+", required=True)
    parser.add_argument("--processed-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args(argv)
    workspace = Path(__file__).resolve().parents[3]

    result_items: list[dict[str, Any]] = []
    for pdf in sorted(arguments.results_dir.glob("*.pdf")):
        lines, text = extract_pdf_text(pdf)
        result_items.append({"path": workspace_relative(workspace, pdf), "event": event_metadata(lines, text), "format": detect_format(text)})
    start_items = []
    for path in arguments.start_lists:
        document = json.loads(path.read_text(encoding="utf-8"))
        start_items.append({"path": workspace_relative(workspace, path), "event": document["event"]})

    matches, errors = match_metadata(result_items, start_items)
    if not result_items:
        errors.append(f"Keine Ergebnis-PDFs in {arguments.results_dir} gefunden.")
    if len(matches) != len(start_items):
        unmatched = len(start_items) - len(matches)
        if unmatched > 0:
            errors.append(f"Für {unmatched} Startlisten fehlt eine eindeutige Ergebnisliste.")

    plan = []
    for item in matches:
        stem = Path(item["result"]).stem
        plan.append({
            "pdf": item["result"],
            "startList": item["startList"],
            "output": workspace_relative(workspace, arguments.processed_dir / f"result-{stem}.json"),
        })
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps({"matches": plan, "errors": errors}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(markdown_report(matches, errors) + "\n", encoding="utf-8")
    print(json.dumps({"status": "FEHLER" if errors else "BEREIT", "matches": len(matches), "errors": len(errors), "report": str(arguments.report)}, ensure_ascii=False))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
