"""Evaluate one local tip submission against normalized official race results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


POINTS_BY_DISTANCE = (100, 80, 60, 40, 20)
CLASSIFIED = "CLASSIFIED"


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
            for entry in group["entries"]:
                athlete_id = athlete_by_start.get((race_id, entry["startNumber"]))
                if not athlete_id:
                    continue
                effective_gap = entry.get("percentageGap")
                if entry["status"] != CLASSIFIED and penalty_time and winner:
                    effective_gap = (penalty_time - winner) / winner * 100
                outcomes.append({
                    "athleteId": athlete_id,
                    "raceId": race_id,
                    "resultGroupId": group["id"],
                    "status": entry["status"],
                    "rank": entry.get("rank"),
                    "officialTimeSeconds": entry.get("officialTimeSeconds"),
                    "percentageGap": entry.get("percentageGap"),
                    "effectivePercentageGap": effective_gap,
                    "penaltyApplied": entry["status"] != CLASSIFIED and effective_gap is not None,
                })
    return outcomes


def scoped_outcomes(question: dict[str, Any], outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    race_ids = set(question["raceIds"])
    athlete_ids = set(question.get("athleteIds", []))
    if question.get("athleteId"):
        athlete_ids.add(question["athleteId"])
    return [
        outcome for outcome in outcomes
        if outcome["raceId"] in race_ids and (not athlete_ids or outcome["athleteId"] in athlete_ids)
    ]


def best_by_athlete(outcomes: list[dict[str, Any]], metric: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for outcome in outcomes:
        grouped.setdefault(outcome["athleteId"], []).append(outcome)

    selected: dict[str, dict[str, Any]] = {}
    for athlete_id, athlete_outcomes in grouped.items():
        if metric == "LOWEST_PERCENTAGE_GAP":
            eligible = [outcome for outcome in athlete_outcomes if outcome["effectivePercentageGap"] is not None]
            if eligible:
                selected[athlete_id] = min(eligible, key=lambda outcome: outcome["effectivePercentageGap"])
        else:
            selected[athlete_id] = min(
                athlete_outcomes,
                key=lambda outcome: (
                    outcome["status"] != CLASSIFIED,
                    outcome["rank"] if outcome["rank"] is not None else 10_000,
                    outcome["effectivePercentageGap"] if outcome["effectivePercentageGap"] is not None else 10_000,
                ),
            )
    return selected


def ordered_athletes(question: dict[str, Any], outcomes: list[dict[str, Any]], metric: str, classified_only: bool = False) -> list[str]:
    selected = best_by_athlete(scoped_outcomes(question, outcomes), metric)
    values = list(selected.values())
    if classified_only:
        values = [outcome for outcome in values if outcome["status"] == CLASSIFIED]
    if metric == "LOWEST_PERCENTAGE_GAP":
        values.sort(key=lambda outcome: outcome["effectivePercentageGap"] if outcome["effectivePercentageGap"] is not None else 10_000)
    else:
        values.sort(key=lambda outcome: (
            outcome["status"] != CLASSIFIED,
            outcome["rank"] if outcome["rank"] is not None else 10_000,
            outcome["effectivePercentageGap"] if outcome["effectivePercentageGap"] is not None else 10_000,
        ))
    return [outcome["athleteId"] for outcome in values]


def actual_for_question(question: dict[str, Any], outcomes: list[dict[str, Any]]) -> Any:
    metric = question["evaluationMetric"]
    scoped = scoped_outcomes(question, outcomes)
    if metric == "PODIUM_COUNT":
        return sum(outcome["status"] == CLASSIFIED and outcome["rank"] <= 3 for outcome in scoped)
    if metric == "TOP_N_COUNT":
        threshold = question.get("threshold", 10)
        return sum(outcome["status"] == CLASSIFIED and outcome["rank"] <= threshold for outcome in scoped)
    if metric == "CLASSIFIED_COUNT":
        return sum(outcome["status"] == CLASSIFIED for outcome in scoped)
    if metric in {"BEST_RESULT", "LOWEST_PERCENTAGE_GAP"}:
        ranking = ordered_athletes(question, outcomes, metric)
        if not ranking:
            return None
        unclassified = [outcome["athleteId"] for outcome in scoped if outcome["status"] != CLASSIFIED]
        return {"winner": ranking[0], "ranking": ranking, "unclassified": list(dict.fromkeys(unclassified))}
    if metric == "EXACT_PLACEMENT":
        classified = [outcome for outcome in scoped if outcome["status"] == CLASSIFIED and outcome["rank"] is not None]
        return min((outcome["rank"] for outcome in classified), default=None)
    if metric == "DIRECT_COMPARISON":
        ranking = ordered_athletes(question, outcomes, "BEST_RESULT")
        classified_ids = [athlete_id for athlete_id in ranking if any(outcome["athleteId"] == athlete_id and outcome["status"] == CLASSIFIED for outcome in scoped)]
        return classified_ids[0] if classified_ids else None
    if metric == "INTERNAL_ORDER":
        ranking = ordered_athletes(question, outcomes, "BEST_RESULT")[:question["positions"]]
        unclassified = [outcome["athleteId"] for outcome in scoped if outcome["status"] != CLASSIFIED]
        return {"ranking": ranking, "unclassified": list(dict.fromkeys(unclassified))}
    if metric == "PODIUM_ORDER":
        return ordered_athletes(question, outcomes, "LOWEST_PERCENTAGE_GAP", classified_only=True)[:question["positions"]]
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
        ranking = actual["ranking"]
        if metric == "BEST_RESULT" and submitted in actual.get("unclassified", []):
            return "SCORED", 0
        return "SCORED", distance_points(ranking.index(submitted)) if submitted in ranking else 0
    if metric == "DIRECT_COMPARISON":
        return "SCORED", 100 if submitted == actual else 0
    if metric == "INTERNAL_ORDER":
        ranking = actual["ranking"]
        unclassified = set(actual.get("unclassified", []))
        position_by_athlete = {athlete_id: index for index, athlete_id in enumerate(ranking)}
        values = [distance_points(abs(index - position_by_athlete[athlete_id])) if athlete_id in position_by_athlete and athlete_id not in unclassified else 0 for index, athlete_id in enumerate(submitted)]
        return "SCORED", round(sum(values) / len(values)) if values else 0
    if metric == "PODIUM_ORDER":
        actual_set = set(actual)
        values = [100 if index < len(actual) and athlete_id == actual[index] else 60 if athlete_id in actual_set else 0 for index, athlete_id in enumerate(submitted)]
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
    return {"id": "perfect-fixture-submission", "tipRoundId": tip_round["id"], "answers": answers}


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
