"""Transparent DSV U14/U16 season-points projection."""

from __future__ import annotations

from typing import Any


MAXIMUM_START_POINTS = 9999.0


def race_discipline(race: dict[str, Any]) -> str | None:
    discipline = str(race.get("discipline") or "").upper()
    code = str(race.get("competitionNumber") or "").upper()
    if discipline == "SL" or code.endswith("MSBS"):
        return "SL"
    if discipline == "GS" or code.endswith("MRBR"):
        return "GS"
    return None


def improvement_points(base_points: float, best_sl: float | None, best_gs: float | None) -> tuple[float, str]:
    candidates: list[tuple[float, str]] = [(base_points, "BAS")]
    if best_sl is not None:
        candidates.extend([((base_points + best_sl) / 2, "0,5 × (BAS + SLbest)"), (best_sl + 30, "SLbest + 30")])
    if best_gs is not None:
        candidates.extend([((base_points + best_gs) / 2, "0,5 × (BAS + RSbest)"), (best_gs + 30, "RSbest + 30")])
    if best_sl is not None and best_gs is not None:
        candidates.append(((best_sl + best_gs) / 2, "0,5 × (SLbest + RSbest)"))
    value, formula = min(candidates, key=lambda item: item[0])
    return round(value, 2), formula


def end_list_points(base_points: float, best_sl: float | None, best_gs: float | None) -> tuple[float, str]:
    if best_sl is not None and best_gs is not None:
        return round((best_sl + best_gs) / 2, 2), "0,5 × (SLbest + RSbest)"
    if best_sl is not None:
        return round(best_sl + 30, 2), "SLbest + 30"
    if best_gs is not None:
        return round(best_gs + 30, 2), "RSbest + 30"
    return round(base_points + 30, 2), "BAS + 30"


def season_projection(base_points: float, results: list[dict[str, Any]]) -> dict[str, Any]:
    best: dict[str, float | None] = {"SL": None, "GS": None}
    history: list[dict[str, Any]] = []
    eligible = sorted(results, key=lambda item: (item.get("race", {}).get("date") or "", item.get("race", {}).get("id") or ""))
    for result in eligible:
        discipline = race_discipline(result.get("race", {}))
        points = result.get("federationPoints")
        if discipline not in best or result.get("status") != "CLASSIFIED" or not isinstance(points, (int, float)):
            continue
        best[discipline] = float(points) if best[discipline] is None else min(float(best[discipline]), float(points))
        overall, formula = improvement_points(base_points, best["SL"], best["GS"])
        history.append({
            "raceId": result.get("race", {}).get("id"),
            "date": result.get("race", {}).get("date"),
            "discipline": discipline,
            "racePoints": round(float(points), 2),
            "slalomPoints": round(min(base_points, best["SL"]), 2) if best["SL"] is not None else round(base_points, 2),
            "giantSlalomPoints": round(min(base_points, best["GS"]), 2) if best["GS"] is not None else round(base_points, 2),
            "overallPoints": overall,
            "formula": formula,
        })
    overall, formula = improvement_points(base_points, best["SL"], best["GS"])
    final_points, final_formula = end_list_points(base_points, best["SL"], best["GS"])
    return {
        "basePoints": round(base_points, 2),
        "slalomPoints": round(min(base_points, best["SL"]), 2) if best["SL"] is not None else round(base_points, 2),
        "giantSlalomPoints": round(min(base_points, best["GS"]), 2) if best["GS"] is not None else round(base_points, 2),
        "bestSlalomResult": round(best["SL"], 2) if best["SL"] is not None else None,
        "bestGiantSlalomResult": round(best["GS"], 2) if best["GS"] is not None else None,
        "overallPoints": overall,
        "overallFormula": formula,
        "projectedEndListPoints": final_points,
        "projectedEndListFormula": final_formula,
        "history": history,
    }
