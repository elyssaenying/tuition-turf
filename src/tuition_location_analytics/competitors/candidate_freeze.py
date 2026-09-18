from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from tuition_location_analytics.foundation.common import (
    file_record,
    sha256_file,
    utc_now,
    write_csv,
    write_json,
    write_parquet,
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _truthy(value: Any) -> bool:
    return value is True or str(value).strip().lower() == "true"


def _unique_by(rows: list[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = str(row[key])
        if value in result:
            raise RuntimeError(f"duplicate {label} key: {value}")
        result[value] = row
    return result


def _add_ordinal_percentile(
    rows: list[dict[str, Any]], metric: str, rank_field: str, percentile_field: str
) -> None:
    ordered = sorted(rows, key=lambda row: (-float(row[metric]), row["commercial_node_id"]))
    denominator = max(1, len(ordered) - 1)
    for position, row in enumerate(ordered, start=1):
        row[rank_field] = position
        row[percentile_field] = 1.0 if len(ordered) == 1 else (len(ordered) - position) / denominator


def _pareto_flags(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        population = float(row["population_proximity"])
        accessibility = float(row["transit_accessibility"])
        row["population_accessibility_pareto_nondominated"] = not any(
            (
                float(other["population_proximity"]) >= population
                and float(other["transit_accessibility"]) >= accessibility
                and (
                    float(other["population_proximity"]) > population
                    or float(other["transit_accessibility"]) > accessibility
                )
            )
            for other in rows
            if other["commercial_node_id"] != row["commercial_node_id"]
        )


def build_candidate_freeze(
    qualified_nodes: list[dict[str, Any]],
    proximity_rows: list[dict[str, Any]],
    accessibility_rows: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    eligibility = config["eligibility"]
    scenario = eligibility["accessibility_scenario_id"]
    threshold_case = eligibility["accessibility_threshold_case_id"]
    primary_accessibility = [
        row
        for row in accessibility_rows
        if row["scenario_id"] == scenario and row["threshold_case_id"] == threshold_case
    ]
    proximity_by_id = _unique_by(proximity_rows, "commercial_node_id", "proximity")
    accessibility_by_id = _unique_by(
        primary_accessibility, "commercial_node_id", "primary accessibility"
    )

    eligible: list[dict[str, Any]] = []
    exclusion_counts: Counter[str] = Counter()
    for node in qualified_nodes:
        node_id = node["commercial_node_id"]
        if node.get("qualification_status") != eligibility["qualification_status"]:
            exclusion_counts["not_commercially_qualified"] += 1
            continue
        proximity = proximity_by_id.get(node_id)
        accessibility = accessibility_by_id.get(node_id)
        if proximity is None or accessibility is None:
            exclusion_counts["missing_screen_input"] += 1
            continue
        region = str(proximity.get("region_name_at_anchor") or "").strip()
        if eligibility["require_known_planning_region"] and not region:
            exclusion_counts["missing_planning_region"] += 1
            continue
        if eligibility["require_route_coverage_complete"] and not _truthy(
            accessibility.get("route_coverage_complete")
        ):
            exclusion_counts["incomplete_route_coverage"] += 1
            continue
        eligible.append(
            {
                "commercial_node_id": node_id,
                "station_complex_id": node["station_complex_id"],
                "node_name": node["node_name"],
                "planning_area_name": proximity["planning_area_name_at_anchor"],
                "planning_region": region,
                "qualification_status": node["qualification_status"],
                "commercial_signal_count": int(node["commercial_signal_count"]),
                "population_proximity": float(
                    proximity[config["screen"]["population_metric"]]
                ),
                "transit_accessibility": float(
                    accessibility[config["screen"]["accessibility_metric"]]
                ),
                "accessibility_scenario_id": scenario,
                "accessibility_threshold_case_id": threshold_case,
                "route_coverage_complete": True,
            }
        )

    _add_ordinal_percentile(
        eligible,
        "population_proximity",
        "population_proximity_rank",
        "population_proximity_percentile",
    )
    _add_ordinal_percentile(
        eligible,
        "transit_accessibility",
        "transit_accessibility_rank",
        "transit_accessibility_percentile",
    )
    weights = config["screen"]["weights"]
    for row in eligible:
        row["screen_score"] = (
            float(weights["population_proximity_percentile"])
            * row["population_proximity_percentile"]
            + float(weights["accessibility_percentile"])
            * row["transit_accessibility_percentile"]
        )
    _pareto_flags(eligible)

    ordered = sorted(eligible, key=lambda row: (-row["screen_score"], row["commercial_node_id"]))
    selection = config["selection"]
    merit_slots = min(int(selection["merit_slots"]), len(ordered))
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()

    for row in ordered[:merit_slots]:
        copy = dict(row)
        copy["selection_stage"] = "merit"
        copy["selection_slot"] = len(selected) + 1
        selected.append(copy)
        selected_ids.add(row["commercial_node_id"])

    region_counts = Counter(row["planning_region"] for row in selected)
    target_count = min(int(selection["maximum_nodes"]), len(ordered))
    coverage_limit = min(
        int(selection["regional_coverage_slots"]), target_count - len(selected)
    )
    coverage_added = 0
    while coverage_added < coverage_limit:
        remaining = [row for row in ordered if row["commercial_node_id"] not in selected_ids]
        if not remaining:
            break
        regions = sorted({row["planning_region"] for row in remaining})
        chosen_region = min(regions, key=lambda region: (region_counts[region], region))
        chosen = next(row for row in remaining if row["planning_region"] == chosen_region)
        copy = dict(chosen)
        copy["selection_stage"] = "regional_coverage"
        copy["selection_slot"] = len(selected) + 1
        selected.append(copy)
        selected_ids.add(chosen["commercial_node_id"])
        region_counts[chosen_region] += 1
        coverage_added += 1

    for row in ordered:
        if len(selected) >= target_count:
            break
        if row["commercial_node_id"] in selected_ids:
            continue
        copy = dict(row)
        copy["selection_stage"] = "global_shortfall_fill"
        copy["selection_slot"] = len(selected) + 1
        selected.append(copy)
        selected_ids.add(row["commercial_node_id"])

    selected_stage_by_id = {
        row["commercial_node_id"]: row["selection_stage"] for row in selected
    }
    for row in eligible:
        row["selected_for_competition_stage"] = row["commercial_node_id"] in selected_ids
        row["selection_stage"] = selected_stage_by_id.get(row["commercial_node_id"])

    quality = {
        "input_node_count": len(qualified_nodes),
        "eligible_node_count": len(eligible),
        "excluded_node_count": len(qualified_nodes) - len(eligible),
        "exclusion_counts": dict(sorted(exclusion_counts.items())),
        "selected_node_count": len(selected),
        "selection_stage_counts": dict(
            sorted(Counter(row["selection_stage"] for row in selected).items())
        ),
        "selected_region_counts": dict(
            sorted(Counter(row["planning_region"] for row in selected).items())
        ),
        "unique_selected_ids": len(selected_ids) == len(selected),
        "competitor_inputs_used": False,
    }
    return eligible, selected, quality


def _markdown(result: dict[str, Any], selected: list[dict[str, Any]]) -> str:
    quality = result["quality"]
    lines = [
        "# Frozen competition-stage candidate set",
        "",
        f"Freeze ID: `{result['freeze_id']}`  ",
        f"Eligible evidence-qualified MRT areas: **{quality['eligible_node_count']}**  ",
        f"Selected areas: **{quality['selected_node_count']}**",
        "",
        "The candidate set was selected before competitor evidence using an equal-weight screen of nearby ages 7–16 population and transit-aware accessible population. The first 24 slots are national merit slots; 12 additional slots improve regional representation.",
        "",
        "| Slot | MRT area | Region | Stage | Screen score | Local population rank | Accessibility rank |",
        "|---:|---|---|---|---:|---:|---:|",
    ]
    for row in sorted(selected, key=lambda item: item["selection_slot"]):
        lines.append(
            f"| {row['selection_slot']} | {row['node_name']} | {row['planning_region']} | "
            f"{row['selection_stage']} | {row['screen_score']:.3f} | "
            f"{row['population_proximity_rank']} | {row['transit_accessibility_rank']} |"
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- No competitor, rent, listing or preferred-location field entered the screen.",
            "- Selection is for the competition-data stage, not the final three recommendations.",
            "- Commercial qualification is based on two independent positive families at 800 m: MP2025 zoning and HSA licensed retail-pharmacy presence.",
            "- Final comparison still requires competition coverage, uncertainty checks and the approved decision framework.",
        ]
    )
    return "\n".join(lines) + "\n"


def run(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    config_path = repo_root / "config/competitors/candidate_freeze.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    inputs = {
        key: (repo_root / reference).resolve() for key, reference in config["inputs"].items()
    }
    for path in inputs.values():
        if not path.is_relative_to(repo_root) or not path.is_file():
            raise RuntimeError(f"candidate-freeze input is missing or outside repository: {path}")

    eligible, selected, quality = build_candidate_freeze(
        _read_csv(inputs["qualified_nodes_ref"]),
        _read_csv(inputs["population_proximity_ref"]),
        _read_csv(inputs["accessibility_ref"]),
        config,
    )
    config_hash = sha256_file(config_path)
    freeze_id = f"candidate_freeze_{config_hash[:16]}"
    output_dir = repo_root / "data/processed/competitors/2026-09-18" / freeze_id
    report_dir = repo_root / "reports/competitors/2026-09-18" / freeze_id
    screen_csv = output_dir / "eligible_node_screen.csv"
    screen_parquet = output_dir / "eligible_node_screen.parquet"
    freeze_csv = output_dir / "candidate_node_freeze.csv"
    freeze_parquet = output_dir / "candidate_node_freeze.parquet"
    write_csv(screen_csv, eligible)
    write_parquet(screen_parquet, eligible)
    write_csv(freeze_csv, selected)
    write_parquet(freeze_parquet, selected)
    result = {
        "freeze_id": freeze_id,
        "created_at": utc_now(),
        "status": "frozen_before_competitor_inspection",
        "config_ref": config_path.relative_to(repo_root).as_posix(),
        "config_sha256": config_hash,
        "input_sha256": {
            key: sha256_file(path) for key, path in sorted(inputs.items())
        },
        "quality": quality,
        "selected_node_ids": [row["commercial_node_id"] for row in selected],
        "outputs": [
            file_record(screen_csv, repo_root, len(eligible)),
            file_record(screen_parquet, repo_root, len(eligible)),
            file_record(freeze_csv, repo_root, len(selected)),
            file_record(freeze_parquet, repo_root, len(selected)),
        ],
    }
    write_json(report_dir / "candidate-freeze.json", result)
    (report_dir / "candidate-freeze.md").parent.mkdir(parents=True, exist_ok=True)
    (report_dir / "candidate-freeze.md").write_text(
        _markdown(result, selected), encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze the competition-stage candidate nodes")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = run(args.repo_root)
    print(json.dumps({"freeze_id": result["freeze_id"], "quality": result["quality"]}, indent=2))


if __name__ == "__main__":
    main()
