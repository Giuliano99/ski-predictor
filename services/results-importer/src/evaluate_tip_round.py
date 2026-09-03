"""Evaluate one local tip submission against normalized official race results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


POINTS_BY_DISTANCE = (100, 80, 60, 40, 20)
CLASSIFIED = "CLASSIFIED"
DNS = "DNS"
LAST_PLACE_STATUSES = {"DNF", "DSQ"}


def distance_points(distance: int) -> int:
    return POINTS_BY_DISTANCE[distance] if 0 <= distance < len(POINTS_BY_DISTANCE) else 0


def build_outcomes(tip_round: dict[str, Any], result_documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    athlete_by_start: dict[tuple[str, int], str] = {}
    for athlete in tip_round["athletes"]:
        for start in athlete.get("starts", []):
            athlete_by_start[(start["raceId"], start["startNumber"])] = athlete["id"]

    outcomes: list[dict[str, Any]] = []
    for result in result_documents:
        race_id = result["raceId"]
        for group in result["groups"]:
            winner = group.get("winnerTimeSeconds")
            slowest = group.get("slowestClassifiedTimeSeconds")
            penalty_time = max(winner * 1.30, slowest * 1.05) if winner and slowest else None
            classified_ranks = [entry["rank"] for entry in group["entries"] if entry.get("status") == CLASSIFIED and entry.get("rank") is not None]
            last_place_rank = max(classified_ranks, default=0) + 1
            for entry in group["entries"]:
                athlete_id = athlete_by_start.get((race_id, entry["startNumber"]))
                if not athlete_id:
                    continue
                status = entry["status"]
                effective_gap = entry.get("percentageGap")
                if status in LAST_PLACE_STATUSES and penalty_time and winner:
                    effective_gap = (penalty_time - winner) / winner * 100
                outcomes.append({
                    "athleteId": athlete_id,
                    "raceId": race_id,
                    "resultGroupId": group["id"],
                    "status": status,
                    "rank": entry.get("rank"),
                    "effectiveRank": entry.get("rank") if status == CLASSIFIED else last_place_rank if status in LAST_PLACE_STATUSES else None,
                    "officialTimeSeconds": entry.get("officialTimeSeconds"),
                    "percentageGap": entry.get("percentageGap"),
                    "effectivePercentageGap": effective_gap,
                    "penaltyApplied": status in LAST_PLACE_STATUSES and effective_gap is not None,
                })
    return outcomes


def scoped_outcomes(question: dict[str, Any], outcomes: list[dict[str, Any]], include_dns: bool = False) -> list[dict[str, Any]]:
    race_ids = set(question["raceIds"])
    athlete_ids = set(question.get("athleteIds", []))
    if question.get("athleteId"):
        athlete_ids.add(question["athleteId"])
    return [
        outcome for outcome in outcomes
        if outcome["raceId"] in race_ids
        and (not athlete_ids or outcome["athleteId"] in athlete_ids)
        and (include_dns or outcome["status"] != DNS)
    ]


def dns_only_athletes(outcomes: list[dict[str, Any]]) -> set[str]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for outcome in outcomes:
        grouped.setdefault(outcome["athleteId"], []).append(outcome)
    return {athlete_id for athlete_id, values in grouped.items() if values and all(value["status"] == DNS for value in values)}


def best_by_athlete(outcomes: list[dict[str, Any]], metric: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for outcome in outcomes:
        grouped.setdefault(outcome["athleteId"], []).append(outcome)

    selected: dict[str, dict[str, Any]] = {}
    for athlete_id, athlete_outcomes in grouped.items():
        if metric == "LOWEST_PERCENTAGE_GAP":
            eligible = [outcome for outcome in athlete_outcomes if outcome["effectivePercentageGap"] is not None]
            if eligible:
                selected[athlete_id] = min(eligible, key=lambda outcome: (
                    outcome["status"] != CLASSIFIED,
                    outcome["effectivePercentageGap"],
                ))
        else:
            selected[athlete_id] = min(
                athlete_outcomes,
                key=lambda outcome: (
                    outcome["status"] != CLASSIFIED,
                    outcome["effectiveRank"] if outcome["effectiveRank"] is not None else 10_000,
                    outcome["effectivePercentageGap"] if outcome["effectivePercentageGap"] is not None else 10_000,
                ),
            )
    return selected


def outcome_order_key(outcome: dict[str, Any], metric: str) -> tuple[Any, ...]:
    if outcome["status"] in LAST_PLACE_STATUSES:
        return (1,)
    if metric == "LOWEST_PERCENTAGE_GAP":
        return (0, outcome["effectivePercentageGap"] if outcome["effectivePercentageGap"] is not None else 10_000)
    return (
        0,
        outcome["effectiveRank"] if outcome["effectiveRank"] is not None else 10_000,
        outcome["effectivePercentageGap"] if outcome["effectivePercentageGap"] is not None else 10_000,
    )


def ranked_athlete_groups(question: dict[str, Any], outcomes: list[dict[str, Any]], metric: str) -> tuple[list[list[str]], dict[str, dict[str, Any]]]:
    selected = best_by_athlete(scoped_outcomes(question, outcomes), metric)
    grouped: dict[tuple[Any, ...], list[str]] = {}
    for athlete_id, outcome in selected.items():
        grouped.setdefault(outcome_order_key(outcome, metric), []).append(athlete_id)
    groups = [sorted(grouped[key]) for key in sorted(grouped)]
    return groups, selected


def flatten_groups(groups: list[list[str]]) -> list[str]:
    return [athlete_id for group in groups for athlete_id in group]


def groups_through_position(groups: list[list[str]], positions: int) -> list[list[str]]:
    selected: list[list[str]] = []
    occupied = 0
    for group in groups:
        if occupied >= positions:
            break
        selected.append(group)
        occupied += len(group)
    return selected


def has_classified(selected: dict[str, dict[str, Any]]) -> bool:
    return any(outcome["status"] == CLASSIFIED for outcome in selected.values())


def rank_distance(athlete_id: str, predicted_position: int, groups: list[list[str]]) -> int | None:
    first_position = 0
    for group in groups:
        last_position = first_position + len(group) - 1
        if athlete_id in group:
            if first_position <= predicted_position <= last_position:
                return 0
            return min(abs(predicted_position - first_position), abs(predicted_position - last_position))
        first_position = last_position + 1
    return None


def actual_for_question(question: dict[str, Any], outcomes: list[dict[str, Any]]) -> Any:
    metric = question["evaluationMetric"]
    raw_scoped = scoped_outcomes(question, outcomes, include_dns=True)
    scoped = scoped_outcomes(question, outcomes)
    dns_athletes = sorted(dns_only_athletes(raw_scoped))
    if metric == "PODIUM_COUNT":
        return sum(outcome["status"] == CLASSIFIED and outcome["rank"] <= 3 for outcome in scoped)
    if metric == "TOP_N_COUNT":
        threshold = question.get("threshold", 10)
        return sum(outcome["status"] == CLASSIFIED and outcome["rank"] <= threshold for outcome in scoped)
    if metric == "CLASSIFIED_COUNT":
        return sum(outcome["status"] == CLASSIFIED for outcome in scoped)
    if metric in {"BEST_RESULT", "LOWEST_PERCENTAGE_GAP"}:
        groups, selected = ranked_athlete_groups(question, outcomes, metric)
        if not groups or not has_classified(selected):
            return None
        ranking = flatten_groups(groups)
        unclassified = [athlete_id for athlete_id, outcome in selected.items() if outcome["status"] != CLASSIFIED]
        return {"winner": ranking[0], "winners": groups[0], "ranking": ranking, "rankGroups": groups, "unclassified": sorted(unclassified), "dns": dns_athletes}
    if metric == "EXACT_PLACEMENT":
        selected = best_by_athlete(scoped, "BEST_RESULT")
        if not selected:
            return None
        outcome = next(iter(selected.values()))
        return outcome.get("effectiveRank")
    if metric == "DIRECT_COMPARISON":
        selected = best_by_athlete(scoped, "BEST_RESULT")
        if len(selected) != len(question.get("athleteIds", [])) or not has_classified(selected):
            return None
        groups, _ = ranked_athlete_groups(question, outcomes, "BEST_RESULT")
        return groups[0][0] if len(groups[0]) == 1 else None
    if metric == "INTERNAL_ORDER":
        groups, selected = ranked_athlete_groups(question, outcomes, "BEST_RESULT")
        if not groups or not has_classified(selected):
            return None
        relevant_groups = groups_through_position(groups, question["positions"])
        ranking = flatten_groups(relevant_groups)[:question["positions"]]
        unclassified = [athlete_id for athlete_id, outcome in selected.items() if outcome["status"] != CLASSIFIED]
        return {"ranking": ranking, "rankGroups": relevant_groups, "unclassified": sorted(unclassified), "dns": dns_athletes}
    if metric == "PODIUM_ORDER":
        groups, selected = ranked_athlete_groups(question, outcomes, "LOWEST_PERCENTAGE_GAP")
        if not groups or not has_classified(selected):
            return None
        relevant_groups = groups_through_position(groups, question["positions"])
        return {
            "ranking": flatten_groups(relevant_groups)[:question["positions"]],
            "rankGroups": relevant_groups,
            "unclassified": sorted(athlete_id for athlete_id, outcome in selected.items() if outcome["status"] != CLASSIFIED),
            "dns": dns_athletes,
        }
    raise ValueError(f"Unsupported evaluation metric: {metric}")


def score_question(question: dict[str, Any], submitted: Any, actual: Any) -> tuple[str, int]:
    if actual is None or (isinstance(actual, list) and not actual):
        return "ANNULLED", 0
    if submitted in (None, "", []):
        return "SCORED", 0

    metric = question["evaluationMetric"]
    if metric in {"PODIUM_COUNT", "TOP_N_COUNT", "CLASSIFIED_COUNT", "EXACT_PLACEMENT"}:
        return "SCORED", distance_points(abs(int(submitted) - int(actual)))
    if metric in {"BEST_RESULT", "LOWEST_PERCENTAGE_GAP"}:
        distance = rank_distance(submitted, 0, actual["rankGroups"])
        return "SCORED", distance_points(distance) if distance is not None else 0
    if metric == "DIRECT_COMPARISON":
        return "SCORED", 100 if submitted == actual else 0
    if metric == "INTERNAL_ORDER":
        filtered_submission = [athlete_id for athlete_id in submitted if athlete_id not in set(actual.get("dns", []))]
        if not filtered_submission:
            return "ANNULLED", 0
        values = []
        for index, athlete_id in enumerate(filtered_submission):
            distance = rank_distance(athlete_id, index, actual["rankGroups"])
            values.append(distance_points(distance) if distance is not None else 0)
        return "SCORED", round(sum(values) / len(values)) if values else 0
    if metric == "PODIUM_ORDER":
        filtered_submission = [athlete_id for athlete_id in submitted if athlete_id not in set(actual.get("dns", []))]
        if not filtered_submission:
            return "ANNULLED", 0
        actual_set = set(flatten_groups(actual["rankGroups"]))
        values = []
        for index, athlete_id in enumerate(filtered_submission):
            distance = rank_distance(athlete_id, index, actual["rankGroups"])
            values.append(100 if distance == 0 else 60 if athlete_id in actual_set else 0)
        return "SCORED", round(sum(values) / len(values)) if values else 0
    raise ValueError(f"Unsupported evaluation metric: {metric}")


def evaluate(tip_round: dict[str, Any], result_documents: list[dict[str, Any]], submission: dict[str, Any]) -> dict[str, Any]:
    validate_submission(tip_round, submission)
    result_race_ids = {result["raceId"] for result in result_documents if result.get("official")}
    required_race_ids = {race["id"] for race in tip_round["races"]}
    missing = required_race_ids - result_race_ids
    if missing:
        raise ValueError(f"Missing official results for races: {sorted(missing)}")

    outcomes = build_outcomes(tip_round, result_documents)
    evaluations: list[dict[str, Any]] = []
    for question in tip_round["questions"]:
        actual = actual_for_question(question, outcomes)
        submitted = submission.get("answers", {}).get(question["id"])
        status, points = score_question(question, submitted, actual)
        evaluations.append({
            "questionId": question["id"],
            "status": status,
            "submittedAnswer": submitted,
            "actualAnswer": actual,
            "points": points,
            "maximumPoints": 0 if status == "ANNULLED" else 100,
        })

    scored = [item for item in evaluations if item["status"] != "ANNULLED"]
    earned = sum(item["points"] for item in scored)
    maximum = sum(item["maximumPoints"] for item in scored)
    weekend_points = round(earned / maximum * 1000) if maximum else 0
    return {
        "schemaVersion": 1,
        "tipRoundId": tip_round["id"],
        "tipRoundVersion": tip_round["contentVersion"],
        "submissionId": submission.get("id", "local-submission"),
        "testFixture": submission.get("id") == "perfect-fixture-submission",
        "questionEvaluations": evaluations,
        "rawPoints": earned,
        "maximumRawPoints": maximum,
        "weekendPoints": weekend_points,
    }


def validate_submission(tip_round: dict[str, Any], submission: dict[str, Any]) -> None:
    if not submission.get("id"):
        raise ValueError("Submission is missing an id")
    if submission.get("tipRoundId") != tip_round["id"]:
        raise ValueError(f"Submission belongs to tip round {submission.get('tipRoundId')!r}, expected {tip_round['id']!r}")
    expected_version = tip_round.get("contentVersion")
    if not expected_version:
        raise ValueError("Tip round is missing its content version")
    if submission.get("tipRoundVersion") != expected_version:
        raise ValueError(
            f"Submission has content version {submission.get('tipRoundVersion')!r}, expected {expected_version!r}"
        )
    player = submission.get("player")
    if submission.get("id") != "perfect-fixture-submission" and (
        not isinstance(player, dict) or not player.get("id") or not player.get("displayName")
    ):
        raise ValueError("Submission is missing player information")
    answers = submission.get("answers")
    if not isinstance(answers, dict):
        raise ValueError("Submission answers must be an object")

    questions = {question["id"]: question for question in tip_round["questions"]}
    missing = set(questions) - set(answers)
    unexpected = set(answers) - set(questions)
    if missing:
        raise ValueError(f"Submission is missing answers for: {sorted(missing)}")
    if unexpected:
        raise ValueError(f"Submission contains unknown answers for: {sorted(unexpected)}")

    for question_id, question in questions.items():
        answer = answers[question_id]
        if question["type"] in {"NUMBER", "PLACEMENT"}:
            try:
                numeric_answer = int(answer)
            except (TypeError, ValueError) as error:
                raise ValueError(f"Answer for {question_id!r} must be an integer") from error
            minimum = question.get("minimum")
            maximum = question.get("maximum")
            if (minimum is not None and numeric_answer < minimum) or (maximum is not None and numeric_answer > maximum):
                raise ValueError(f"Answer for {question_id!r} is outside the allowed range")
        elif question["type"] in {"ATHLETE", "HEAD_TO_HEAD"}:
            if answer not in question["athleteIds"]:
                raise ValueError(f"Answer for {question_id!r} is not an eligible athlete")
        elif question["type"] in {"INTERNAL_RANKING", "PODIUM"}:
            if not isinstance(answer, list) or len(answer) != question["positions"] or len(set(answer)) != len(answer):
                raise ValueError(f"Answer for {question_id!r} must contain {question['positions']} unique athletes")
            if any(athlete_id not in question["athleteIds"] for athlete_id in answer):
                raise ValueError(f"Answer for {question_id!r} contains an ineligible athlete")


def perfect_fixture_submission(tip_round: dict[str, Any], result_documents: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes = build_outcomes(tip_round, result_documents)
    answers: dict[str, Any] = {}
    for question in tip_round["questions"]:
        actual = actual_for_question(question, outcomes)
        if isinstance(actual, dict) and "winner" in actual:
            answers[question["id"]] = actual["winner"]
        elif isinstance(actual, dict) and "ranking" in actual:
            answers[question["id"]] = actual["ranking"]
        else:
            answers[question["id"]] = actual
    return {"id": "perfect-fixture-submission", "tipRoundId": tip_round["id"], "tipRoundVersion": tip_round["contentVersion"], "answers": answers}


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tip_round", type=Path)
    parser.add_argument("results", nargs="+", type=Path)
    parser.add_argument("--submission", type=Path)
    parser.add_argument("--perfect-fixture", action="store_true", help="Test only: derive a submission containing every official answer")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)

    tip_round = json.loads(arguments.tip_round.read_text(encoding="utf-8"))
    result_documents = [json.loads(path.read_text(encoding="utf-8")) for path in arguments.results]
    if bool(arguments.submission) == bool(arguments.perfect_fixture):
        parser.error("use exactly one of --submission or --perfect-fixture")
    submission = json.loads(arguments.submission.read_text(encoding="utf-8")) if arguments.submission else perfect_fixture_submission(tip_round, result_documents)
    evaluation = evaluate(tip_round, result_documents, submission)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"tipRoundId": evaluation["tipRoundId"], "questions": len(evaluation["questionEvaluations"]), "weekendPoints": evaluation["weekendPoints"], "output": str(arguments.output) if arguments.output else None}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
