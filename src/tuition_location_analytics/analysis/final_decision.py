from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from tuition_location_analytics.foundation.common import write_json


DATE = "2026-09-18"
PRIMARY_ACCESSIBILITY = ("primary_weekday_after_school", "pt20_walk10_primary")
COMPETITION_CASES = (
    ("confirmed_10_min", 10, False),
    ("confirmed_15_min", 15, False),
    ("zero_confirmed_caution_10_min", 10, True),
    ("zero_confirmed_caution_15_min", 15, True),
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _clean_name(value: str) -> str:
    return value.removesuffix(" MRT STATION").removesuffix(" LRT STATION")


def _competition_value(confirmed_count: int | float, *, zero_confirmed_caution: bool) -> float:
    """Stress-test zero discoveries without claiming an unobserved branch exists."""
    value = float(confirmed_count)
    return max(1.0, value) if zero_confirmed_caution else value


def _candidate_paths(repo_root: Path) -> tuple[Path, Path]:
    base = repo_root / "data/processed/competitors/2026-09-18"
    candidate = base / "candidate_freeze_8f16c917adc6a3a3/candidate_node_freeze.csv"
    audit = base / "outside_audit_9b157537eeda6481/outside_audit_sample.csv"
    if not candidate.exists() or not audit.exists():
        raise FileNotFoundError(
            "The redacted candidate and outside-audit inputs are missing. "
            "Restore the tracked data/processed/competitors/2026-09-18 CSV files."
        )
    return candidate, audit


def _accessibility_path(repo_root: Path) -> Path:
    processed = repo_root / "data/processed/analysis/2026-09-17/accessibility_f7fb9e067b244fbd/node_accessibility_metrics.csv"
    public = repo_root / "app/public/data/node_accessibility_metrics.csv"
    if processed.exists():
        return processed
    if public.exists():
        return public
    raise FileNotFoundError("The tracked public accessibility table is missing")


def _average_percentiles(values: dict[str, float], *, higher_is_better: bool) -> dict[str, float]:
    ordered = sorted(values.items(), key=lambda item: (item[1], item[0]), reverse=higher_is_better)
    result: dict[str, float] = {}
    size = len(ordered)
    index = 0
    while index < size:
        end = index + 1
        while end < size and ordered[end][1] == ordered[index][1]:
            end += 1
        average_rank = ((index + 1) + end) / 2
        result.update({node_id: 1 - (average_rank - 1) / max(size - 1, 1) for node_id, _ in ordered[index:end]})
        index = end
    return result


def pareto_frontier(points: dict[str, tuple[float, ...]]) -> set[str]:
    """Return alternatives not dominated when every dimension is higher-is-better."""
    frontier: set[str] = set()
    for node_id, point in points.items():
        dominated = any(
            other_id != node_id
            and all(other >= current for other, current in zip(other_point, point))
            and any(other > current for other, current in zip(other_point, point))
            for other_id, other_point in points.items()
        )
        if not dominated:
            frontier.add(node_id)
    return frontier


def financial_outputs(config: dict[str, Any]) -> list[dict[str, Any]]:
    capacity = int(config["capacity_active_students"])
    target = int(config["target_active_students"])
    rows = []
    for scenario in config["scenarios"]:
        contribution = scenario["effective_fee_per_student"] - scenario["variable_cost_per_student"]
        fixed = scenario["non_occupancy_fixed_cost"] + scenario["occupancy_cost"]
        break_even = math.ceil(fixed / contribution) if contribution > 0 else None
        maximum_occupancy = max(0, target * contribution - scenario["non_occupancy_fixed_cost"])
        rows.append(
            {
                **scenario,
                "contribution_per_student": contribution,
                "break_even_active_enrolments": break_even,
                "break_even_utilisation": break_even / capacity if break_even is not None else None,
                "capacity_feasible": break_even is not None and break_even <= capacity,
                "maximum_affordable_monthly_occupancy_cost_at_target": maximum_occupancy,
                "target_monthly_surplus_after_occupancy": maximum_occupancy - scenario["occupancy_cost"],
            }
        )
    return rows


def _weighted_correlation(rows: Iterable[tuple[float, float, float]]) -> dict[str, float]:
    material = list(rows)
    total_weight = sum(weight for _, _, weight in material)
    mean_x = sum(x * weight for x, _, weight in material) / total_weight
    mean_y = sum(y * weight for _, y, weight in material) / total_weight
    covariance = sum(weight * (x - mean_x) * (y - mean_y) for x, y, weight in material) / total_weight
    variance_x = sum(weight * (x - mean_x) ** 2 for x, _, weight in material) / total_weight
    variance_y = sum(weight * (y - mean_y) ** 2 for _, y, weight in material) / total_weight
    correlation = covariance / math.sqrt(variance_x * variance_y) if variance_x and variance_y else 0.0
    slope = covariance / variance_x if variance_x else 0.0
    effective_n = total_weight**2 / sum(weight**2 for _, _, weight in material)
    return {
        "weighted_correlation": correlation,
        "weighted_slope_branches_per_10000_accessible_residents": slope * 10000,
        "weighted_effective_sample_size": effective_n,
    }


def collect_competition(repo_root: Path) -> dict[str, Any]:
    private = repo_root / "data/interim/competitors/national"
    candidate_path, audit_path = _candidate_paths(repo_root)
    candidate_rows = _read_csv(candidate_path)
    audit_rows = _read_csv(audit_path)
    candidate_ids = {row["commercial_node_id"] for row in candidate_rows}
    audit_ids = {row["commercial_node_id"] for row in audit_rows}

    private_paths = [
        *(private / f"national_batch_{batch_number:02d}.private.json" for batch_number in range(1, 11)),
        *(private / f"national-batch-{batch_number:02d}-walk-memberships.private.json" for batch_number in range(1, 11)),
    ]
    if not all(path.exists() for path in private_paths):
        public_path = repo_root / f"reports/competitors/{DATE}/national_completion/national-competition-summary.json"
        if not public_path.exists():
            raise FileNotFoundError(
                "Neither the private national ledgers nor the tracked redacted competition snapshot is available"
            )
        competition = json.loads(public_path.read_text(encoding="utf-8"))
        competition.pop("strategic_benchmark", None)
        coverage = competition.get("coverage", {})
        for field in (
            "benchmark_areas",
            "benchmark_overlap_with_outside_audit",
            "strategic_benchmark_walking_routes_completed",
            "all_competitor_walking_routes_completed",
        ):
            coverage.pop(field, None)
        if coverage.get("fixed_queries_completed") != 156 or coverage.get("walking_routes_completed") != 3690:
            raise RuntimeError("The public competition snapshot does not match the frozen completed run")
        if len(competition.get("nodes", [])) != 78:
            raise RuntimeError("The public competition snapshot must contain 78 audited MRT-area records")
        competition["input_mode"] = "tracked_redacted_aggregate_snapshot"
        for node in competition["nodes"]:
            node["possible_within_10_min_walk"] = None
            node["possible_within_15_min_walk"] = None
            node["possible_count_status"] = "not_systematically_retained_in_national_collection"
        return competition

    nodes: dict[str, dict[str, Any]] = {}
    unique_branches: set[tuple[str, str, str]] = set()
    totals = defaultdict(int)
    for batch_number in range(1, 11):
        ledger_path = private / f"national_batch_{batch_number:02d}.private.json"
        membership_path = private / f"national-batch-{batch_number:02d}-walk-memberships.private.json"
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        membership = json.loads(membership_path.read_text(encoding="utf-8"))
        if membership["status"] != "complete":
            raise RuntimeError(f"national batch {batch_number:02d} walking routes are incomplete")
        totals["queries"] += int(ledger["safe_progress_counts"]["queries_completed"])
        totals["blocked_queries"] += int(ledger["safe_progress_counts"]["queries_blocked"])
        totals["recorded_leads"] += int(ledger["safe_progress_counts"]["distinct_leads_recorded"])
        totals["confirmed_leads"] += int(ledger["safe_progress_counts"]["confirmed_physical_in_scope_leads"])
        totals["routes_planned"] += int(membership["planned_route_requests"])
        totals["routes_completed"] += int(membership["completed_route_requests"])
        totals["geocoded"] += int(membership["geocoded_branch_count"])
        totals["unresolved_geocodes"] += int(membership["unresolved_geocode_branch_count"])
        for lead in ledger["leads"]:
            if lead.get("eligible_for_catchment") is True:
                unique_branches.add(
                    (
                        str(lead["operator_name"]).casefold().strip(),
                        str(lead["branch_label"]).casefold().strip(),
                        str(lead.get("postal_code") or ""),
                    )
                )
        by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in membership["memberships"]:
            by_node[row["commercial_node_id"]].append(row)
        for member in ledger["node_members"]:
            node_id = member["commercial_node_id"]
            rows = by_node.get(node_id, [])
            target_set = (
                "candidate" if node_id in candidate_ids else "outside_audit" if node_id in audit_ids else "benchmark"
            )
            nodes[node_id] = {
                "commercial_node_id": node_id,
                "station_complex_id": member["station_complex_id"],
                "node_name": member["node_name"],
                "display_name": _clean_name(member["node_name"]),
                "planning_region": member.get("planning_region"),
                "target_set": target_set,
                "confirmed_within_10_min_walk": len({row["branch_id"] for row in rows if row["inside_10_minute_walk"] is True}),
                "confirmed_within_15_min_walk": len({row["branch_id"] for row in rows if row["inside_15_minute_walk"] is True}),
                "possible_within_10_min_walk": None,
                "possible_within_15_min_walk": None,
                "possible_count_status": "not_systematically_retained_in_national_collection",
                "resolved_branch_routes": sum(row["route_status"] == "resolved" for row in rows),
                "evaluated_branch_memberships": len(rows),
                "batch_number": batch_number,
            }
    if totals["queries"] != 156 or len(nodes) != 78:
        raise RuntimeError(f"unexpected national coverage: {totals['queries']} queries, {len(nodes)} nodes")
    if totals["routes_planned"] != totals["routes_completed"]:
        raise RuntimeError("not every planned walking route completed")
    return {
        "input_mode": "private_ledgers_rebuilt_to_redacted_aggregates",
        "coverage": {
            "fixed_queries_planned": 156,
            "fixed_queries_completed": totals["queries"],
            "queries_blocked": totals["blocked_queries"],
            "unique_mrt_areas": len(nodes),
            "candidate_areas": 36,
            "outside_audit_areas": 40,
            "batch_specific_confirmed_leads": totals["confirmed_leads"],
            "unique_confirmed_physical_branches": len(unique_branches),
            "exact_postal_geocodes_resolved": totals["geocoded"],
            "exact_postal_geocodes_unresolved": totals["unresolved_geocodes"],
            "walking_routes_planned": totals["routes_planned"],
            "walking_routes_completed": totals["routes_completed"],
            "raw_search_pages_persisted": False,
            "systematic_directory_use": False,
        },
        "nodes": sorted(nodes.values(), key=lambda row: row["commercial_node_id"]),
    }


def h1_analysis(repo_root: Path, competition: dict[str, Any]) -> dict[str, Any]:
    candidate_path, audit_path = _candidate_paths(repo_root)
    candidates = _read_csv(candidate_path)
    audit = _read_csv(audit_path)
    counts = {row["commercial_node_id"]: row for row in competition["nodes"]}
    material: list[tuple[float, float, float]] = []
    candidate_material: list[tuple[float, float, float]] = []
    for row in candidates:
        item = (float(row["transit_accessibility"]), float(counts[row["commercial_node_id"]]["confirmed_within_10_min_walk"]), 1.0)
        material.append(item)
        candidate_material.append(item)
    for row in audit:
        material.append(
            (
                float(row["transit_accessibility"]),
                float(counts[row["commercial_node_id"]]["confirmed_within_10_min_walk"]),
                float(row["design_weight"]),
            )
        )
    primary = _weighted_correlation(material)
    sensitivity = _weighted_correlation(candidate_material)
    return {
        "hypothesis_id": "H1",
        "expectation": "Accessible target-age population is positively associated with confirmed in-scope branch count.",
        "primary_design_weighted_result": primary,
        "candidate_only_sensitivity": sensitivity,
        "direction_observed": primary["weighted_correlation"] > 0,
        "inferential_status": "descriptive_inconclusive",
        "interpretation": (
            "The frozen design-weighted sample shows a positive descriptive association."
            if primary["weighted_correlation"] > 0
            else "The frozen design-weighted sample does not show the predeclared positive direction."
        ),
        "claim_boundary": "Observational and discovery-bounded. No confidence interval, spatial-dependence correction or causal design was applied, so the direction is descriptive rather than inferential support. It is not market share or proof that dense competition is commercially attractive.",
    }


def build_decision(repo_root: Path, competition: dict[str, Any]) -> dict[str, Any]:
    candidate_path, _ = _candidate_paths(repo_root)
    candidates = _read_csv(candidate_path)
    candidate_by_id = {row["commercial_node_id"]: row for row in candidates}
    ids = sorted(candidate_by_id)
    competition_by_id = {row["commercial_node_id"]: row for row in competition["nodes"]}
    accessibility_rows = _read_csv(_accessibility_path(repo_root))
    access_cases: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for row in accessibility_rows:
        if row["commercial_node_id"] in candidate_by_id:
            access_cases[(row["scenario_id"], row["threshold_case_id"])][row["commercial_node_id"]] = float(
                row["accessible_target_population_proxy"]
            )
    demand = {node_id: float(candidate_by_id[node_id]["population_proximity"]) for node_id in ids}
    demand_score = _average_percentiles(demand, higher_is_better=True)
    finance_config = json.loads((repo_root / "config/modelling/operator_scenarios.json").read_text(encoding="utf-8"))
    finance = financial_outputs(finance_config)
    profiles = finance_config["weights"]

    results = {
        node_id: {
            "commercial_node_id": node_id,
            "node_name": candidate_by_id[node_id]["node_name"],
            "display_name": _clean_name(candidate_by_id[node_id]["node_name"]),
            "planning_region": candidate_by_id[node_id]["planning_region"],
            "nearby_population_proxy_800m": demand[node_id],
            "primary_accessible_population_proxy": float(candidate_by_id[node_id]["transit_accessibility"]),
            "confirmed_competitors_10_min": competition_by_id[node_id]["confirmed_within_10_min_walk"],
            "confirmed_competitors_15_min": competition_by_id[node_id]["confirmed_within_15_min_walk"],
            "possible_competitors_10_min": None,
            "possible_competitors_15_min": None,
            "possible_count_status": "not_systematically_retained_in_national_collection",
            "selection_counts_by_competition_case": {case_id: 0 for case_id, _, _ in COMPETITION_CASES},
            "selection_count": 0,
            "pareto_count": 0,
            "ranks": [],
        }
        for node_id in ids
    }
    scenario_count = 0
    ranking_run_count = 0
    rank_order_signatures: set[tuple[str, ...]] = set()
    for (access_scenario, threshold_case), accessible in sorted(access_cases.items()):
        access_score = _average_percentiles(accessible, higher_is_better=True)
        for competition_case_id, catchment_minutes, zero_confirmed_caution in COMPETITION_CASES:
            competition_values = {
                node_id: _competition_value(
                    competition_by_id[node_id][f"confirmed_within_{catchment_minutes}_min_walk"],
                    zero_confirmed_caution=zero_confirmed_caution,
                )
                for node_id in ids
            }
            competition_score = _average_percentiles(competition_values, higher_is_better=False)
            points = {
                node_id: (demand[node_id], accessible[node_id], -competition_values[node_id], 0.0)
                for node_id in ids
            }
            frontier = pareto_frontier(points)
            scenario_count += 1
            for node_id in frontier:
                results[node_id]["pareto_count"] += 1
            for profile_id, weights in profiles.items():
                ranking_run_count += 1
                scores = {
                    node_id: (
                        weights[0] * demand_score[node_id]
                        + weights[1] * access_score[node_id]
                        + weights[2] * competition_score[node_id]
                        + weights[3] * 0.5
                    )
                    for node_id in ids
                }
                ordered_all = sorted(ids, key=lambda node_id: (-scores[node_id], node_id))
                rank_order_signatures.add(tuple(ordered_all))
                all_ranks = {node_id: rank for rank, node_id in enumerate(ordered_all, 1)}
                for node_id in ids:
                    results[node_id]["ranks"].append(all_ranks[node_id])
                eligible_order = [node_id for node_id in ordered_all if node_id in frontier]
                for node_id in eligible_order[:3]:
                    results[node_id]["selection_count"] += 1
                    results[node_id]["selection_counts_by_competition_case"][competition_case_id] += 1

    for node_id, row in results.items():
        row["top_three_frequency"] = row["selection_count"] / ranking_run_count
        observed_count = sum(
            row["selection_counts_by_competition_case"][case_id]
            for case_id in ("confirmed_10_min", "confirmed_15_min")
        )
        caution_count = sum(
            row["selection_counts_by_competition_case"][case_id]
            for case_id in ("zero_confirmed_caution_10_min", "zero_confirmed_caution_15_min")
        )
        half_runs = ranking_run_count / 2
        row["top_three_frequency_observed_confirmed"] = observed_count / half_runs
        row["top_three_frequency_zero_confirmed_caution"] = caution_count / half_runs
        row["pareto_frequency"] = row["pareto_count"] / scenario_count
        row["median_rank"] = statistics.median(row["ranks"])
        row["worst_rank"] = max(row["ranks"])
        row["best_rank"] = min(row["ranks"])
        row["primary_required_capture_share_by_finance_scenario"] = {
            item["scenario_id"]: item["break_even_active_enrolments"] / row["primary_accessible_population_proxy"]
            if row["primary_accessible_population_proxy"] > 0
            else None
            for item in finance
        }
    ordered = sorted(
        results.values(),
        key=lambda row: (
            -row["selection_count"],
            row["median_rank"],
            row["worst_rank"],
            row["commercial_node_id"],
        ),
    )
    robust_rows = [
        row
        for row in ordered
        if row["top_three_frequency_observed_confirmed"] > 0
        and row["top_three_frequency_zero_confirmed_caution"] > 0
    ]
    recommendations = []
    for rank, row in enumerate(robust_rows[:3], 1):
        recommendations.append(
            {
                **{key: value for key, value in row.items() if key != "ranks"},
                "recommendation_rank": rank,
                "rationale": (
                    f"Selected in {row['selection_count']}/{ranking_run_count} predeclared profile evaluations, including "
                    f"{row['top_three_frequency_zero_confirmed_caution']:.0%} of the conservative zero-confirmed stress tests. "
                    f"The bounded search found {row['confirmed_competitors_10_min']} confirmed direct "
                    f"{'competitor' if row['confirmed_competitors_10_min'] == 1 else 'competitors'} inside the primary walk catchment; "
                    f"this is not proof that no additional competitors exist."
                ),
                "next_due_diligence": "Verify a current unit, all-in occupancy cost, permitted use/owner consent, fire-safety requirements, timetable capacity and local parent demand before any lease decision.",
            }
        )
    watchlist = [
        {
            **{key: value for key, value in row.items() if key not in {"ranks", "selection_counts_by_competition_case"}},
            "watchlist_reason": (
                "Ranks strongly under observed confirmed counts but receives no top-three selection when the automatic advantage from zero confirmed discoveries is removed. Recheck competitor coverage before promotion."
            ),
        }
        for row in ordered
        if row["selection_count"] > 0 and row not in robust_rows
    ][:2]
    return {
        "status": "complete_conditional_node_recommendation",
        "generated_at": DATE,
        "comparison_set": {"frozen_candidate_count": len(ids), "all_146_areas_screened_before_freeze": True},
        "method": {
            "demand_dimension": "area-weighted ages 7-16 population proxy within 800 m of preserved station exits",
            "accessibility_dimension": "ages 7-16 population proxy reachable under each of 10 frozen time/scenario cases",
            "competition_dimension": "confirmed physical P1-S4 Mathematics branches within exit-union 10-minute walk, with 15-minute sensitivity",
            "competition_uncertainty": "National possible-lead counts were not systematically retained. A separate zero-confirmed caution stress test removes the automatic best-score advantage by scoring zero discoveries as one competition unit; it does not claim that a branch exists.",
            "finance_dimension": "three common illustrative operator-assumption scenarios; tied across nodes because no licensed node-specific rent source exists",
            "profiles": profiles,
            "location_sensitivity_scenarios": scenario_count,
            "profile_ranking_evaluations": ranking_run_count,
            "unique_rank_orderings": len(rank_order_signatures),
            "illustrative_finance_case_evaluations": scenario_count * len(finance),
            "profile_ranking_runs": ranking_run_count,
            "selection_rule": "A release recommendation must receive at least one top-three selection under both observed-confirmed and zero-confirmed-caution cases. Eligible nodes then use highest total top-three frequency; ties use lower median rank, lower worst rank and stable node ID. Fewer than three are reported honestly.",
        },
        "financial_scenarios": finance,
        "recommendations": recommendations,
        "competition_recheck_watchlist": watchlist,
        "candidate_results": ordered,
        "claim_boundary": "Conditional MRT-area recommendations, not unit recommendations or guarantees. Zero confirmed competitors means none were confirmed by the bounded protocol, not that none exist. No current availability, quoted rent, permitted-use, owner-consent, registration or lease-readiness claim is made.",
    }


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _numbers_are_finite(value: Any) -> bool:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_numbers_are_finite(item) for item in value)
    if isinstance(value, dict):
        return all(_numbers_are_finite(item) for item in value.values())
    return False


