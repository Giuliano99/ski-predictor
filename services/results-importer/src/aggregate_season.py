"""Aggregate evaluated weekend bundles into a season leaderboard."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from evaluate_submissions import ranked


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
        for standing in bundle["standings"]:
            player = by_player.setdefault(standing["playerId"], {
                "playerId": standing["playerId"],
                "displayName": standing["displayName"],
                "seasonPoints": 0,
                "rounds": 0,
            })
            player["displayName"] = standing["displayName"]
            player["seasonPoints"] += standing["weekendPoints"]
            player["rounds"] += 1

    standings = ranked(list(by_player.values()), "seasonPoints")
    for standing in standings:
        standing["averagePoints"] = round(standing["seasonPoints"] / standing["rounds"])
    return {
        "schemaVersion": 1,
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
