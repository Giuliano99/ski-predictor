"""Resolve portable repository and external storage references."""

from __future__ import annotations

import json
import os
from pathlib import Path


STORAGE_PREFIX = "storage://"


def _contained_path(root: Path, relative: str, label: str) -> Path:
    normalized_root = Path(os.path.abspath(root))
    candidate = Path(os.path.abspath(normalized_root / relative))
    try:
        candidate.relative_to(normalized_root)
    except ValueError as error:
        raise ValueError(f"Pfad liegt außerhalb von {label}: {relative}") from error
    return candidate


def storage_root(workspace: Path) -> Path:
    settings_path = workspace / "config" / "local-storage.json"
    if not settings_path.is_file():
        raise ValueError(
            "Der externe Datenspeicher ist nicht eingerichtet. "
            "Kopiere config/local-storage.example.json nach config/local-storage.json und trage den Ordner ein."
        )
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    root_value = str(settings.get("root", "")).strip()
    if settings.get("provider") != "local-folder" or not root_value:
        raise ValueError("config/local-storage.json enthält keine gültige local-folder-Konfiguration.")
    root = Path(root_value)
    if not root.is_absolute():
        raise ValueError("Der externe Datenordner muss als absoluter Pfad angegeben werden.")
    return Path(os.path.abspath(root))


def resolve_path(workspace: Path, value: str) -> Path:
    if value.startswith(STORAGE_PREFIX):
        return _contained_path(storage_root(workspace), value[len(STORAGE_PREFIX):], "des externen Datenspeichers")
    path = Path(value)
    if path.is_absolute():
        candidate = Path(os.path.abspath(path))
        for root in (Path(os.path.abspath(workspace)), storage_root(workspace)):
            try:
                candidate.relative_to(root)
                return candidate
            except ValueError:
                continue
        raise ValueError(f"Absoluter Pfad ist weder Projekt noch Datenspeicher: {value}")
    return _contained_path(workspace, value, "des Repositories")