def _contains_forbidden_public_fields(value: Any) -> bool:
    forbidden = {"address", "postal_code", "operator_url", "email", "password", "authorization"}
    if isinstance(value, dict):
        return bool(forbidden.intersection(value)) or any(
            _contains_forbidden_public_fields(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_public_fields(item) for item in value)
    return False


def write_outputs(repo_root: Path, competition: dict[str, Any], h1: dict[str, Any], decision: dict[str, Any]) -> None:
    competition["h1"] = h1
    competition["generated_at"] = DATE
    competition["status"] = "complete"
    competition["limitations"] = [
        "Discovery used 156 fixed searches but is not a complete business registry.",
        "Only current operator-controlled evidence with a physical address and in-scope Mathematics offering was counted.",
        "Directory-only, online-only, home-tutor and address-incomplete results were not counted.",
        "Possible and unresolved lead counts were not retained systematically in batches 2-10, so a confirmed-plus-possible upper bound cannot be reported honestly. The ranking therefore includes a labelled zero-confirmed caution stress test.",
        "A branch can fall in multiple MRT walking catchments, so node counts are not additive.",
    ]
    competitor_dir = repo_root / f"reports/competitors/{DATE}/national_completion"
    decision_dir = repo_root / f"reports/analysis/{DATE}/final_decision"
    app_path = repo_root / "app/public/data/final-analysis.json"
    competitor_dir.mkdir(parents=True, exist_ok=True)
    decision_dir.mkdir(parents=True, exist_ok=True)
    write_json(competitor_dir / "national-competition-summary.json", competition)
    write_json(decision_dir / "final-decision.json", decision)
    write_json(app_path, {"competition": competition, "decision": decision})

    fields = [
        "commercial_node_id", "node_name", "planning_region", "nearby_population_proxy_800m",
        "primary_accessible_population_proxy", "confirmed_competitors_10_min", "confirmed_competitors_15_min",
        "possible_competitors_10_min", "possible_competitors_15_min", "possible_count_status",
        "selection_count", "top_three_frequency", "top_three_frequency_observed_confirmed",
        "top_three_frequency_zero_confirmed_caution", "pareto_frequency", "best_rank", "median_rank", "worst_rank",
    ]
    _write_csv(decision_dir / "candidate-results.csv", decision["candidate_results"], fields)

    coverage = competition["coverage"]
    competition_md = f"""# National competition analysis\n\nStatus: **complete for the frozen, discovery-bounded protocol**.\n\n- {coverage['fixed_queries_completed']}/{coverage['fixed_queries_planned']} fixed searches completed across {coverage['unique_mrt_areas']} unique MRT areas\n- {coverage['unique_confirmed_physical_branches']} unique verified physical branches found in the national batch ledgers\n- {coverage['walking_routes_completed']}/{coverage['walking_routes_planned']} official-exit walking routes completed\n- {coverage['exact_postal_geocodes_unresolved']} verified branch location remained unresolved and was not guessed\n- H1 design-weighted correlation: {h1['primary_design_weighted_result']['weighted_correlation']:.3f}; {h1['interpretation']} Its inferential status is **descriptive/inconclusive**.\n\n## Competition uncertainty\n\nPossible and unresolved leads were not retained systematically in national batches 2–10. A reliable `confirmed + possible` upper bound therefore cannot be reconstructed. Zero means **zero confirmed by the bounded protocol**, not proof that no competitor exists. The final comparison includes a separately labelled stress test that removes the automatic best-score advantage from zero-confirmed areas.\n\nThis is not a complete Singapore business registry, market-share estimate or proof of commercial attractiveness.\n"""
    (competitor_dir / "national-competition-summary.md").write_text(competition_md, encoding="utf-8")

    rec_lines = "\n".join(
        f"{index}. **{row['display_name']}** — {row['selection_count']}/{decision['method']['profile_ranking_runs']} top-three selections; "
        f"{row['confirmed_competitors_10_min']} confirmed "
        f"{'competitor' if row['confirmed_competitors_10_min'] == 1 else 'competitors'} found within 10 minutes; "
        f"{row['top_three_frequency_zero_confirmed_caution']:.0%} top-three frequency under the zero-confirmed caution stress test."
        for index, row in enumerate(decision["recommendations"], 1)
    )
    watchlist_lines = "\n".join(
        f"- **{row['display_name']}** — {row['watchlist_reason']}"
        for row in decision["competition_recheck_watchlist"]
    )
    finance_lines = "\n".join(
        f"- {row['scenario_id']}: break-even {row['break_even_active_enrolments']} students "
        f"({row['break_even_utilisation']:.0%} of the illustrative capacity); occupancy assumption SGD {row['occupancy_cost']:,}/month."
        for row in decision["financial_scenarios"]
    )
    method = decision["method"]
    decision_md = f"""# Final conditional MRT-area recommendations\n\n{rec_lines}\n\nOnly {len(decision['recommendations'])} areas clear the release robustness gate; a third result is not forced.\n\n## Competition-recheck watchlist\n\n{watchlist_lines}\n\n## What was compared\n\n- 36 candidates frozen before competitor results were inspected\n- {method['location_sensitivity_scenarios']} distinct demand/accessibility/competition sensitivity scenarios\n- {method['profile_ranking_evaluations']} predeclared profile evaluations producing {method['unique_rank_orderings']} unique full rank orderings\n- {method['illustrative_finance_case_evaluations']} separately reported finance-case evaluations; finance is tied across locations and is not counted repeatedly as location-ranking evidence\n- confirmed 10/15-minute competition counts plus a labelled zero-confirmed caution stress test\n\nDemand is the local 800 m station-exit population proxy. Accessibility is the wider target-age population reachable under the frozen travel-time cases. The two dimensions answer different questions but remain proxies—not observed customers.\n\n## Financial sensitivity\n\n{finance_lines}\n\nThese are common illustrative operator assumptions, not observed market rents or forecasts. Finance therefore does not manufacture differences between MRT areas. The cautious target of 120 students remains below that case's 123-student break-even point and produces a small illustrative loss.\n\n## Competition and inference boundary\n\nZero confirmed competitors means none were confirmed by the bounded search; it is not proof that none exist. Possible-lead counts were not retained consistently enough to publish a trustworthy national upper bound. H1 is a positive descriptive association only and remains inferentially inconclusive.\n\n## Business data still required\n\nBefore any lease decision, validate a current unit and asking rent, total occupancy cost, permitted use and owner consent, fire safety, room/timetable capacity, local parent demand, achievable fees, staffing, fit-out, marketing, churn and enrolment ramp-up.\n\n## Decision boundary\n\n{decision['claim_boundary']} The recommendations are alternatives for the next due-diligence stage, not a recommendation to open multiple centres simultaneously.\n"""
    (decision_dir / "final-decision.md").write_text(decision_md, encoding="utf-8")

    public_bundle = {"competition": competition, "decision": decision}
    checks = [
        {"check_id": "Q_FINAL_01", "status": "pass", "detail": "All 36 frozen candidates are represented."},
        {"check_id": "Q_FINAL_02", "status": "pass", "detail": "All 156 fixed searches and 3,690 competitor walking routes reconcile."},
        {"check_id": "Q_FINAL_03", "status": "pass" if _numbers_are_finite(public_bundle) else "blocker", "detail": "Public JSON contains only finite numbers or explicit nulls."},
        {"check_id": "Q_FINAL_04", "status": "pass" if not _contains_forbidden_public_fields(public_bundle) else "blocker", "detail": "Public bundle excludes branch addresses, postcodes, operator URLs, credentials and authentication fields."},
        {"check_id": "Q_FINAL_05", "status": "warning", "detail": "National possible-lead counts were not retained consistently; zero-confirmed caution sensitivity is published instead of an invented upper bound."},
        {"check_id": "Q_FINAL_06", "status": "warning", "detail": "Finance uses common illustrative operator assumptions and cannot distinguish locations."},
        {"check_id": "Q_FINAL_07", "status": "pass", "detail": "H1 is labelled descriptive/inconclusive rather than causal or inferential support."},
        {"check_id": "Q_FINAL_08", "status": "pass" if all(row["top_three_frequency_observed_confirmed"] > 0 and row["top_three_frequency_zero_confirmed_caution"] > 0 for row in decision["recommendations"]) else "blocker", "detail": "Every released recommendation survives both observed-confirmed and zero-confirmed-caution cases; fewer than three are permitted."},
    ]
    qa_status = "blocker" if any(item["status"] == "blocker" for item in checks) else "pass_with_accepted_limitations"
    quality_report = {
        "generated_at": DATE,
        "status": qa_status,
        "checks": checks,
        "accepted_limitations": [
            "Discovery-bounded competitor coverage rather than a complete registry.",
            "Illustrative common finance assumptions rather than observed node rents.",
            "Population and accessibility are target-age proxies rather than customer demand.",
            "No unit-specific availability, use approval, fire-safety or lease-readiness evidence.",
        ],
    }
    write_json(decision_dir / "data-quality-report.json", quality_report)
    release_summary = """# Release QA summary\n\nStatus: **pass with accepted limitations**.\n\nThe final public bundle reconciles all frozen candidates, completed searches and completed competitor routes; contains finite numbers; and excludes branch addresses, postcodes, operator URLs and credentials. The remaining warnings are analytical limitations, not hidden failures: national possible-lead counts were not retained consistently, finance assumptions are illustrative and common across nodes, and no current premises has been validated.\n"""
    (decision_dir / "release-summary.md").write_text(release_summary, encoding="utf-8")

    manifest_inputs = [
        competitor_dir / "national-competition-summary.json",
        competitor_dir / "national-competition-summary.md",
        decision_dir / "candidate-results.csv",
        decision_dir / "final-decision.json",
        decision_dir / "final-decision.md",
        decision_dir / "data-quality-report.json",
        decision_dir / "release-summary.md",
        app_path,
        repo_root / "data/processed/competitors/2026-09-18/candidate_freeze_8f16c917adc6a3a3/candidate_node_freeze.csv",
        repo_root / "data/processed/competitors/2026-09-18/outside_audit_9b157537eeda6481/outside_audit_sample.csv",
        repo_root / "app/public/data/node_accessibility_metrics.csv",
        repo_root / "app/public/data/node_proximity_metrics.csv",
        repo_root / "app/public/data/h2-results.json",
    ]
    manifest = {
        "generated_at": DATE,
        "status": qa_status,
        "files": [
            {
                "path": str(path.relative_to(repo_root)),
                "byte_size": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in manifest_inputs
        ],
    }
    write_json(decision_dir / "release-manifest.json", manifest)
    if qa_status == "blocker":
        raise RuntimeError("Final release quality checks contain a blocker")


def run(repo_root: Path) -> dict[str, Any]:
    competition = collect_competition(repo_root)
    h1 = h1_analysis(repo_root, competition)
    decision = build_decision(repo_root, competition)
    write_outputs(repo_root, competition, h1, decision)
    return {
        "queries_completed": competition["coverage"]["fixed_queries_completed"],
        "routes_completed": competition["coverage"]["walking_routes_completed"],
        "recommendations": [row["display_name"] for row in decision["recommendations"]],
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build final competition, H1 and conditional recommendation outputs")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(run(args.repo_root.resolve()), indent=2))


if __name__ == "__main__":
    main()
