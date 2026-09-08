"""Initialize the configured database and import existing Ski Predictor JSON data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from database import Database, DatabaseError
from document_catalog import DocumentCatalog
from server import WORKSPACE, load_storage_root


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def import_existing(database: Database, catalog: DocumentCatalog) -> dict[str, int]:
    documents = catalog.documents()
    by_id = {document.document_id: document for document in documents}
    database.sync_documents(documents)
    extractions = 0
    approvals = 0
    missing_documents = 0
    jobs_root = WORKSPACE / "data" / "extractions" / "jobs"
    for job_path in sorted(jobs_root.glob("extract-*/job.json")):
        job = read_json(job_path)
        if job.get("status") not in {"REVIEW_REQUIRED", "APPROVED"}:
            continue
        document = by_id.get(job.get("documentId"))
        directory = job_path.parent
        if not document or not (directory / "raw.json").is_file() or not (directory / "normalized.json").is_file():
            missing_documents += 1
            continue
        raw = read_json(directory / "raw.json")
        normalized = read_json(directory / "normalized.json")
        review = job.get("review", {})
        from extract_start_list import extract_pdf_text
        _, source_text = extract_pdf_text(document.path)
        database.save_extraction(job, document, raw, normalized, review, source_text)
        extractions += 1
        if job["status"] == "APPROVED":
            database.approve_extraction(job, normalized)
            approvals += 1

    submissions = 0
    for path in sorted((WORKSPACE / "data" / "submissions" / "inbox").glob("**/*.json")):
        try:
            submission = read_json(path)
            if submission.get("id") and submission.get("tipRoundId") and submission.get("player"):
                database.save_submission(submission)
                submissions += 1
        except (OSError, json.JSONDecodeError, KeyError):
            continue
    return {
        "documents": len(documents),
        "extractions": extractions,
        "approved": approvals,
        "submissions": submissions,
        "skippedExtractions": missing_documents,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("migrate", "import-existing", "status"), nargs="?", default="status")
    arguments = parser.parse_args()
    try:
        database = Database.configured()
        if not database:
            raise DatabaseError("Keine Datenbank konfiguriert. config/database.local.json fehlt.")
        applied = database.migrate()
        result: dict[str, Any] = {"database": "available", "migrationsApplied": applied}
        if arguments.command == "import-existing":
            result["import"] = import_existing(database, DocumentCatalog(load_storage_root()))
        result["counts"] = database.counts()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (DatabaseError, OSError, ValueError) as error:
        print(f"Datenbankfehler: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
