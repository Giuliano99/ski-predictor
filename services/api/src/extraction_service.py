"""Persistent asynchronous PDF extraction and reusable race-data projections."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from athlete_identity import AthleteIdentityError, AthleteIdentityRegistry
from document_catalog import Document, DocumentCatalog


WORKSPACE = Path(__file__).resolve().parents[3]
IMPORTER_SOURCE = WORKSPACE / "services" / "results-importer" / "src"
if str(IMPORTER_SOURCE) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SOURCE))

from extract_result_list import extract_result_list  # noqa: E402
from extract_start_list import extract_start_list, slugify  # noqa: E402


EXTRACTION_VERSION = "ski-predictor-extractor-v2-athlete-identity"
JOB_STATUSES = {"PENDING", "PROCESSING", "REVIEW_REQUIRED", "APPROVED", "FAILED"}


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
    def __init__(self, catalog: DocumentCatalog, data_directory: Path | None = None):
        self.catalog = catalog
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
        return json.loads(path.read_text(encoding="utf-8"))

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
        if document.kind not in {"START_LIST", "RESULT_LIST"}:
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

    def _normalize(self, document: Document, extracted: dict[str, Any]) -> dict[str, Any]:
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
        return {
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

    def _review(self, normalized: dict[str, Any]) -> dict[str, Any]:
        warnings = list(normalized.get("warnings", []))
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
            else:
                extracted = self._extract_result(document, job)
            normalized = self._normalize(document, extracted)
            review = self._review(normalized)
            directory = self._job_directory(job_id)
            atomic_json(directory / "raw.json", extracted)
            atomic_json(directory / "normalized.json", normalized)
            (directory / "report.md").write_text(self._report_markdown(job, review, normalized), encoding="utf-8")
            with self._lock:
                job = self._read_job(job_id)
                job.update({"status": "REVIEW_REQUIRED", "completedAt": utc_now(), "review": review, "raceId": normalized["race"]["id"], "eventId": normalized["event"]["id"]})
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
            previous_identity = [[person.get("athleteId"), person.get("identityMatch")] for group in artifact.get("groups", []) for person in group.get(participant_key, [])]
            identity_counts, identity_warnings = self._assign_identities(artifact["groups"], participant_key)
            current_identity = [[person.get("athleteId"), person.get("identityMatch")] for group in artifact.get("groups", []) for person in group.get(participant_key, [])]
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
            self._write_job(job)
            approved = self.public_job(job)
        if job.get("documentKind") == "START_LIST" and job.get("weekendDate"):
            start_documents = {item.document_id for item in self.catalog.query(weekend_date=job["weekendDate"], archived=False) if item.kind == "START_LIST"}
            approved_documents = {item.get("documentId") for item in self._all_jobs() if item.get("weekendDate") == job["weekendDate"] and item.get("documentKind") == "START_LIST" and item.get("status") == "APPROVED"}
            if start_documents and start_documents <= approved_documents:
                self.start_weekend(job["weekendDate"])
        return approved

    def _approved_artifacts(self) -> list[dict[str, Any]]:
        artifacts = []
        redirects = self.identities.redirects()
        for job in self._all_jobs():
            if job.get("status") != "APPROVED":
                continue
            try:
                artifact = json.loads((self._job_directory(job["jobId"]) / "normalized.json").read_text(encoding="utf-8"))
                participant_key = "starters" if artifact.get("documentType") == "START_LIST" else "entries"
                for group in artifact.get("groups", []):
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
        events = {artifact["event"]["id"]: artifact["event"] for artifact in self._approved_artifacts()}
        return sorted(events.values(), key=lambda item: (item.get("date") or "", item.get("name") or ""), reverse=True)

    def races(self) -> list[dict[str, Any]]:
        races: dict[str, dict[str, Any]] = {}
        for artifact in self._approved_artifacts():
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

    def athlete(self, athlete_id: str) -> dict[str, Any]:
        try:
            athlete = self.identities.athlete(athlete_id)
        except AthleteIdentityError as error:
            raise ExtractionError(str(error)) from error
        starts = []
        results = []
        for artifact in self._approved_artifacts():
            if artifact["documentType"] == "START_LIST":
                for group in artifact["groups"]:
                    for entry in group.get("starters", []):
                        if entry.get("athleteId") == athlete["id"]:
                            starts.append({"race": artifact["race"], "event": artifact["event"], "group": {key: group.get(key) for key in ("id", "label", "ageClass", "competitionCategory")}, "start": entry})
            else:
                for group in artifact["groups"]:
                    for entry in group.get("entries", []):
                        if entry.get("athleteId") == athlete["id"]:
                            results.append({"race": artifact["race"], "event": artifact["event"], "group": {key: group.get(key) for key in ("id", "label", "ageClass", "competitionCategory", "classificationMethod")}, "result": entry})
        return athlete | {"starts": starts, "results": results}

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
