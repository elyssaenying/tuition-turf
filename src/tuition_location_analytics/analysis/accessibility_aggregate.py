from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any


def threshold_cases(config: dict[str, Any]) -> list[dict[str, Any]]:
    primary = config["primary_scenario"]
    pt_primary = int(primary["public_transport_threshold_minutes"])
    walk_primary = int(primary["walking_threshold_minutes"])
    cases = [
        {"threshold_case_id": f"pt{pt_primary}_walk{walk_primary}_primary", "pt_minutes": pt_primary, "walk_minutes": walk_primary, "is_primary": True}
    ]
    for value in config["sensitivity_scenarios"]["public_transport_threshold_minutes"]:
        cases.append({"threshold_case_id": f"pt{int(value)}_walk{walk_primary}", "pt_minutes": int(value), "walk_minutes": walk_primary, "is_primary": False})
    for value in config["sensitivity_scenarios"]["walking_threshold_minutes"]:
        cases.append({"threshold_case_id": f"pt{pt_primary}_walk{int(value)}", "pt_minutes": pt_primary, "walk_minutes": int(value), "is_primary": False})
    if len({case["threshold_case_id"] for case in cases}) != len(cases):
        raise ValueError("accessibility threshold case identifiers are not unique")
    return cases


def _outcome_index(outcomes: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in outcomes:
        key = (str(row["od_plan_id"]), str(row["method"]))
        if key in indexed:
            raise ValueError(f"duplicate route outcome: {key[0]} {key[1]}")
        indexed[key] = row
    return indexed


def aggregate_accessibility(
    plan_rows: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    *,
    proximity_fallback_metres: float,
) -> list[dict[str, Any]]:
    if not plan_rows:
        return []
    if len({str(row["od_plan_id"]) for row in plan_rows}) != len(plan_rows):
        raise ValueError("duplicate route plan identifier")
    indexed = _outcome_index(outcomes)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in plan_rows:
        grouped[(str(row["commercial_node_id"]), str(row["scenario_id"]))].append(row)

    expected_origins = {str(row["origin_geo_id"]) for row in plan_rows}
    total_population_by_origin: dict[str, float] = {}
    for row in plan_rows:
        origin_id = str(row["origin_geo_id"])
        value = float(row["origin_target_population_proxy"])
        previous = total_population_by_origin.setdefault(origin_id, value)
        if not math.isclose(previous, value):
            raise ValueError(f"inconsistent origin population: {origin_id}")
    national_population = sum(total_population_by_origin.values())

    results: list[dict[str, Any]] = []
    for (node_id, scenario_id), rows in sorted(grouped.items()):
        if {str(row["origin_geo_id"]) for row in rows} != expected_origins:
            raise ValueError(f"incomplete origin coverage for {node_id} {scenario_id}")
        resolved: list[dict[str, Any]] = []
        for row in rows:
            od_id = str(row["od_plan_id"])
            pt = indexed.get((od_id, "pt"))
            if pt is None:
                raise ValueError(f"missing PT outcome: {od_id}")
            pt_category = str(pt["category"])
            if pt_category not in {"success", "missing_route"}:
                raise ValueError(f"non-final PT outcome {pt_category}: {od_id}")
            walk = indexed.get((od_id, "walk")) if pt_category == "missing_route" else None
            if pt_category == "missing_route" and walk is None:
                raise ValueError(f"missing walking fallback outcome: {od_id}")
            if walk is not None and str(walk["category"]) not in {"success", "missing_route", "http_error", "invalid_response"}:
                raise ValueError(f"non-final walking outcome {walk['category']}: {od_id}")
            resolved.append({"plan": row, "pt": pt, "walk": walk})

        centroid_proximity_population = sum(
            float(item["plan"]["origin_target_population_proxy"])
            for item in resolved
            if float(item["plan"]["nearest_exit_straight_line_distance_metres"]) <= proximity_fallback_metres
        )
        unresolved_population = sum(
            float(item["plan"]["origin_target_population_proxy"])
            for item in resolved
            if item["pt"]["category"] == "missing_route"
            and item["walk"] is not None
            and item["walk"]["category"] != "success"
        )
        route_complete = unresolved_population == 0

        for case in cases:
            pt_seconds = float(case["pt_minutes"]) * 60
            walk_seconds = float(case["walk_minutes"]) * 60
            pt_population = sum(
                float(item["plan"]["origin_target_population_proxy"])
                for item in resolved
                if item["pt"]["category"] == "success"
                and item["pt"]["duration_seconds"] is not None
                and float(item["pt"]["duration_seconds"]) <= pt_seconds
            )
            walk_population = sum(
                float(item["plan"]["origin_target_population_proxy"])
                for item in resolved
                if item["pt"]["category"] == "missing_route"
                and item["walk"] is not None
                and item["walk"]["category"] == "success"
                and item["walk"]["duration_seconds"] is not None
                and float(item["walk"]["duration_seconds"]) <= walk_seconds
            )
            accessible = pt_population + walk_population if route_complete else None
            results.append(
                {
                    "commercial_node_id": node_id,
                    "node_name": rows[0]["node_name"],
                    "scenario_id": scenario_id,
                    "threshold_case_id": case["threshold_case_id"],
                    "is_primary_threshold_case": bool(case["is_primary"]),
                    "pt_threshold_minutes": int(case["pt_minutes"]),
                    "walking_fallback_threshold_minutes": int(case["walk_minutes"]),
                    "accessible_target_population_proxy": accessible,
                    "pt_accessible_population_proxy": pt_population,
                    "walking_fallback_accessible_population_proxy": walk_population,
                    "centroid_proximity_population_proxy_800m": centroid_proximity_population,
                    "transit_reach_share": accessible / national_population if accessible is not None and national_population > 0 else None,
                    "national_target_population_proxy": national_population,
                    "origin_count": len(rows),
                    "pt_success_count": sum(item["pt"]["category"] == "success" for item in resolved),
                    "pt_missing_route_count": sum(item["pt"]["category"] == "missing_route" for item in resolved),
                    "walking_fallback_success_count": sum(item["walk"] is not None and item["walk"]["category"] == "success" for item in resolved),
                    "unresolved_route_population_proxy": unresolved_population,
                    "route_coverage_complete": route_complete,
                }
            )
    return results


def _average_descending_ranks(values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    ranks: dict[str, float] = {}
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and math.isclose(ordered[end][1], ordered[index][1]):
            end += 1
        average_rank = ((index + 1) + end) / 2
        for key, _ in ordered[index:end]:
            ranks[key] = average_rank
        index = end
    return ranks


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = statistics.mean(left)
    right_mean = statistics.mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    left_sq = sum((x - left_mean) ** 2 for x in left)
    right_sq = sum((y - right_mean) ** 2 for y in right)
    if left_sq == 0 or right_sq == 0:
        return None
    return numerator / math.sqrt(left_sq * right_sq)


def evaluate_h2(
    metrics: list[dict[str, Any]],
    *,
    primary_scenario_id: str,
    materiality_threshold: float,
) -> dict[str, Any]:
    selected = [
        row
        for row in metrics
        if row["scenario_id"] == primary_scenario_id and row["is_primary_threshold_case"]
    ]
    if not selected:
        raise ValueError("no primary accessibility metrics for H2")
    if any(row["accessible_target_population_proxy"] is None for row in selected):
        raise ValueError("H2 cannot run with incomplete accessibility metrics")
    valid = [row for row in selected if float(row["centroid_proximity_population_proxy_800m"] or 0) > 0]
    differences = [
        abs(float(row["accessible_target_population_proxy"]) - float(row["centroid_proximity_population_proxy_800m"]))
        / float(row["centroid_proximity_population_proxy_800m"])
        for row in valid
    ]
    transit_values = {str(row["commercial_node_id"]): float(row["accessible_target_population_proxy"]) for row in valid}
    proximity_values = {str(row["commercial_node_id"]): float(row["centroid_proximity_population_proxy_800m"]) for row in valid}
    transit_ranks = _average_descending_ranks(transit_values)
    proximity_ranks = _average_descending_ranks(proximity_values)
    ids = sorted(transit_values)
    correlation = _pearson([transit_ranks[key] for key in ids], [proximity_ranks[key] for key in ids])
    moved = sum(abs(transit_ranks[key] - proximity_ranks[key]) >= 10 for key in ids)
    median_difference = statistics.median(differences) if differences else None
    return {
        "hypothesis": "H2_transit_aware_differs_from_straight_line",
        "primary_scenario_id": primary_scenario_id,
        "valid_node_count": len(valid),
        "excluded_zero_or_null_proximity_denominator_count": len(selected) - len(valid),
        "median_node_absolute_percentage_difference": median_difference,
        "materiality_threshold": materiality_threshold,
        "material_difference": bool(median_difference is not None and median_difference >= materiality_threshold),
        "spearman_rank_correlation": correlation,
        "nodes_moving_at_least_10_ranks_count": moved,
        "share_nodes_moving_at_least_10_ranks": moved / len(ids) if ids else None,
    }
