"""Apply a validated lifecycle transition to a weekend and its website data."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from storage_paths import resolve_path


TRANSITIONS = {
    "DRAFT": {"OPEN", "CANCELLED"},
    "OPEN": {"CLOSED", "CANCELLED"},
    "CLOSED": {"EVALUATED", "CANCELLED"},
    "EVALUATED": {"ARCHIVED"},
    "ARCHIVED": set(),
    "CANCELLED": {"ARCHIVED"},
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def report_is_ready(path: Path) -> bool:
    return path.is_file() and "**Status: BEREIT**" in path.read_text(encoding="utf-8")


def change_status(
    workspace: Path,
    config_path: Path,
    target_status: str,
    changed_at: datetime | None = None,
) -> dict[str, Any]:
    config = load_json(config_path)
    current = str(config.get("status", "DRAFT")).upper()
    target = target_status.upper()
    if target not in TRANSITIONS:
        raise ValueError(f"Unbekannter Wochenendstatus: {target}")
    if current == target:
        return config
    if target not in TRANSITIONS.get(current, set()):
        raise ValueError(f"Ungültiger Statuswechsel: {current} -> {target}")

    if target == "OPEN":
        report_path = resolve_path(workspace, config.get("reviewReport", f"output/reports/review-{config['id']}.md"))
        if not report_is_ready(report_path):
            raise ValueError("Die Tipprunde kann nur mit einem bereiten Fragen-Prüfbericht geöffnet werden.")
    if target == "EVALUATED":
        report_path = resolve_path(workspace, config.get("resultReviewReport", f"output/reports/results-{config['id']}.md"))
        evaluation_path = resolve_path(workspace, config["weekendEvaluation"]["output"])
        if not report_is_ready(report_path) or not evaluation_path.is_file():
            raise ValueError("Die Tipprunde kann erst nach erfolgreicher Ergebnisprüfung und Auswertung abgeschlossen werden.")

    artifact_paths = [
        resolve_path(workspace, config["tipRound"]["output"]),
        resolve_path(workspace, config["tipRound"]["websiteOutput"]),
    ]
    missing = [str(path) for path in artifact_paths if not path.is_file()]
    if missing:
        raise ValueError(f"Tipprunden-Datei fehlt: {missing[0]}")

    artifacts = [load_json(path) for path in artifact_paths]
    versions = {artifact.get("contentVersion") for artifact in artifacts}
    if None in versions or len(versions) != 1:
        raise ValueError("Die Tipprunden-Dateien haben keine eindeutige Inhaltsversion.")

    timestamp = (changed_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    config["status"] = target
    config.setdefault("statusHistory", []).append({"status": target, "changedAt": timestamp})
    for artifact_path, artifact in zip(artifact_paths, artifacts):
        artifact["status"] = target
        write_json(artifact_path, artifact)
    write_json(config_path, config)
    return config


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("status", choices=sorted(TRANSITIONS))
    arguments = parser.parse_args(argv)
    workspace = Path(__file__).resolve().parents[3]
    config = change_status(workspace, arguments.config.resolve(), arguments.status)
    print(json.dumps({"id": config["id"], "status": config["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
