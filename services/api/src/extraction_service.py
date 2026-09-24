"""Persistent asynchronous PDF extraction and reusable race-data projections."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from athlete_identity import AthleteIdentityError, AthleteIdentityRegistry
from database import Database
from document_catalog import Document, DocumentCatalog
from dsv_points import MAXIMUM_START_POINTS, adjusted_season_base, round_points, season_projection


WORKSPACE = Path(__file__).resolve().parents[3]
IMPORTER_SOURCE = WORKSPACE / "services" / "results-importer" / "src"
if str(IMPORTER_SOURCE) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SOURCE))

from extract_result_list import extract_result_list  # noqa: E402
from extract_start_list import extract_pdf_text, extract_start_list, slugify  # noqa: E402
from extract_dsv_snapshot import extract as extract_dsv_snapshot  # noqa: E402


EXTRACTION_VERSION = "ski-predictor-extractor-v5.6-season-bases"
JOB_STATUSES = {"PENDING", "PROCESSING", "REVIEW_REQUIRED", "APPROVED", "SUPERSEDED", "FAILED"}


class ExtractionError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def stable_id(prefix: str, value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(encoded).hexdigest()[:16]}"


class ExtractionService:
    def __init__(self, catalog: DocumentCatalog, data_directory: Path | None = None, database: Database | None = None):
        self.catalog = catalog
        self.database = database
        self.data_directory = (data_directory or WORKSPACE / "data" / "extractions").resolve()
        self.jobs_directory = self.data_directory / "jobs"
        self.identities = AthleteIdentityRegistry(self.data_directory / "athletes.json")
        self._lock = threading.RLock()

    def _job_directory(self, job_id: str) -> Path:
        if not re.fullmatch(r"extract-[a-f0-9]{32}", job_id):
            raise ExtractionError("Ungültige Extraktions-ID.")
        return self.jobs_directory / job_id

    def _job_path(self, job_id: str) -> Path:
        return self._job_directory(job_id) / "job.json"

    def _read_job(self, job_id: str) -> dict[str, Any]:
        path = self._job_path(job_id)
        if not path.is_file():
            raise ExtractionError("Der Extraktionsauftrag wurde nicht gefunden.")
        for attempt in range(4):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (PermissionError, json.JSONDecodeError):
                if attempt == 3:
                    raise
                time.sleep(0.01)
        raise ExtractionError("Der Extraktionsauftrag konnte nicht gelesen werden.")

    def _write_job(self, job: dict[str, Any]) -> None:
        job["updatedAt"] = utc_now()
        atomic_json(self._job_path(job["jobId"]), job)

    def _all_jobs(self) -> list[dict[str, Any]]:
        if not self.jobs_directory.is_dir():
            return []
        jobs = []
        for path in self.jobs_directory.glob("extract-*/job.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                if job.get("status") in JOB_STATUSES:
                    jobs.append(job)
            except (OSError, json.JSONDecodeError):
                continue
        return sorted(jobs, key=lambda item: item.get("createdAt", ""), reverse=True)

    def public_job(self, job: dict[str, Any]) -> dict[str, Any]:
        job_id = job["jobId"]
        return {
            key: value for key, value in job.items()
            if key not in {"options"}
        } | {
            "links": {
                "self": f"/api/v1/extraction-jobs/{job_id}",
                "extraction": f"/api/v1/documents/{job['documentId']}/extraction",
                "approve": f"/api/v1/extraction-jobs/{job_id}/approve",
            }
        }

    def jobs(self, weekend_date: str | None = None) -> list[dict[str, Any]]:
        jobs = self._all_jobs()
        if weekend_date:
            jobs = [job for job in jobs if job.get("weekendDate") == weekend_date]
        return [self.public_job(job) for job in jobs]

    def job(self, job_id: str) -> dict[str, Any]:
        return self.public_job(self._read_job(job_id))

    def start(self, document_id: str, options: dict[str, Any] | None = None) -> tuple[dict[str, Any], bool]:
        options = options or {}
        document = self.catalog.find(document_id)
        if not document:
            raise ExtractionError("Das Dokument wurde nicht gefunden.")
        if document.kind not in {"START_LIST", "RESULT_LIST", "DSV_RANKING", "DSV_RACE_COUNT"}:
            raise ExtractionError("Der Dokumenttyp kann noch nicht automatisch extrahiert werden.")
        force = options.get("force") is True
        if not force:
            existing = next((job for job in self._all_jobs() if job.get("documentId") == document_id and job.get("sourceContentHash") == f"sha256-{document.content_hash}" and job.get("extractionVersion") == EXTRACTION_VERSION and job.get("status") != "FAILED"), None)
            if existing:
                return self.public_job(existing), False

        job_id = f"extract-{uuid.uuid4().hex}"
        created_at = utc_now()
        job = {
            "schemaVersion": 1,
            "jobId": job_id,
            "documentId": document_id,
            "documentKind": document.kind,
            "sourceContentHash": f"sha256-{document.content_hash}",
            "sourceName": document.original_name,
            "seasonId": document.season_id,
            "weekendDate": document.weekend_date,
            "extractionVersion": EXTRACTION_VERSION,
            "status": "PENDING",
            "createdAt": created_at,
            "updatedAt": created_at,
            "options": {"startListDocumentId": options.get("startListDocumentId")},
        }
        with self._lock:
            self._write_job(job)
        threading.Thread(target=self.process, args=(job_id,), daemon=True, name=job_id).start()
        return self.public_job(job), True

    def start_weekend(self, weekend_date: str) -> list[dict[str, Any]]:
        documents = self.catalog.query(weekend_date=weekend_date, archived=False)
        jobs = []
        for document in sorted(documents, key=lambda item: item.kind != "START_LIST"):
            if document.kind not in {"START_LIST", "RESULT_LIST"}:
                continue
            job, _ = self.start(document.document_id)
            jobs.append(job)
        return jobs

    def start_season_results(self, season_id: str) -> list[dict[str, Any]]:
        documents = [
            document for document in self.catalog.query(kind="RESULT_LIST", season_id=season_id, archived=False)
            if document.weekend_date is None
        ]
        selected: dict[str, Document] = {}
        for document in documents:
            selected.setdefault(document.content_hash, document)
        jobs = []
        for document in sorted(selected.values(), key=lambda item: item.original_name.casefold()):
            job, _ = self.start(document.document_id)
            jobs.append(job)
        return jobs

    def _restart_weekend_results(self, weekend_date: str) -> None:
        for document in self.catalog.query(weekend_date=weekend_date, archived=False):
            if document.kind == "RESULT_LIST":
                self.start(document.document_id, {"force": True})

    def _approved_start_list(self, document_id: str | None) -> dict[str, Any] | None:
        if not document_id:
            return None
        job = next((item for item in self._all_jobs() if item.get("documentId") == document_id and item.get("documentKind") == "START_LIST" and item.get("status") == "APPROVED"), None)
        if not job:
            raise ExtractionError("Die zugehörige Startliste muss zuerst extrahiert und freigegeben werden.")
        return json.loads((self._job_directory(job["jobId"]) / "raw.json").read_text(encoding="utf-8"))

    def _approved_start_candidates(self, weekend_date: str | None) -> list[dict[str, Any]]:
        candidates = []
        for job in self._all_jobs():
            if job.get("documentKind") != "START_LIST" or job.get("status") != "APPROVED" or job.get("weekendDate") != weekend_date:
                continue
            try:
                candidates.append(json.loads((self._job_directory(job["jobId"]) / "raw.json").read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return candidates

    def _extract_result(self, document: Document, job: dict[str, Any]) -> dict[str, Any]:
        selected_id = job.get("options", {}).get("startListDocumentId")
        if selected_id:
            return extract_result_list(document.path, self._approved_start_list(selected_id))
        try:
            return extract_result_list(document.path)
        except ValueError as initial_error:
            if "require --start-list" not in str(initial_error):
                raise
        candidates = self._approved_start_candidates(job.get("weekendDate"))
        if not candidates:
            raise ExtractionError("Diese Ergebnisliste benötigt eine freigegebene Startliste desselben Wochenendes.")
        extracted_candidates = []
        for candidate in candidates:
            try:
                extracted = extract_result_list(document.path, candidate)
                extracted_candidates.append((len(extracted.get("warnings", [])), extracted))
            except ValueError:
                continue
        if not extracted_candidates:
            raise ExtractionError("Keine freigegebene Startliste konnte der Ergebnisliste zugeordnet werden.")
        extracted_candidates.sort(key=lambda item: item[0])
        best_score, best = extracted_candidates[0]
        if len(extracted_candidates) > 1 and extracted_candidates[1][0] == best_score:
            best.setdefault("warnings", []).append("Mehrere Startlisten passten gleich gut. Bitte die automatische Zuordnung besonders prüfen.")
        return best

    def _assign_identities(self, groups: list[dict[str, Any]], participant_key: str) -> tuple[dict[str, int], list[str]]:
        identity_counts: dict[str, int] = {}
        identity_warnings: list[str] = []
        for group in groups:
            for person in group.get(participant_key, []):
                identity = self.identities.resolve(person)
                person["athleteId"] = identity["athleteId"]
                person["identityMatch"] = identity["match"]
                person["identityConfidence"] = identity["confidence"]
                identity_counts[identity["match"]] = identity_counts.get(identity["match"], 0) + 1
                if identity.get("warning"):
                    identity_warnings.append(identity["warning"])
        return identity_counts, identity_warnings

    @staticmethod
    def _snapshot_people(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [person for section in sections for person in section.get("entries", [])]

    def _normalize_snapshot(self, document: Document, extracted: dict[str, Any]) -> dict[str, Any]:
        sections = json.loads(json.dumps(extracted.get("sections", []), ensure_ascii=False))
        for person in self._snapshot_people(sections):
            person["fullName"] = f"{person.get('firstName', '')} {person.get('lastName', '')}".strip()
            last_name = str(person.get("lastName", "")).strip()
            person["displayName"] = f"{person.get('firstName', '')} {last_name[:1]}.".strip()
            person["targetClub"] = str(person.get("club", "")).casefold() == "skiteam oberhaching"
        identity_counts, identity_warnings = self._assign_identities(sections, "entries")
        snapshot = dict(extracted["snapshot"])
        if document.season_id and snapshot.get("seasonId") != document.season_id:
            snapshot["sourceSeasonId"] = snapshot.get("sourceSeasonId") or snapshot.get("seasonId")
            snapshot["seasonId"] = document.season_id
        source = {key: value for key, value in extracted.get("source", {}).items() if key != "rawText"}
        if source.get("format") == "DSV_CLUB_END_LIST_PDF" and snapshot.get("snapshotKind") == "SEASON_START_BASE":
            for section in sections:
                gender = section.get("gender")
                for person in section.get("entries", []):
                    previous_end_points = float(person["listPoints"])
                    adjusted, correction = adjusted_season_base(previous_end_points, snapshot["seasonId"], gender)
                    person.update({
                        "previousEndListPoints": round_points(previous_end_points),
                        "seasonCorrectionPoints": correction,
                        "basePoints": adjusted,
                        "listPoints": adjusted,
                    })
            snapshot["baseDerivation"] = "PREVIOUS_END_LIST_PLUS_SEASON_CORRECTION"
        timestamp = snapshot.get("publishedAt") or snapshot.get("observedAt")
        snapshot_id = stable_id("dsv-snapshot", {
            "type": extracted["documentType"],
            "documentId": snapshot.get("documentId"),
            "timestamp": timestamp,
        })
        normalized = {
            "schemaVersion": 1,
            "extractionVersion": EXTRACTION_VERSION,
            "documentId": document.document_id,
            "documentType": extracted["documentType"],
            "source": source,
            "snapshot": {"id": snapshot_id, **snapshot},
            "coverage": extracted.get("coverage"),
            "sections": sections,
            "statistics": {**extracted.get("statistics", {}), "identities": identity_counts},
            "warnings": list(dict.fromkeys([*extracted.get("warnings", []), *identity_warnings])),
        }
        if extracted.get("pointsCalculations"):
            normalized["pointsCalculations"] = extracted["pointsCalculations"]
        if extracted.get("pointsNormalization"):
            normalized["pointsNormalization"] = extracted["pointsNormalization"]
        return normalized

    def _normalize(self, document: Document, extracted: dict[str, Any]) -> dict[str, Any]:
        if extracted["documentType"] in {"DSV_RANKING", "DSV_RACE_COUNT"}:
            return self._normalize_snapshot(document, extracted)
        event = dict(extracted.get("event", {}))
        event_id = stable_id("event", {key: event.get(key) for key in ("name", "date", "location")})
        if extracted["documentType"] == "START_LIST":
            race_id = f"race-{slugify(event.get('competitionNumber') or Path(extracted['source']['fileName']).stem)}"
            participants_key = "starters"
        else:
            race_id = extracted["raceId"]
            participants_key = "entries"
        groups = json.loads(json.dumps(extracted.get("groups", []), ensure_ascii=False))
        identity_counts, identity_warnings = self._assign_identities(groups, participants_key)
        participant_count = sum(len(group.get(participants_key, [])) for group in groups)
        target_count = sum(1 for group in groups for item in group.get(participants_key, []) if item.get("targetClub"))
        normalized = {
            "schemaVersion": 1,
            "extractionVersion": EXTRACTION_VERSION,
            "documentId": document.document_id,
            "documentType": extracted["documentType"],
            "event": {"id": event_id, **event},
            "race": {
                "id": race_id,
                "eventId": event_id,
                "name": event.get("name", "Unbekanntes Rennen"),
                "date": event.get("date"),
                "location": event.get("location"),
                "discipline": event.get("discipline", "OTHER"),
                "competitionNumber": event.get("competitionNumber"),
                "sourceDocumentId": document.document_id,
            },
            "groups": groups,
            "statistics": {"groups": len(groups), "participants": participant_count, "targetClubParticipants": target_count, "identities": identity_counts},
            "warnings": list(dict.fromkeys([*extracted.get("warnings", []), *identity_warnings])),
        }
        if extracted.get("pointsCalculations"):
            normalized["pointsCalculations"] = extracted["pointsCalculations"]
        if extracted.get("pointsNormalization"):
            normalized["pointsNormalization"] = extracted["pointsNormalization"]
        return normalized

    def _review(self, normalized: dict[str, Any]) -> dict[str, Any]:
        warnings = list(normalized.get("warnings", []))
        if normalized["documentType"] in {"DSV_RANKING", "DSV_RACE_COUNT"}:
            if not normalized.get("snapshot", {}).get("seasonId"):
                warnings.append("Die Saison des DSV-Snapshots wurde nicht erkannt.")
            if not normalized.get("statistics", {}).get("entries"):
                raise ExtractionError("Es wurden keine DSV-Snapshot-Einträge erkannt.")
            return {
                "status": "WARNUNGEN" if warnings else "BEREIT",
                "warnings": list(dict.fromkeys(warnings)),
                "statistics": normalized["statistics"],
            }
        event = normalized["event"]
        if not event.get("date"):
            warnings.append("Das Veranstaltungsdatum wurde nicht erkannt.")
        if event.get("name") == "Unbekannte Veranstaltung":
            warnings.append("Der Veranstaltungsname wurde nicht erkannt.")
        if not normalized["statistics"]["participants"]:
            raise ExtractionError("Es wurden keine Teilnehmer erkannt.")
        return {
            "status": "WARNUNGEN" if warnings else "BEREIT",
            "warnings": list(dict.fromkeys(warnings)),
            "statistics": normalized["statistics"],
        }

    def _report_markdown(self, job: dict[str, Any], review: dict[str, Any], normalized: dict[str, Any]) -> str:
        warnings = review["warnings"]
        if normalized["documentType"] in {"DSV_RANKING", "DSV_RACE_COUNT"}:
            snapshot = normalized["snapshot"]
            timestamp = snapshot.get("publishedAt") or snapshot.get("observedAt")
            return "\n".join([
                f"# Extraktionsbericht: {job['sourceName']}", "",
                f"**Status: {review['status']}**", "",
                f"- Dokument: `{job['documentId']}`",
                f"- Typ: `{job['documentKind']}`",
                f"- DSV-Dokumentkennung: `{snapshot.get('documentId')}`",
                f"- Saison: `{snapshot.get('seasonId')}`",
                f"- Stichtag: `{timestamp}`",
                f"- Abschnitte: {review['statistics']['sections']}",
                f"- Einträge: {review['statistics']['entries']}",
                f"- Eindeutige Athleten: {review['statistics']['uniqueAthletes']}",
                f"- Skiteam Oberhaching: {review['statistics']['targetClubUniqueAthletes']}", "",
                "## Athletenidentität", "",
                *[f"- {key}: {value}" for key, value in sorted(review["statistics"].get("identities", {}).items())], "",
                "## Warnungen", "",
                *([f"- {warning}" for warning in warnings] if warnings else ["- Keine Warnungen."]), "",
                "Die Daten werden erst nach der Bestätigung in die Athletenauswertung übernommen.", "",
            ])
        return "\n".join([
            f"# Extraktionsbericht: {job['sourceName']}", "",
            f"**Status: {review['status']}**", "",
            f"- Dokument: `{job['documentId']}`",
            f"- Typ: `{job['documentKind']}`",
            f"- Veranstaltung: {normalized['event'].get('name', 'Unbekannt')}",
            f"- Rennen: `{normalized['race']['id']}`",
            f"- Gruppen: {review['statistics']['groups']}",
            f"- Teilnehmer: {review['statistics']['participants']}",
            f"- Skiteam Oberhaching: {review['statistics']['targetClubParticipants']}", "",
            "## Athletenidentität", "",
            *[f"- {key}: {value}" for key, value in sorted(review["statistics"].get("identities", {}).items())], "",
            "## Warnungen", "",
            *([f"- {warning}" for warning in warnings] if warnings else ["- Keine Warnungen."]), "",
            "Die Daten werden erst nach der Bestätigung durch den Spielleiter in den allgemeinen Rennendpunkten veröffentlicht.", "",
        ])

    def process(self, job_id: str) -> None:
        try:
            with self._lock:
                job = self._read_job(job_id)
                job["status"] = "PROCESSING"
                job["startedAt"] = utc_now()
                self._write_job(job)
            document = self.catalog.find(job["documentId"])
            if not document or f"sha256-{document.content_hash}" != job["sourceContentHash"]:
                raise ExtractionError("Das Quelldokument wurde seit Auftragserstellung verändert oder entfernt.")
            if document.kind == "START_LIST":
                extracted = extract_start_list(document.path)
            elif document.kind == "RESULT_LIST":
                extracted = self._extract_result(document, job)
            else:
                extracted = extract_dsv_snapshot(document.path, document.kind, "Skiteam Oberhaching")
            normalized = self._normalize(document, extracted)
            review = self._review(normalized)
            directory = self._job_directory(job_id)
            atomic_json(directory / "raw.json", extracted)
            atomic_json(directory / "normalized.json", normalized)
            (directory / "report.md").write_text(self._report_markdown(job, review, normalized), encoding="utf-8")
            if self.database:
                source_text = extracted.get("rawText")
                if source_text is None:
                    _, source_text = extract_pdf_text(document.path)
                self.database.save_extraction(job, document, extracted, normalized, review, source_text)
            with self._lock:
                job = self._read_job(job_id)
                identifiers = {}
                if normalized["documentType"] in {"DSV_RANKING", "DSV_RACE_COUNT"}:
                    identifiers["snapshotId"] = normalized["snapshot"]["id"]
                else:
                    identifiers.update(raceId=normalized["race"]["id"], eventId=normalized["event"]["id"])
                job.update({"status": "REVIEW_REQUIRED", "completedAt": utc_now(), "review": review, **identifiers})
                self._write_job(job)
        except Exception as error:
            with self._lock:
                try:
                    job = self._read_job(job_id)
                    job.update({"status": "FAILED", "completedAt": utc_now(), "error": str(error)})
                    self._write_job(job)
                except Exception:
                    return

    def extraction(self, document_id: str) -> dict[str, Any]:
        job = next((item for item in self._all_jobs() if item.get("documentId") == document_id and item.get("status") in {"REVIEW_REQUIRED", "APPROVED"}), None)
        if not job:
            raise ExtractionError("Für dieses Dokument liegt noch keine prüfbare Extraktion vor.")
        directory = self._job_directory(job["jobId"])
        return {
            "job": self.public_job(job),
            "raw": json.loads((directory / "raw.json").read_text(encoding="utf-8")),
            "normalized": json.loads((directory / "normalized.json").read_text(encoding="utf-8")),
            "report": (directory / "report.md").read_text(encoding="utf-8"),
        }

    def approve(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._read_job(job_id)
            if job.get("status") != "REVIEW_REQUIRED":
                raise ExtractionError("Nur eine erfolgreich geprüfte Extraktion kann freigegeben werden.")
            artifact_path = self._job_directory(job_id) / "normalized.json"
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            participant_key = "starters" if artifact.get("documentType") == "START_LIST" else "entries"
            containers = artifact.get("groups", []) or artifact.get("sections", [])
            previous_identity = [[person.get("athleteId"), person.get("identityMatch")] for group in containers for person in group.get(participant_key, [])]
            identity_counts, identity_warnings = self._assign_identities(containers, participant_key)
            current_identity = [[person.get("athleteId"), person.get("identityMatch")] for group in containers for person in group.get(participant_key, [])]
            artifact["statistics"]["identities"] = identity_counts
            artifact["warnings"] = list(dict.fromkeys([*artifact.get("warnings", []), *identity_warnings]))
            review = self._review(artifact)
            if identity_counts.get("CONFLICT"):
                atomic_json(artifact_path, artifact)
                job["review"] = review
                self._write_job(job)
                (self._job_directory(job_id) / "report.md").write_text(self._report_markdown(job, review, artifact), encoding="utf-8")
                raise ExtractionError("Die Athletenidentität enthält einen Konflikt und kann noch nicht freigegeben werden.")
            identity_changed = previous_identity != current_identity
            previously_reconciled = job.get("identityReconciledSignature") == current_identity
            if identity_changed and identity_counts.get("FUZZY_REVIEW") and not previously_reconciled:
                atomic_json(artifact_path, artifact)
                job["review"] = review
                job["identityReconciledSignature"] = current_identity
                self._write_job(job)
                (self._job_directory(job_id) / "report.md").write_text(self._report_markdown(job, review, artifact), encoding="utf-8")
                raise ExtractionError("Es wurde eine ähnliche Athletenidentität erkannt. Bitte den aktualisierten Prüfbericht kontrollieren und anschließend erneut freigeben.")
            atomic_json(artifact_path, artifact)
            job["review"] = review
            self.identities.register_artifact(artifact)
            job["status"] = "APPROVED"
            job["approvedAt"] = utc_now()
            if self.database:
                self.database.approve_extraction(job, artifact)
            for previous in self._all_jobs():
                if previous.get("jobId") == job_id or previous.get("documentId") != job.get("documentId"):
                    continue
                if previous.get("status") == "APPROVED":
                    previous["status"] = "SUPERSEDED"
                    previous["supersededBy"] = job_id
                    self._write_job(previous)
            self._write_job(job)
            approved = self.public_job(job)
        if job.get("documentKind") == "START_LIST" and job.get("weekendDate"):
            start_documents = {item.document_id for item in self.catalog.query(weekend_date=job["weekendDate"], archived=False) if item.kind == "START_LIST"}
            approved_documents = {item.get("documentId") for item in self._all_jobs() if item.get("weekendDate") == job["weekendDate"] and item.get("documentKind") == "START_LIST" and item.get("status") == "APPROVED"}
            if start_documents and start_documents <= approved_documents:
                self._restart_weekend_results(job["weekendDate"])
        return approved

    def approve_ready(self, weekend_date: str) -> list[dict[str, Any]]:
        selected: dict[str, dict[str, Any]] = {}
        for job in self._all_jobs():
            if job.get("weekendDate") != weekend_date or job.get("status") != "REVIEW_REQUIRED":
                continue
            selected.setdefault(str(job.get("documentId")), job)
        approved = []
        for job in selected.values():
            review = job.get("review") or {}
            if review.get("status") == "BEREIT" and not review.get("warnings"):
                approved.append(self.approve(job["jobId"]))
        return approved

    def approve_ready_snapshots(self) -> list[dict[str, Any]]:
        selected: dict[str, dict[str, Any]] = {}
        for job in self._all_jobs():
            if job.get("documentKind") not in {"DSV_RANKING", "DSV_RACE_COUNT"} or job.get("status") != "REVIEW_REQUIRED":
                continue
            selected.setdefault(str(job.get("documentId")), job)
        approved = []
        for job in selected.values():
            review = job.get("review") or {}
            if review.get("status") == "BEREIT" and not review.get("warnings"):
                approved.append(self.approve(job["jobId"]))
        return approved

    def approve_ready_season_results(self, season_id: str) -> list[dict[str, Any]]:
        selected: dict[str, dict[str, Any]] = {}
        for job in self._all_jobs():
            if job.get("documentKind") != "RESULT_LIST" or job.get("seasonId") != season_id or job.get("status") != "REVIEW_REQUIRED":
                continue
            selected.setdefault(str(job.get("sourceContentHash")), job)
        approved = []
        for job in selected.values():
            review = job.get("review") or {}
            if review.get("status") == "BEREIT" and not review.get("warnings"):
                approved.append(self.approve(job["jobId"]))
        return approved

    def _approved_artifacts(self) -> list[dict[str, Any]]:
        artifacts = []
        redirects = self.identities.redirects()
        content_hashes: set[str] = set()
        for job in self._all_jobs():
            if job.get("status") != "APPROVED":
                continue
            content_hash = str(job.get("sourceContentHash") or "")
            if content_hash and content_hash in content_hashes:
                continue
            if content_hash:
                content_hashes.add(content_hash)
            try:
                artifact = json.loads((self._job_directory(job["jobId"]) / "normalized.json").read_text(encoding="utf-8"))
                participant_key = "starters" if artifact.get("documentType") == "START_LIST" else "entries"
                for group in artifact.get("groups", []) or artifact.get("sections", []):
                    for person in group.get(participant_key, []):
                        athlete_id = person.get("athleteId")
                        seen = set()
                        while athlete_id in redirects and athlete_id not in seen:
                            seen.add(athlete_id)
                            athlete_id = redirects[athlete_id]
                        if athlete_id:
                            person["athleteId"] = athlete_id
                artifacts.append(artifact)
            except (OSError, json.JSONDecodeError):
                continue
        return artifacts

    def events(self) -> list[dict[str, Any]]:
        events = {artifact["event"]["id"]: artifact["event"] for artifact in self._approved_artifacts() if "event" in artifact}
        return sorted(events.values(), key=lambda item: (item.get("date") or "", item.get("name") or ""), reverse=True)

    def races(self) -> list[dict[str, Any]]:
        races: dict[str, dict[str, Any]] = {}
        for artifact in self._approved_artifacts():
            if "race" not in artifact:
                continue
            race = races.setdefault(artifact["race"]["id"], {**artifact["race"], "hasStartList": False, "hasResults": False, "sourceDocumentIds": []})
            race["hasStartList"] = race["hasStartList"] or artifact["documentType"] == "START_LIST"
            race["hasResults"] = race["hasResults"] or artifact["documentType"] == "RACE_RESULT"
            if artifact["documentId"] not in race["sourceDocumentIds"]:
                race["sourceDocumentIds"].append(artifact["documentId"])
        return sorted(races.values(), key=lambda item: (item.get("date") or "", item.get("name") or ""), reverse=True)

    def race(self, race_id: str) -> dict[str, Any]:
        matches = [artifact for artifact in self._approved_artifacts() if artifact["race"]["id"] == race_id]
        if not matches:
            raise ExtractionError("Das Rennen wurde nicht gefunden oder noch nicht freigegeben.")
        return {
            "race": next(item for item in self.races() if item["id"] == race_id),
            "event": matches[0]["event"],
            "startLists": [item for item in matches if item["documentType"] == "START_LIST"],
            "results": [item for item in matches if item["documentType"] == "RACE_RESULT"],
        }

    def athletes(self, target_club: bool | None = None) -> list[dict[str, Any]]:
        return self.identities.public_athletes(target_club)

    def athlete(self, athlete_id: str, artifacts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        try:
            athlete = self.identities.athlete(athlete_id)
        except AthleteIdentityError as error:
            raise ExtractionError(str(error)) from error
        starts = []
        results = []
        rankings = []
        race_counts = []
        race_count_coverages = []
        for artifact in artifacts if artifacts is not None else self._approved_artifacts():
            if artifact["documentType"] == "START_LIST":
                for group in artifact["groups"]:
                    for entry in group.get("starters", []):
                        if entry.get("athleteId") == athlete["id"]:
                            starts.append({"race": artifact["race"], "event": artifact["event"], "group": {key: group.get(key) for key in ("id", "label", "ageClass", "competitionCategory")}, "start": entry})
            elif artifact["documentType"] == "RACE_RESULT":
                for group in artifact["groups"]:
                    for entry in group.get("entries", []):
                        if entry.get("athleteId") == athlete["id"]:
                            results.append({"race": artifact["race"], "event": artifact["event"], "group": {key: group.get(key) for key in ("id", "label", "ageClass", "competitionCategory", "classificationMethod")}, "result": entry})
            elif artifact["documentType"] == "DSV_RANKING":
                for section in artifact["sections"]:
                    for entry in section.get("entries", []):
                        if entry.get("athleteId") == athlete["id"]:
                            rankings.append({
                                "snapshot": artifact["snapshot"],
                                "sourceFormat": artifact.get("source", {}).get("format"),
                                "section": {key: section.get(key) for key in ("scope", "label", "gender", "ageClass", "birthYear")},
                                "ranking": entry,
                            })
            elif artifact["documentType"] == "DSV_RACE_COUNT":
                race_count_coverages.append({
                    "snapshot": artifact["snapshot"],
                    "coverage": artifact.get("coverage"),
                    "sections": [
                        {key: section.get(key) for key in ("ageClass", "minimumIncludedRaces", "maximumRaces")}
                        for section in artifact["sections"]
                    ],
                })
                for section in artifact["sections"]:
                    for entry in section.get("entries", []):
                        if entry.get("athleteId") == athlete["id"]:
                            race_counts.append({"snapshot": artifact["snapshot"], "coverage": artifact.get("coverage"), "ageClass": section.get("ageClass"), "raceCount": entry})
        return athlete | {"starts": starts, "results": results, "rankings": rankings, "raceCounts": race_counts, "raceCountCoverages": race_count_coverages}

    @staticmethod
    def _season_for_date(value: str | None) -> str | None:
        if not value or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return None
        year, month = int(value[:4]), int(value[5:7])
        start = year if month >= 7 else year - 1
        return f"{start}-{start + 1}"

    def athlete_analytics(self, athlete_id: str, artifacts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        profile = self.athlete(athlete_id, artifacts)
        seasons: dict[str, dict[str, Any]] = {}

        def season(value: str) -> dict[str, Any]:
            return seasons.setdefault(value, {
                "seasonId": value, "recordedResults": [], "rankingHistory": [],
                "raceCountHistory": [], "raceCountCoverageHistory": [], "recordedRaceStarts": 0,
                "reportedDns": 0,
            })

        for item in profile["results"]:
            season_id = self._season_for_date(item.get("race", {}).get("date"))
            if not season_id:
                continue
            result = item["result"]
            runs = result.get("runResults", [])
            started = bool(runs and runs[0].get("status") != "DNS") or (not runs and result.get("status") != "DNS")
            compact = {
                "race": item["race"], "event": item["event"], "group": item["group"],
                "status": result.get("status"), "rank": result.get("rank"),
                "federationPoints": result.get("federationPoints"),
                "printedFederationPoints": result.get("printedFederationPoints"),
                "rawRacePoints": result.get("rawRacePoints"),
                "appliedPenaltyPoints": result.get("appliedPenaltyPoints"),
                "pointsSource": result.get("pointsSource"),
                "officialTimeSeconds": result.get("officialTimeSeconds"), "started": started,
            }
            season_value = season(season_id)
            if started:
                season_value["recordedResults"].append(compact)
                season_value["recordedRaceStarts"] += 1
            else:
                # DNS remains in the approved raw extraction for auditability,
                # but it is not an athlete result because no race was started.
                season_value["reportedDns"] += 1

        ranking_by_snapshot: dict[str, dict[str, Any]] = {}
        scope_priority = {"OVERALL": 0, "AGE_CLASS": 1, "BIRTH_YEAR": 2}
        for item in profile["rankings"]:
            snapshot = item["snapshot"]
            snapshot_id = snapshot["id"]
            candidate = {
                "snapshotId": snapshot_id, "documentId": snapshot.get("documentId"),
                "publishedAt": snapshot.get("publishedAt"), "seasonId": snapshot["seasonId"],
                "snapshotKind": snapshot.get("snapshotKind"),
                "sourceFormat": item.get("sourceFormat"),
                "scope": item["section"],
                "basePoints": item["ranking"].get("basePoints"),
                "listPoints": item["ranking"].get("listPoints"),
                "previousEndListPoints": item["ranking"].get("previousEndListPoints"),
                "seasonCorrectionPoints": item["ranking"].get("seasonCorrectionPoints"),
                "overallRank": item["ranking"].get("overallRank"),
                "ageClassRank": item["ranking"].get("ageClassRank"),
                "birthYearRank": item["ranking"].get("birthYearRank"),
            }
            current = ranking_by_snapshot.get(snapshot_id)
            if current is None or scope_priority.get(candidate["scope"].get("scope"), 99) < scope_priority.get(current["scope"].get("scope"), 99):
                ranking_by_snapshot[snapshot_id] = candidate
        for item in ranking_by_snapshot.values():
            season(item["seasonId"])["rankingHistory"].append(item)

        for item in profile["raceCounts"]:
            snapshot = item["snapshot"]
            season(snapshot["seasonId"])["raceCountHistory"].append({
                "snapshotId": snapshot["id"], "documentId": snapshot.get("documentId"),
                "observedAt": snapshot.get("observedAt"), "ageClass": item.get("ageClass"),
                "raceCount": item["raceCount"].get("raceCount"),
                "listPoints": item["raceCount"].get("listPoints"),
                "coverage": item.get("coverage"),
            })

        for item in profile.get("raceCountCoverages", []):
            snapshot = item["snapshot"]
            season(snapshot["seasonId"])["raceCountCoverageHistory"].append({
                "snapshotId": snapshot["id"], "documentId": snapshot.get("documentId"),
                "observedAt": snapshot.get("observedAt"), "coverage": item.get("coverage"),
                "sections": item.get("sections", []),
            })

        for value in seasons.values():
            value["recordedResults"].sort(key=lambda item: item["race"].get("date") or "")
            value["rankingHistory"].sort(key=lambda item: item.get("publishedAt") or "")
            value["raceCountHistory"].sort(key=lambda item: item.get("observedAt") or "")
            value["raceCountCoverageHistory"].sort(key=lambda item: item.get("observedAt") or "")
            value["latestRanking"] = value["rankingHistory"][-1] if value["rankingHistory"] else None
            value["latestPublishedRaceCount"] = value["raceCountHistory"][-1] if value["raceCountHistory"] else None
            latest_coverage = value["raceCountCoverageHistory"][-1] if value["raceCountCoverageHistory"] else None
            official_count = value["latestPublishedRaceCount"]
            if official_count:
                value["raceCountOverview"] = {**official_count, "source": "DSV_OFFICIAL"}
            else:
                season_end_year = int(value["seasonId"].split("-")[1])
                athlete_age = season_end_year - int(profile.get("birthYear") or 0)
                age_class = "U14" if athlete_age in {13, 14} else "U16" if athlete_age in {15, 16} else None
                coverage_section = next((item for item in (latest_coverage or {}).get("sections", []) if item.get("ageClass") == age_class), None)
                value["raceCountOverview"] = {
                    "raceCount": value["recordedRaceStarts"], "source": "IMPORTED_RESULTS",
                    "observedAt": max((item["race"].get("date") or "" for item in value["recordedResults"]), default=None),
                    "ageClass": age_class,
                    "officialMinimumIncludedRaces": (coverage_section or {}).get("minimumIncludedRaces"),
                    "maximumRaces": (coverage_section or {}).get("maximumRaces"),
                    "coverage": (latest_coverage or {}).get("coverage"),
                }
            if len(value["rankingHistory"]) >= 2:
                first, last = value["rankingHistory"][0], value["rankingHistory"][-1]
                value["listPointsChange"] = round_points(last["listPoints"] - first["listPoints"])
            else:
                value["listPointsChange"] = None
            statuses = {status: 0 for status in ("CLASSIFIED", "DNS", "DNF", "DSQ")}
            for result in value["recordedResults"]:
                status = result.get("status")
                if status in statuses:
                    statuses[status] += 1
            classified_ranks = [result["rank"] for result in value["recordedResults"] if result.get("status") == "CLASSIFIED" and isinstance(result.get("rank"), int)]
            value["resultSummary"] = {
                "documents": len(value["recordedResults"]),
                "starts": value["recordedRaceStarts"],
                "classified": statuses["CLASSIFIED"],
                "dns": value.pop("reportedDns", 0), "dnf": statuses["DNF"], "dsq": statuses["DSQ"],
                "podiums": sum(rank <= 3 for rank in classified_ranks),
                "bestRank": min(classified_ranks) if classified_ranks else None,
            }
            start_snapshot = next((item for item in value["rankingHistory"] if item.get("snapshotKind") == "SEASON_START_BASE"), None)
            if start_snapshot is None:
                base_points = MAXIMUM_START_POINTS
            elif start_snapshot.get("seasonCorrectionPoints") is not None:
                base_points = float(start_snapshot["listPoints"])
            elif start_snapshot.get("sourceFormat") == "DSV_CLUB_END_LIST_PDF":
                previous_end_points = float(start_snapshot["listPoints"])
                base_points, correction = adjusted_season_base(
                    previous_end_points, value["seasonId"], profile.get("gender") or "MALE"
                )
                start_snapshot["previousEndListPoints"] = previous_end_points
                start_snapshot["seasonCorrectionPoints"] = correction
                start_snapshot["listPoints"] = base_points
            else:
                base_points = float(start_snapshot["listPoints"])
            value["disciplinePoints"] = season_projection(base_points, value["recordedResults"], value["seasonId"])
            value["disciplinePoints"]["baseSource"] = (
                "MAXIMUM_NEW_ATHLETE" if start_snapshot is None else "DSV_SEASON_START_LIST"
            )
            if start_snapshot:
                value["disciplinePoints"]["previousEndListPoints"] = start_snapshot.get("previousEndListPoints")
                value["disciplinePoints"]["seasonCorrectionPoints"] = start_snapshot.get("seasonCorrectionPoints")

        athlete = {key: value for key, value in profile.items() if key not in {"starts", "results", "rankings", "raceCounts", "raceCountCoverages"}}
        return {"athlete": athlete, "seasons": sorted(seasons.values(), key=lambda item: item["seasonId"], reverse=True)}

    def athlete_season_overview(self, season_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"\d{4}-\d{4}", season_id):
            raise ExtractionError("Die Saison muss das Format JJJJ-JJJJ haben.")
        artifacts = self._approved_artifacts()
        season_end_year = int(season_id.split("-")[1])
        items = []
        for athlete in self.athletes(True):
            birth_year = athlete.get("birthYear")
            age = season_end_year - int(birth_year or 0)
            age_class = "U14" if age in {13, 14} else "U16" if age in {15, 16} else None
            if not age_class:
                continue
            analytics = self.athlete_analytics(athlete["id"], artifacts)
            selected = next((item for item in analytics["seasons"] if item["seasonId"] == season_id), None)
            if not selected:
                continue
            points = selected.get("disciplinePoints") or {}
            ranking = selected.get("latestRanking") or {}
            items.append({
                "athleteId": athlete["id"], "displayName": athlete.get("displayName"),
                "fullName": athlete.get("fullName"), "birthYear": birth_year, "ageClass": age_class,
                "gender": athlete.get("gender") or (ranking.get("scope") or {}).get("gender"),
                "basePoints": points.get("basePoints"), "overallPoints": points.get("overallPoints"),
                "slalomPoints": points.get("slalomPoints"), "giantSlalomPoints": points.get("giantSlalomPoints"),
                "birthYearRank": ranking.get("birthYearRank"), "ageClassRank": ranking.get("ageClassRank"),
                "recordedRaceStarts": selected.get("recordedRaceStarts", 0),
            })
        items.sort(key=lambda item: (-(item.get("birthYear") or 0), item.get("birthYearRank") or 1_000_000, item.get("displayName") or ""))
        return {"seasonId": season_id, "items": items, "total": len(items)}

    def merge_athletes(self, source_id: str, target_id: str) -> dict[str, Any]:
        try:
            return self.identities.merge(source_id, target_id)
        except AthleteIdentityError as error:
            raise ExtractionError(str(error)) from error

    def resume_incomplete(self) -> None:
        for job in self._all_jobs():
            if job.get("status") not in {"PENDING", "PROCESSING"}:
                continue
            job["status"] = "PENDING"
            self._write_job(job)
            threading.Thread(target=self.process, args=(job["jobId"],), daemon=True, name=job["jobId"]).start()
