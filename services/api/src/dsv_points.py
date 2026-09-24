"""Transparent DSV U14/U16 season-points projection."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


MAXIMUM_START_POINTS = 999.0
SEASON_BASE_CORRECTIONS = {
    "2025-2026": {"FEMALE": -10.44, "MALE": -5.78},
    "2026-2027": {"FEMALE": 4.91, "MALE": -3.06},
}


def round_points(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def average_points(left: float, right: float) -> float:
    return float((Decimal(str(left)) + Decimal(str(right))) / Decimal("2"))


def adjusted_season_base(previous_end_points: float, season_id: str, gender: str) -> tuple[float, float]:
    correction = SEASON_BASE_CORRECTIONS.get(season_id, {}).get(gender)
    if correction is None:
        raise ValueError(f"Kein DSV-Korrekturwert für {season_id} / {gender} hinterlegt")
    adjusted = Decimal(str(previous_end_points)) + Decimal(str(correction))
    return round_points(float(adjusted)), correction


def race_discipline(race: dict[str, Any]) -> str | None:
    discipline = str(race.get("discipline") or "").upper()
    code = str(race.get("competitionNumber") or "").upper()
    if discipline == "SL" or code.endswith("MSBS"):
        return "SL"
    if discipline == "GS" or code.endswith("MRBR"):
        return "GS"
    return None


def improvement_candidates(base_points: float, best_sl: float | None, best_gs: float | None) -> list[dict[str, Any]]:
    candidates: list[tuple[float, str]] = [(base_points, "BAS")]
    if best_sl is not None:
        candidates.extend([(average_points(base_points, best_sl), "0,5 × (BAS + SLbest)"), (best_sl + 30, "SLbest + 30")])
    if best_gs is not None:
        candidates.extend([(average_points(base_points, best_gs), "0,5 × (BAS + RSbest)"), (best_gs + 30, "RSbest + 30")])
    if best_sl is not None and best_gs is not None:
        candidates.append((average_points(best_sl, best_gs), "0,5 × (SLbest + RSbest)"))
    selected_value, selected_formula = min(candidates, key=lambda item: item[0])
    return [
        {"formula": formula, "value": round_points(value), "selected": formula == selected_formula}
        for value, formula in candidates
    ]


def improvement_points(base_points: float, best_sl: float | None, best_gs: float | None) -> tuple[float, str]:
    selected = next(item for item in improvement_candidates(base_points, best_sl, best_gs) if item["selected"])
    return selected["value"], selected["formula"]


def end_list_points(base_points: float, best_sl: float | None, best_gs: float | None) -> tuple[float, str]:
    candidates: list[tuple[float, str]] = []
    if best_sl is not None and best_gs is not None:
        candidates.append((average_points(best_sl, best_gs), "0,5 × (SLbest + RSbest)"))
    if best_sl is not None:
        candidates.append((best_sl + 30, "SLbest + 30"))
    if best_gs is not None:
        candidates.append((best_gs + 30, "RSbest + 30"))
    if not candidates:
        candidates.append((base_points + 30, "BAS + 30"))
    value, formula = min(candidates, key=lambda item: item[0])
    return round_points(value), formula


def season_start_date(season_id: str | None) -> str | None:
    if not season_id:
        return None
    try:
        return f"{int(season_id.split('-')[1]):04d}-01-01"
    except (IndexError, TypeError, ValueError):
        return None


def season_projection(base_points: float, results: list[dict[str, Any]], season_id: str | None = None) -> dict[str, Any]:
    best: dict[str, float | None] = {"SL": None, "GS": None}
    start_date = season_start_date(season_id)
    history: list[dict[str, Any]] = [] if start_date is None else [{
        "raceId": None,
        "date": start_date,
        "discipline": "BASE",
        "racePoints": None,
        "slalomPoints": None,
        "giantSlalomPoints": None,
        "overallPoints": round_points(base_points),
        "formula": "Saison-Startwert",
        "pointKind": "SEASON_START",
    }]
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
            "racePoints": round_points(float(points)),
            "slalomPoints": round_points(best["SL"]) if best["SL"] is not None else None,
            "giantSlalomPoints": round_points(best["GS"]) if best["GS"] is not None else None,
            "overallPoints": overall,
            "formula": formula,
        })
    overall, formula = improvement_points(base_points, best["SL"], best["GS"])
    final_points, final_formula = end_list_points(base_points, best["SL"], best["GS"])
    return {
        "basePoints": round_points(base_points),
        "slalomPoints": round_points(best["SL"]) if best["SL"] is not None else None,
        "giantSlalomPoints": round_points(best["GS"]) if best["GS"] is not None else None,
        "bestSlalomResult": round_points(best["SL"]) if best["SL"] is not None else None,
        "bestGiantSlalomResult": round_points(best["GS"]) if best["GS"] is not None else None,
        "overallPoints": overall,
        "overallFormula": formula,
        "formulaCandidates": improvement_candidates(base_points, best["SL"], best["GS"]),
        "projectedEndListPoints": final_points,
        "projectedEndListFormula": final_formula,
        "history": history,
    }
