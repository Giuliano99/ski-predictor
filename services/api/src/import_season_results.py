"""Import a flat season result-list folder and create an audit report."""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from database import Database
from document_catalog import DocumentCatalog
from extraction_service import ExtractionError, ExtractionService
from server import WORKSPACE, load_storage_root


def wait_for_jobs(service: ExtractionService, job_ids: list[str], timeout: int) -> list[dict]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        jobs = [service.job(job_id) for job_id in job_ids]
        if all(job["status"] not in {"PENDING", "PROCESSING"} for job in jobs):
            return jobs
        time.sleep(0.2)
    raise TimeoutError(f"Die Saisonextraktion war nach {timeout} Sekunden noch nicht abgeschlossen.")


def athlete_rows(service: ExtractionService, season_id: str) -> list[dict]:
    season_end = int(season_id.split("-")[1])
    rows = []
    for athlete in service.athletes(True):
        birth_year = athlete.get("birthYear")
        age = season_end - int(birth_year) if birth_year else None
        age_class = "U14" if age in {13, 14} else "U16" if age in {15, 16} else None
        if not age_class:
            continue
        analytics = service.athlete_analytics(athlete["id"])
        season = next((item for item in analytics["seasons"] if item["seasonId"] == season_id), None)
        if not season or not season["recordedResults"]:
            continue
        ranking = season.get("latestRanking") or {}
        rows.append({
            "athleteId": athlete["id"], "name": athlete["displayName"], "birthYear": birth_year,
            "ageClass": age_class, **season["resultSummary"],
            "listPoints": ranking.get("listPoints"), "ageClassRank": ranking.get("ageClassRank"),
            "birthYearRank": ranking.get("birthYearRank"),
            "slalomPoints": (season.get("disciplinePoints") or {}).get("slalomPoints"),
            "giantSlalomPoints": (season.get("disciplinePoints") or {}).get("giantSlalomPoints"),
            "overallPoints": (season.get("disciplinePoints") or {}).get("overallPoints"),
        })
    return sorted(rows, key=lambda item: (item["ageClass"], item["birthYear"], item["name"]))


def build_report(season_id: str, jobs: list[dict], approved: list[dict], approval_errors: list[str], athletes: list[dict]) -> dict:
    rows = []
    for job in jobs:
        statistics = (job.get("review") or {}).get("statistics") or {}
        rows.append({
            "file": job.get("sourceName"), "status": job.get("status"),
            "reviewStatus": (job.get("review") or {}).get("status"),
            "groups": statistics.get("groups", 0), "participants": statistics.get("participants", 0),
            "targetClubParticipants": statistics.get("targetClubParticipants", 0),
            "warnings": (job.get("review") or {}).get("warnings", []), "error": job.get("error"),
        })
    return {
        "seasonId": season_id, "documents": len(rows),
        "statuses": dict(Counter(row["status"] for row in rows)),
        "participants": sum(row["participants"] for row in rows),
        "targetClubResults": sum(row["targetClubParticipants"] for row in rows),
        "approved": sum(row["status"] == "APPROVED" for row in rows),
        "approvedThisRun": len(approved), "approvalErrors": approval_errors, "items": rows,
        "athletes": athletes,
    }


def markdown(report: dict) -> str:
    lines = [
        f"# Saisonimport {report['seasonId']}", "",
        f"- Ergebnislisten: {report['documents']}",
        f"- Erkannte Ergebniszeilen: {report['participants']}",
        f"- Ergebnisse Skiteam Oberhaching: {report['targetClubResults']}",
        f"- Freigegeben: {report['approved']}", "",
        "| Datei | Status | Gruppen | Ergebnisse | Oberhaching | Warnungen |", "|---|---|---:|---:|---:|---:|",
    ]
    for item in report["items"]:
        lines.append(f"| {item['file']} | {item['status']} | {item['groups']} | {item['participants']} | {item['targetClubParticipants']} | {len(item['warnings'])} |")
    lines.extend(["", "## Probleme", ""])
    problems = [f"{item['file']}: {item['error']}" for item in report["items"] if item.get("error")]
    problems.extend(report["approvalErrors"])
    lines.extend([f"- {problem}" for problem in problems] or ["- Keine technischen Fehler."])
    lines.extend(["", "## Oberhachinger U14/U16-Athleten", "", "| Athlet | AK | Jg. | Starts | Gewertet | Podest | Bestes Ergebnis | DNF | DSQ | DNS | SL | RS | Gesamt | AK-Rang | Jg.-Rang |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
    for athlete in report["athletes"]:
        value = lambda key: athlete.get(key) if athlete.get(key) is not None else "–"
        lines.append(f"| {athlete['name']} | {athlete['ageClass']} | {athlete['birthYear']} | {athlete['starts']} | {athlete['classified']} | {athlete['podiums']} | {value('bestRank')} | {athlete['dnf']} | {athlete['dsq']} | {athlete['dns']} | {value('slalomPoints')} | {value('giantSlalomPoints')} | {value('overallPoints')} | {value('ageClassRank')} | {value('birthYearRank')} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season_id")
    parser.add_argument("--approve-clean", action="store_true")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    catalog = DocumentCatalog(load_storage_root())
    database = Database.configured()
    if database:
        database.migrate()
        database.sync_documents(catalog.documents())
    service = ExtractionService(catalog, database=database)
    started = service.start_season_results(arguments.season_id)
    jobs = wait_for_jobs(service, [job["jobId"] for job in started], arguments.timeout)
    approved, approval_errors = [], []
    if arguments.approve_clean:
        for job in jobs:
            review = job.get("review") or {}
            if job.get("status") != "REVIEW_REQUIRED" or review.get("status") != "BEREIT" or review.get("warnings"):
                continue
            try:
                approved.append(service.approve(job["jobId"]))
            except ExtractionError as error:
                approval_errors.append(f"{job.get('sourceName')}: {error}")
        jobs = [service.job(job["jobId"]) for job in started]
    report = build_report(arguments.season_id, jobs, approved, approval_errors, athlete_rows(service, arguments.season_id))
    output = (arguments.output or WORKSPACE / "output" / "reports" / f"season-results-{arguments.season_id}.md").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown(report), encoding="utf-8")
    output.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("seasonId", "documents", "statuses", "participants", "targetClubResults", "approved", "approvedThisRun", "approvalErrors")} | {"athletes": len(report["athletes"]), "output": str(output)}, ensure_ascii=False))
    return 2 if report["statuses"].get("FAILED") or approval_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
