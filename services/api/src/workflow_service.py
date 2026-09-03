"""Application service behind the local game-master API."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG_DIRECTORY = WORKSPACE / "config" / "weekends"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
STORAGE_PREFIX = "storage://"
WEEKEND_ID_PATTERN = re.compile(r"^tip-round-\d{4}-\d{2}-\d{2}$")
SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9ÄÖÜäöüß._() -]+")
ACTION_LOCK = threading.Lock()


class WorkflowError(RuntimeError):
    pass


@dataclass
class CommandResult:
    output: str
    return_code: int


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def external_storage_root() -> Path:
    settings = read_json(WORKSPACE / "config" / "local-storage.json")
    root = Path(str(settings.get("root", "")))
    if settings.get("provider") != "local-folder" or not root.is_absolute():
        raise WorkflowError("Die lokale Speichereinstellung ist ungültig.")
    return Path(os.path.abspath(root))


def resolve_path(value: str) -> Path:
    workspace = Path(os.path.abspath(WORKSPACE))
    if value.startswith(STORAGE_PREFIX):
        root, relative = external_storage_root(), value[len(STORAGE_PREFIX):]
    elif Path(value).is_absolute():
        candidate = Path(os.path.abspath(value))
        for root in (workspace, external_storage_root()):
            try:
                candidate.relative_to(root)
                return candidate
            except ValueError:
                continue
        raise WorkflowError("Der Pfad liegt außerhalb der erlaubten Speicherbereiche.")
    else:
        root, relative = workspace, value
    candidate = Path(os.path.abspath(root / relative))
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise WorkflowError("Der Pfad liegt außerhalb der erlaubten Speicherbereiche.") from error
    return candidate


def weekend_config_path(weekend_id: str) -> Path:
    if not WEEKEND_ID_PATTERN.fullmatch(weekend_id):
        raise WorkflowError("Ungültige Wochenend-ID.")
    path = CONFIG_DIRECTORY / f"{weekend_id}.json"
    if not path.is_file():
        raise WorkflowError("Das Rennwochenende wurde nicht gefunden.")
    return path


def report_summary(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    content = path.read_text(encoding="utf-8")
    status_match = re.search(r"\*\*Status: (BEREIT|WARNUNGEN|FEHLER)\*\*", content)
    sections: dict[str, list[str]] = {"errors": [], "warnings": [], "notes": []}
    headings = {"Fehler": "errors", "Warnungen": "warnings", "Hinweise": "notes"}
    current = None
    for line in content.splitlines():
        if line.startswith("## "):
            current = headings.get(line[3:].strip())
        elif current and line.startswith("- ") and not line[2:].startswith("Keine "):
            sections[current].append(line[2:].strip())
    return {"status": status_match.group(1) if status_match else "UNBEKANNT", "content": content, **sections}


def directory_files(path: Path, suffix: str) -> list[dict[str, Any]]:
    if not path.is_dir():
        return []
    return [{"name": item.name, "size": item.stat().st_size} for item in sorted(path.iterdir(), key=lambda entry: entry.name.casefold()) if item.is_file() and item.suffix.casefold() == suffix]


def configured_files(config: dict[str, Any], collection: str) -> list[dict[str, Any]]:
    files = []
    for item in config.get(collection, []):
        if item.get("pdf"):
            path = resolve_path(item["pdf"])
            if path.is_file():
                files.append({"name": path.name, "size": path.stat().st_size})
    return files


def weekend_state(path: Path) -> dict[str, Any]:
    config = read_json(path)
    status = str(config.get("status", "DRAFT"))
    date = config["id"].removeprefix("tip-round-")
    start_directory = resolve_path(config.get("startListsDirectory", f"data/result-lists/inbox/weekend-{date}/start-lists"))
    result_directory = resolve_path(config.get("resultsDirectory", f"data/result-lists/inbox/weekend-{date}/results"))
    question_path = resolve_path(config["questionsFile"])
    starts = directory_files(start_directory, ".pdf") or configured_files(config, "startLists")
    results = directory_files(result_directory, ".pdf") or configured_files(config, "results")
    submissions = directory_files(resolve_path(config["submissionsDir"]), ".json")
    preparation = report_summary(resolve_path(config.get("reviewReport", f"output/reports/review-{config['id']}.md")))
    result_report = report_summary(resolve_path(config.get("resultReviewReport", f"output/reports/results-{config['id']}.md")))
    actions = {
        "prepare": status == "DRAFT" and bool(starts) and question_path.is_file(),
        "open": status == "DRAFT" and preparation is not None and preparation["status"] == "BEREIT",
        "close": status == "OPEN",
        "evaluate": status == "CLOSED" and bool(results) and bool(submissions),
        "archive": status in {"EVALUATED", "CANCELLED"},
        "cancel": status in {"DRAFT", "OPEN", "CLOSED"},
    }
    return {
        "id": config["id"], "title": config.get("tipRound", {}).get("title", config["id"]),
        "seasonId": config.get("seasonId"), "status": status, "testMode": bool(config.get("tipRound", {}).get("testMode")),
        "storageRoot": str(external_storage_root()) if str(config.get("startListsDirectory", "")).startswith(STORAGE_PREFIX) else None,
        "questions": question_path.read_text(encoding="utf-8") if question_path.is_file() else "",
        "files": {"startLists": starts, "results": results, "submissions": submissions},
        "reports": {"preparation": preparation, "results": result_report}, "actions": actions,
    }


def all_weekends() -> list[dict[str, Any]]:
    weekends = []
    for path in sorted(CONFIG_DIRECTORY.glob("tip-round-????-??-??.json"), reverse=True):
        try:
            weekends.append(weekend_state(path))
        except (KeyError, OSError, ValueError, json.JSONDecodeError, WorkflowError) as error:
            weekends.append({"id": path.stem, "title": path.stem, "status": "FEHLER", "loadError": str(error)})
    return weekends


def run_script(name: str, arguments: list[str]) -> CommandResult:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if not executable:
        raise WorkflowError("PowerShell wurde nicht gefunden.")
    process = subprocess.run([executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(WORKSPACE / "scripts" / "game-master" / name), *arguments], cwd=WORKSPACE, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, check=False)
    output = "\n".join(part.strip() for part in (process.stdout, process.stderr) if part.strip())
    if process.returncode:
        raise WorkflowError(output or f"{name} ist fehlgeschlagen.")
    return CommandResult(output, process.returncode)


def create_weekend(payload: dict[str, Any]) -> dict[str, Any]:
    date, title = str(payload.get("date", "")).strip(), str(payload.get("title", "")).strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) or not 3 <= len(title) <= 100:
        raise WorkflowError("Datum oder Name des Rennwochenendes ist ungültig.")
    arguments = ["-WeekendDate", date, "-Title", title]
    if not payload.get("testMode"):
        arguments.append("-ProductionMode")
    result = run_script("New-Weekend.ps1", arguments)
    return {"message": "Das Rennwochenende wurde angelegt.", "log": result.output, "weekend": weekend_state(weekend_config_path(f"tip-round-{date}"))}


def save_questions(weekend_id: str, content: str) -> dict[str, Any]:
    path = weekend_config_path(weekend_id)
    config = read_json(path)
    if config.get("status", "DRAFT") != "DRAFT" or len(content.strip()) < 20:
        raise WorkflowError("Fragen können nur als vollständiger Entwurf gespeichert werden.")
    question_path = resolve_path(config["questionsFile"])
    question_path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return {"message": "Fragen gespeichert.", "weekend": weekend_state(path)}


def safe_filename(name: str, suffix: str) -> str:
    cleaned = SAFE_FILENAME_PATTERN.sub("_", Path(urllib.parse.unquote(name)).name.strip())
    if not cleaned or Path(cleaned).suffix.casefold() != suffix:
        raise WorkflowError(f"Erlaubt sind nur {suffix}-Dateien.")
    return cleaned


def upload_file(weekend_id: str, category: str, filename: str, content: bytes) -> dict[str, Any]:
    path = weekend_config_path(weekend_id)
    config = read_json(path)
    date = config["id"].removeprefix("tip-round-")
    settings = {
        "start-lists": (config.get("startListsDirectory", f"data/result-lists/inbox/weekend-{date}/start-lists"), ".pdf", {"DRAFT"}),
        "results": (config.get("resultsDirectory", f"data/result-lists/inbox/weekend-{date}/results"), ".pdf", {"CLOSED"}),
        "submissions": (config["submissionsDir"], ".json", {"OPEN", "CLOSED"}),
    }
    if category not in settings:
        raise WorkflowError("Unbekannte Dateiart.")
    directory, suffix, statuses = settings[category]
    if config.get("status", "DRAFT") not in statuses or not content or len(content) > MAX_UPLOAD_BYTES:
        raise WorkflowError("Die Datei kann im aktuellen Zustand nicht abgelegt werden.")
    destination = resolve_path(directory) / safe_filename(filename, suffix)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise WorkflowError(f"Die Datei {destination.name} ist bereits vorhanden.")
    destination.write_bytes(content)
    return {"message": f"{destination.name} wurde abgelegt.", "weekend": weekend_state(path)}


def perform_action(weekend_id: str, action: str) -> dict[str, Any]:
    if not ACTION_LOCK.acquire(blocking=False):
        raise WorkflowError("Es läuft bereits eine automatische Verarbeitung.")
    try:
        path, state = weekend_config_path(weekend_id), weekend_state(weekend_config_path(weekend_id))
        if not state["actions"].get(action):
            raise WorkflowError("Diese Aktion ist im aktuellen Zustand nicht möglich.")
        config_reference = path.relative_to(WORKSPACE).as_posix()
        if action == "prepare":
            result, message = run_script("Prepare-Weekend.ps1", ["-Config", config_reference]), "Startlisten und Fragen wurden verarbeitet und geprüft."
        elif action == "evaluate":
            result, message = run_script("Evaluate-Weekend.ps1", ["-Config", config_reference]), "Ergebnisse und Tipps wurden geprüft und ausgewertet."
        else:
            target = {"open": "OPEN", "close": "CLOSED", "archive": "ARCHIVED", "cancel": "CANCELLED"}[action]
            result, message = run_script("Set-WeekendStatus.ps1", ["-Config", config_reference, "-Status", target]), f"Der Status wurde auf {target} gesetzt."
        return {"message": message, "log": result.output, "weekend": weekend_state(path)}
    finally:
        ACTION_LOCK.release()


def close_expired_weekends() -> None:
    for path in CONFIG_DIRECTORY.glob("tip-round-????-??-??.json"):
        try:
            config = read_json(path)
            if config.get("status") != "OPEN" or config.get("tipRound", {}).get("testMode"):
                continue
            deadline = datetime.fromisoformat(read_json(resolve_path(config["tipRound"]["output"]))["closesAt"])
            now = datetime.now(deadline.tzinfo) if deadline.tzinfo else datetime.now()
            if now >= deadline:
                run_script("Set-WeekendStatus.ps1", ["-Config", path.relative_to(WORKSPACE).as_posix(), "-Status", "CLOSED"])
        except (WorkflowError, KeyError, OSError, ValueError, json.JSONDecodeError):
            continue
