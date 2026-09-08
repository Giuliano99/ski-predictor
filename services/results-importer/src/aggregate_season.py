"""Aggregate evaluated weekend bundles into a season leaderboard."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCORING_MODEL = "EQUAL_QUESTION_POINTS_V1"


def standing_question_points(bundle: dict[str, Any], standing: dict[str, Any]) -> tuple[int, int]:
    """Read equal question points and transparently migrate old weekend bundles."""
    evaluations = {
        evaluation.get("submissionId"): evaluation
        for evaluation in bundle.get("evaluations", [])
    }
    evaluation = evaluations.get(standing.get("submissionId"))
    if evaluation and evaluation.get("rawPoints") is not None:
        return int(evaluation["rawPoints"]), int(evaluation.get("maximumRawPoints", 0))
    return int(standing["weekendPoints"]), int(standing.get("maximumWeekendPoints", 0))


def rank_season(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank by total points, then weekend wins; share rank if both are equal."""
    ordered = sorted(
        items,
        key=lambda item: (-item["seasonPoints"], -item["weekendWins"], item["displayName"].casefold()),
    )
    previous_result: tuple[int, int] | None = None
    previous_rank = 0
    for index, item in enumerate(ordered, start=1):
        result = (item["seasonPoints"], item["weekendWins"])
        if result != previous_result:
            previous_rank = index
            previous_result = result
        item["rank"] = previous_rank
    return ordered


def aggregate_season(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    if not bundles:
        raise ValueError("At least one weekend evaluation is required")
    season_ids = {bundle["seasonId"] for bundle in bundles}
    if len(season_ids) != 1:
        raise ValueError(f"Weekend evaluations belong to different seasons: {sorted(season_ids)}")
    tip_round_ids = [bundle["tipRoundId"] for bundle in bundles]
    if len(tip_round_ids) != len(set(tip_round_ids)):
        raise ValueError("A tip round may only be included once")

    by_player: dict[str, dict[str, Any]] = {}
    for bundle in bundles:
        weekend_results: list[tuple[str, int]] = []
        for standing in bundle["standings"]:
            player = by_player.setdefault(standing["playerId"], {
                "playerId": standing["playerId"],
                "displayName": standing["displayName"],
                "seasonPoints": 0,
                "maximumSeasonPoints": 0,
                "scoredQuestions": 0,
                "weekendWins": 0,
                "rounds": 0,
            })
            player["displayName"] = standing["displayName"]
            points, maximum = standing_question_points(bundle, standing)
            player["seasonPoints"] += points
            player["maximumSeasonPoints"] += maximum
            player["scoredQuestions"] += maximum // 100
            player["rounds"] += 1
            weekend_results.append((standing["playerId"], points))

        if weekend_results:
            winning_points = max(points for _, points in weekend_results)
            for player_id, points in weekend_results:
                if points == winning_points:
                    by_player[player_id]["weekendWins"] += 1

    standings = rank_season(list(by_player.values()))
    for standing in standings:
        standing["averageQuestionPoints"] = (
            round(standing["seasonPoints"] / standing["scoredQuestions"])
            if standing["scoredQuestions"] else 0
        )
        # Kept temporarily for older website clients.
        standing["averagePoints"] = (
            standing["averageQuestionPoints"]
            if standing["scoredQuestions"]
            else round(standing["seasonPoints"] / standing["rounds"])
        )
    return {
        "schemaVersion": 1,
        "scoringModel": SCORING_MODEL,
        "seasonId": next(iter(season_ids)),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "tipRoundIds": tip_round_ids,
        "tipRoundVersions": {bundle["tipRoundId"]: bundle["tipRoundVersion"] for bundle in bundles},
        "standings": standings,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("weekends", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--website-output", type=Path)
    arguments = parser.parse_args(argv)
    bundles = [json.loads(path.read_text(encoding="utf-8")) for path in arguments.weekends]
    season = aggregate_season(bundles)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(season, ensure_ascii=False, indent=2) + "\n"
    arguments.output.write_text(serialized, encoding="utf-8")
    if arguments.website_output:
        arguments.website_output.parent.mkdir(parents=True, exist_ok=True)
        arguments.website_output.write_text(serialized, encoding="utf-8")
    print(json.dumps({
        "seasonId": season["seasonId"],
        "players": len(season["standings"]),
        "output": str(arguments.output),
        "websiteOutput": str(arguments.website_output) if arguments.website_output else None,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
