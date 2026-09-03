from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from storage_paths import resolve_path  # noqa: E402


class StoragePathTests(unittest.TestCase):
    def test_resolves_portable_external_reference(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_directory, tempfile.TemporaryDirectory() as storage_directory:
            workspace = Path(workspace_directory)
            settings = workspace / "config" / "local-storage.json"
            settings.parent.mkdir(parents=True)
            settings.write_text(json.dumps({"provider": "local-folder", "root": storage_directory}), encoding="utf-8")
            resolved = resolve_path(workspace, "storage://saisons/2026-2027/startliste.pdf")
            self.assertEqual(resolved, Path(storage_directory) / "saisons" / "2026-2027" / "startliste.pdf")

    def test_rejects_escape_from_external_storage(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_directory, tempfile.TemporaryDirectory() as storage_directory:
            workspace = Path(workspace_directory)
            settings = workspace / "config" / "local-storage.json"
            settings.parent.mkdir(parents=True)
            settings.write_text(json.dumps({"provider": "local-folder", "root": storage_directory}), encoding="utf-8")
            with self.assertRaises(ValueError):
                resolve_path(workspace, "storage://../außerhalb.pdf")


if __name__ == "__main__":
    unittest.main()
