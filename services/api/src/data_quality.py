"""Read-only quality checks for the shared ski race database."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


EXPECTED_RESULT_STATUSES = {"CLASSIFIED", "DNS", "DNF", "DSQ"}
BROKEN_TEXT_MARKERS = ("\ufffd", "Ã", "Â", "â€", "â€“", "â€”")


def _rows(database: Any, statement: str, parameters: Iterable[Any] = ()) -> list[tuple[Any, ...]]:
    with database.connect() as connection:
        return [tuple(row) for row in connection.execute(statement, tuple(parameters)).fetchall()]


def _group_counts(database: Any, table: str, column: str) -> dict[str, int]:
    return {
        str(row[0] if row[0] is not None else "NULL"): int(row[1])
        for row in _rows(database, f"SELECT {column}, count(*) FROM {table} GROUP BY {column} ORDER BY {column}")
    }


def audit_database(database: Any, available_document_ids: set[str] | None = None) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []

    def add(code: str, severity: str, message: str, records: list[dict[str, Any]]) -> None:
        if records:
            issues.append({"code": code, "severity": severity, "message": message, "count": len(records), "records": records})

    documents_without_import = _rows(
        database,
        """SELECT d.id,d.original_name,d.kind FROM source_documents d
        LEFT JOIN extraction_imports i ON i.document_id=d.id
        GROUP BY d.id,d.original_name,d.kind HAVING count(i.id)=0 ORDER BY d.original_name""",
    )
    add("DOCUMENT_WITHOUT_IMPORT", "WARNING", "Dokumente wurden noch nicht extrahiert.", [
        {"documentId": row[0], "name": row[1], "kind": row[2]} for row in documents_without_import
    ])

    documents_without_approval = _rows(
        database,
        """SELECT d.id,d.original_name,d.kind FROM source_documents d
        JOIN extraction_imports i ON i.document_id=d.id
        GROUP BY d.id,d.original_name,d.kind
        HAVING sum(CASE WHEN i.status='APPROVED' THEN 1 ELSE 0 END)=0 ORDER BY d.original_name""",
    )
    add("DOCUMENT_WITHOUT_APPROVAL", "WARNING", "Extrahierte Dokumente warten noch auf eine Freigabe.", [
        {"documentId": row[0], "name": row[1], "kind": row[2]} for row in documents_without_approval
    ])

    approved_without_race = _rows(
        database,
        """SELECT i.id,d.original_name FROM extraction_imports i
        JOIN source_documents d ON d.id=i.document_id
        LEFT JOIN race_documents rd ON rd.extraction_id=i.id
        WHERE i.status='APPROVED' AND d.kind IN ('START_LIST','RESULT_LIST')
          AND rd.extraction_id IS NULL ORDER BY d.original_name""",
    )
    add("APPROVED_IMPORT_WITHOUT_RACE", "ERROR", "Freigegebene Importe sind keinem Rennen zugeordnet.", [
        {"importId": row[0], "name": row[1]} for row in approved_without_race
    ])

    missing_athlete = _rows(
        database,
        """SELECT id,race_id,full_name,start_number,participant_type FROM race_participants
        WHERE athlete_id IS NULL ORDER BY race_id,start_number""",
    )
    add("PARTICIPANT_WITHOUT_ATHLETE", "ERROR", "Teilnehmer besitzen keine stabile Athletenidentitaet.", [
        {"participantId": row[0], "raceId": row[1], "name": row[2], "startNumber": row[3], "type": row[4]}
        for row in missing_athlete
    ])

    snapshot_without_athlete = _rows(
        database,
        """SELECT 'DSV_RANKING',snapshot_id,external_athlete_id FROM dsv_ranking_entries
        WHERE athlete_id IS NULL
        UNION ALL
        SELECT 'DSV_RACE_COUNT',snapshot_id,external_athlete_id FROM dsv_race_count_entries
        WHERE athlete_id IS NULL
        ORDER BY 1,2,3""",
    )
    add("SNAPSHOT_ENTRY_WITHOUT_ATHLETE", "ERROR", "DSV-Snapshot-Eintraege besitzen keine stabile Athletenidentitaet.", [
        {"documentType": row[0], "snapshotId": row[1], "externalAthleteId": row[2]}
        for row in snapshot_without_athlete
    ])

    external_conflicts = _rows(
        database,
        """SELECT external_athlete_id,count(DISTINCT athlete_id) FROM (
          SELECT external_athlete_id,athlete_id FROM race_participants
          UNION ALL SELECT external_athlete_id,athlete_id FROM dsv_ranking_entries
          UNION ALL SELECT external_athlete_id,athlete_id FROM dsv_race_count_entries
        ) athlete_sources
        WHERE external_athlete_id IS NOT NULL AND trim(external_athlete_id)<>'' AND athlete_id IS NOT NULL
        GROUP BY external_athlete_id HAVING count(DISTINCT athlete_id)>1 ORDER BY external_athlete_id""",
    )
    add("EXTERNAL_ID_CONFLICT", "ERROR", "Ein Verbandscode zeigt auf mehrere Athleten.", [
        {"externalAthleteId": row[0], "athleteCount": row[1]} for row in external_conflicts
    ])

    duplicate_identities = _rows(
        database,
        """SELECT lower(trim(full_name)),birth_year,count(DISTINCT id) FROM athletes
        GROUP BY lower(trim(full_name)),birth_year HAVING count(DISTINCT id)>1
        ORDER BY lower(trim(full_name)),birth_year""",
    )
    add("POSSIBLE_DUPLICATE_ATHLETE", "WARNING", "Name und Jahrgang kommen unter mehreren Athletenkennungen vor.", [
        {"normalizedName": row[0], "birthYear": row[1], "athleteCount": row[2]} for row in duplicate_identities
    ])

    missing_birth_year = _rows(
        database,
        """SELECT id,display_name FROM athletes WHERE target_club=true AND birth_year IS NULL ORDER BY display_name""",
    )
    add("TARGET_ATHLETE_WITHOUT_BIRTH_YEAR", "WARNING", "Bei Oberhachinger Athleten fehlt der Jahrgang.", [
        {"athleteId": row[0], "displayName": row[1]} for row in missing_birth_year
    ])

    race_coverage = _rows(
        database,
        """SELECT r.id,r.name,
        sum(CASE WHEN rd.document_type='START_LIST' THEN 1 ELSE 0 END),
        sum(CASE WHEN rd.document_type='RACE_RESULT' THEN 1 ELSE 0 END),
        max(CASE WHEN rd.document_type='RACE_RESULT' AND d.weekend_date IS NULL THEN 1 ELSE 0 END)
        FROM races r LEFT JOIN race_documents rd ON rd.race_id=r.id
        LEFT JOIN source_documents d ON d.id=rd.document_id
        GROUP BY r.id,r.name ORDER BY r.name""",
    )
    add("INCOMPLETE_RACE_DOCUMENTS", "WARNING", "Rennen haben nicht mindestens eine Start- und Ergebnisliste.", [
        {"raceId": row[0], "name": row[1], "startLists": row[2], "resultLists": row[3]}
        for row in race_coverage if (not row[2] and not row[4]) or not row[3]
    ])

    broken_text: list[dict[str, Any]] = []
    text_sources = (
        ("events", "id", ("name", "location")),
        ("races", "id", ("name", "location")),
        ("athletes", "id", ("full_name", "display_name")),
        ("race_participants", "id", ("full_name", "display_name", "club", "federation")),
    )
    for table, id_column, columns in text_sources:
        selected = ",".join((id_column, *columns))
        for row in _rows(database, f"SELECT {selected} FROM {table}"):
            for position, value in enumerate(row[1:], 1):
                if value is not None and any(marker in str(value) for marker in BROKEN_TEXT_MARKERS):
                    broken_text.append({
                        "table": table, "recordId": row[0], "field": columns[position - 1], "value": value,
                    })
    add("BROKEN_TEXT_ENCODING", "ERROR", "Texte enthalten Zeichen einer fehlerhaften Zeichenkodierung.", broken_text)

    result_statuses = _group_counts(database, "race_participants", "status")
    add("UNEXPECTED_RESULT_STATUS", "WARNING", "Unbekannte Ergebnisstatus muessen fachlich geprueft werden.", [
        {"status": status, "count": count}
        for status, count in result_statuses.items()
        if status != "NULL" and status not in EXPECTED_RESULT_STATUSES
    ])

    if available_document_ids is not None:
        stored_documents = {str(row[0]): str(row[1]) for row in _rows(database, "SELECT id,original_name FROM source_documents")}
        add("SOURCE_FILE_MISSING", "ERROR", "In der Datenbank registrierte Originaldateien fehlen im Storage.", [
            {"documentId": document_id, "name": name}
            for document_id, name in stored_documents.items() if document_id not in available_document_ids
        ])

    error_count = sum(issue["count"] for issue in issues if issue["severity"] == "ERROR")
    warning_count = sum(issue["count"] for issue in issues if issue["severity"] == "WARNING")
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "FEHLER" if error_count else ("WARNUNGEN" if warning_count else "BEREIT"),
        "errors": error_count,
        "warnings": warning_count,
        "counts": database.counts(),
        "distributions": {
            "documentKinds": _group_counts(database, "source_documents", "kind"),
            "importStatuses": _group_counts(database, "extraction_imports", "status"),
            "participantTypes": _group_counts(database, "race_participants", "participant_type"),
            "resultStatuses": result_statuses,
        },
        "issues": issues,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Datenqualitaetsbericht", "", f"**Status: {report['status']}**", "",
        f"Erzeugt: `{report['generatedAt']}`  ", f"Fehler: **{report['errors']}**  ",
        f"Warnungen: **{report['warnings']}**", "", "## Datenmengen", "",
    ]
    lines.extend(f"- {name}: {count}" for name, count in report["counts"].items())
    lines.extend(["", "## Pruefpunkte", ""])
    if not report["issues"]:
        lines.append("- Keine Auffaelligkeiten erkannt.")
    for issue in report["issues"]:
        lines.extend([f"### {issue['severity']}: {issue['code']} ({issue['count']})", "", issue["message"], ""])
        for record in issue["records"]:
            lines.append("- " + " | ".join(f"{key}: {value}" for key, value in record.items()))
        lines.append("")
    lines.extend([
        "## Hinweis", "",
        "Der Bericht veraendert keine Daten. Unsichere Identitaeten und unvollstaendige Dokumente muessen vor einer Korrektur vom Spielleiter geprueft werden.", "",
    ])
    return "\n".join(lines)


def write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(report), encoding="utf-8")
