"""Evaluate all exported submissions for one weekend and build its standings."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from evaluate_tip_round import evaluate


def ranked(items: list[dict[str, Any]], points_field: str) -> list[dict[str, Any]]:
    ordered = sorted(items, key=lambda item: (-item[points_field], item["displayName"].casefold()))
    previous_points: int | None = None
    previous_rank = 0
    for index, item in enumerate(ordered, start=1):
        points = item[points_field]
        if points != previous_points:
            previous_rank = index
            previous_points = points
        item["rank"] = previous_rank
    return ordered


def latest_submissions(submissions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_by_player: dict[str, dict[str, Any]] = {}
    for submission in submissions:
        player_id = submission.get("player", {}).get("id")
        if not player_id:
            raise ValueError(f"Submission {submission.get('id')!r} is missing a player id")
        current = latest_by_player.get(player_id)
        if current is None or submission.get("submittedAt", "") > current.get("submittedAt", ""):
            latest_by_player[player_id] = submission
    return list(latest_by_player.values())


def normalize_legacy_test_submission(
    tip_round: dict[str, Any],
    submission: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Add the missing version to compatible exports from the old local test UI.

    Production submissions and submissions carrying an explicit version always go
    through the normal strict version check.
    """
    if submission.get("tipRoundVersion") is not None:
        return submission, False
    if not tip_round.get("testMode") or not str(submission.get("id", "")).startswith("local-"):
        return submission, False
    expected_questions = {question["id"] for question in tip_round.get("questions", [])}
    answers = submission.get("answers")
    if submission.get("tipRoundId") != tip_round.get("id") or not isinstance(answers, dict) or set(answers) != expected_questions:
        return submission, False
    normalized = dict(submission)
    normalized["tipRoundVersion"] = tip_round["contentVersion"]
    return normalized, True


def build_weekend_evaluation(
    tip_round: dict[str, Any],
    results: list[dict[str, Any]],
    submissions: list[dict[str, Any]],
    season_id: str,
) -> dict[str, Any]:
    evaluations: list[dict[str, Any]] = []
    standings: list[dict[str, Any]] = []
    for original_submission in latest_submissions(submissions):
        submission, legacy_version_assumed = normalize_legacy_test_submission(tip_round, original_submission)
        evaluation = evaluate(tip_round, results, submission)
        evaluation["player"] = submission["player"]
        if legacy_version_assumed:
            evaluation["legacyTipRoundVersionAssumed"] = True
        evaluations.append(evaluation)
        standings.append({
            "submissionId": submission["id"],
            "playerId": submission["player"]["id"],
            "displayName": submission["player"]["displayName"],
            "weekendPoints": evaluation["weekendPoints"],
        })
    return {
        "schemaVersion": 1,
        "seasonId": season_id,
        "tipRoundId": tip_round["id"],
        "tipRoundVersion": tip_round["contentVersion"],
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "standings": ranked(standings, "weekendPoints"),
        "evaluations": evaluations,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tip_round", type=Path)
    parser.add_argument("results", nargs="+", type=Path)
    parser.add_argument("--submissions-dir", type=Path, required=True)
    parser.add_argument("--season-id", default="2026-2027")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--website-output", type=Path)
    arguments = parser.parse_args(argv)

    tip_round = json.loads(arguments.tip_round.read_text(encoding="utf-8"))
    result_documents = [json.loads(path.read_text(encoding="utf-8")) for path in arguments.results]
    submission_paths = sorted(arguments.submissions_dir.glob("*.json"))
    if not submission_paths:
        parser.error(f"no JSON submissions found in {arguments.submissions_dir}")
    submissions = [json.loads(path.read_text(encoding="utf-8")) for path in submission_paths]
    bundle = build_weekend_evaluation(tip_round, result_documents, submissions, arguments.season_id)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(bundle, ensure_ascii=False, indent=2) + "\n"
    arguments.output.write_text(serialized, encoding="utf-8")
    if arguments.website_output:
        arguments.website_output.parent.mkdir(parents=True, exist_ok=True)
        arguments.website_output.write_text(serialized, encoding="utf-8")
    print(json.dumps({
        "tipRoundId": bundle["tipRoundId"],
        "submissions": len(submissions),
        "players": len(bundle["standings"]),
        "output": str(arguments.output),
        "websiteOutput": str(arguments.website_output) if arguments.website_output else None,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
