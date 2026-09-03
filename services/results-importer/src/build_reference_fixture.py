"""Create a privacy-reduced regression fixture from one reviewed local weekend."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from storage_paths import resolve_path


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def reduced_result(document: dict[str, Any]) -> dict[str, Any]:
    groups = []
    for group_index, group in enumerate(document["groups"]):
        target_entries = [entry for entry in group["entries"] if entry.get("targetClub")]
        classified_ranks = [entry["rank"] for entry in group["entries"] if entry.get("status") == "CLASSIFIED" and entry.get("rank") is not None]
        max_rank = max(classified_ranks, default=0)
        retained_entries = list(target_entries)
        if max_rank and not any(entry.get("rank") == max_rank for entry in target_entries):
            retained_entries.append({
                "startNumber": 900_000 + group_index,
                "status": "CLASSIFIED",
                "rank": max_rank,
                "officialTimeSeconds": group.get("slowestClassifiedTimeSeconds"),
                "targetClub": False,
            })
        groups.append({
            "id": group["id"],
            "winnerTimeSeconds": group.get("winnerTimeSeconds"),
            "slowestClassifiedTimeSeconds": group.get("slowestClassifiedTimeSeconds"),
            "entries": [
                {
                    key: entry[key]
                    for key in ("startNumber", "status", "rank", "officialTimeSeconds", "percentageGap", "targetClub")
                    if key in entry
                }
                for entry in retained_entries
            ],
        })
    return {"raceId": document["raceId"], "official": document["official"], "groups": groups}


def build_fixture(workspace: Path, config_path: Path) -> dict[str, Any]:
    config = load_json(config_path)
    tip_round = load_json(resolve_path(workspace, config["tipRound"]["output"]))
    results = [load_json(resolve_path(workspace, item["output"])) for item in config["results"]]
    submissions_dir = resolve_path(workspace, config["submissionsDir"])
    submissions = [load_json(path) for path in sorted(submissions_dir.glob("*.json"))]
    evaluation = load_json(resolve_path(workspace, config["weekendEvaluation"]["output"]))

    expected_points = {
        item["player"]["id"]: {
            question["questionId"]: question["points"]
            for question in item["questionEvaluations"]
        }
        for item in evaluation["evaluations"]
    }
    expected_standings = [
        {key: standing[key] for key in ("rank", "playerId", "displayName", "weekendPoints")}
        for standing in evaluation["standings"]
    ]
    reduced_tip_round = {
        key: tip_round[key]
        for key in ("id", "contentVersion", "races", "athletes", "questions")
    }
    reduced_submissions = [
        {key: submission[key] for key in ("id", "tipRoundId", "tipRoundVersion", "player", "submittedAt", "answers")}
        for submission in submissions
    ]
    return {
        "description": "Fachlicher Referenzfall Rennwochenende 7. und 8. März 2026",
        "tipRound": reduced_tip_round,
        "results": [reduced_result(result) for result in results],
        "submissions": reduced_submissions,
        "expected": {
            "standings": expected_standings,
            "questionPointsByPlayer": expected_points,
        },
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/weekends/tip-round-2026-03-07.json"))
    parser.add_argument("--output", type=Path, default=Path("services/results-importer/tests/fixtures/reference-weekend-2026-03-07.json"))
    arguments = parser.parse_args(argv)
    workspace = Path(__file__).resolve().parents[3]
    fixture = build_fixture(workspace, resolve_path(workspace, str(arguments.config)))
    output = resolve_path(workspace, str(arguments.output))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "players": len(fixture["submissions"]), "questions": len(fixture["tipRound"]["questions"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
