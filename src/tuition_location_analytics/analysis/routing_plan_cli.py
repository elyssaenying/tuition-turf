from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from tuition_location_analytics.foundation.common import file_record, sha256_file, utc_now, write_csv, write_json, write_parquet

from .routing_plan import build_routing_plan


def _repo_file(repo_root: Path, reference: str) -> Path:
    path = (repo_root / reference).resolve()
    if not path.is_relative_to(repo_root.resolve()) or not path.is_file():
        raise RuntimeError(f"configured input is missing or outside repository: {reference}")
    return path


def _scenarios(accessibility: dict[str, Any]) -> list[dict[str, Any]]:
    primary = accessibility["primary_scenario"]
    weekend = accessibility["sensitivity_scenarios"]["weekend_comparison_scenario"]
    return [
        {
            "scenario_id": primary["scenario_id"],
            "journey_timestamp": primary["journey_timestamp"],
            "pt_threshold_minutes": primary["public_transport_threshold_minutes"],
            "walking_threshold_minutes": primary["walking_threshold_minutes"],
            "proximity_fallback_metres": primary["straight_line_proximity_fallback_metres"],
        },
        {
            "scenario_id": weekend["scenario_id"],
            "journey_timestamp": weekend["journey_timestamp"],
            "pt_threshold_minutes": primary["public_transport_threshold_minutes"],
            "walking_threshold_minutes": primary["walking_threshold_minutes"],
            "proximity_fallback_metres": primary["straight_line_proximity_fallback_metres"],
        },
    ]


def run(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    config_path = repo_root / "config/accessibility/national_routing_plan.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config["execution_status"] not in {
        "planning_only_pending_owner_approval",
        "approved_for_bounded_readiness",
    }:
        raise RuntimeError("unexpected routing-plan execution status")
    paths = {key: _repo_file(repo_root, value) for key, value in config["inputs"].items()}
    accessibility = json.loads(paths["accessibility_scenarios"].read_text(encoding="utf-8"))
    scenarios = _scenarios(accessibility)
    subzones = pq.read_table(paths["mp2019_subzones"]).drop(["geometry"]).to_pylist()
    population = {
        row["geo_id"]: float(row["accessible_target_population_proxy"])
        for row in pq.read_table(paths["population_proxy_subzone"]).to_pylist()
    }
    nodes = pq.read_table(paths["commercial_node_candidates"]).to_pylist()
    exits = pq.read_table(paths["station_complex_exits"]).to_pylist()
    records = build_routing_plan(
        subzones,
        population,
        nodes,
        exits,
        scenarios,
        max_walk_distance_metres=int(config["primary_max_walk_distance_metres"]),
        num_itineraries=int(config["num_itineraries"]),
    )
    expected = len(subzones) * len(nodes) * len(scenarios)
    unique_ids = len({row["od_plan_id"] for row in records})
    quality = {
        "status": "planning_complete_execution_not_authorised",
        "origin_subzone_count": len(subzones),
        "node_count": len(nodes),
        "scenario_count": len(scenarios),
        "planned_pt_request_count": len(records),
        "expected_pt_request_count": expected,
        "unique_od_plan_id_count": unique_ids,
        "all_population_nonnegative": all(row["origin_target_population_proxy"] >= 0 for row in records),
        "all_distances_nonnegative": all(row["nearest_exit_straight_line_distance_metres"] >= 0 for row in records),
        "request_execution_authorised": False,
        "network_requests_executed": 0,
        "approved_primary_parameter": {
            "max_walk_distance_metres": config["primary_max_walk_distance_metres"],
            "basis": config["max_walk_distance_basis"],
        },
        "bounded_sample_authorised": bool(config["bounded_sample_authorised"]),
        "national_execution_authorised": bool(config["national_execution_authorised"]),
    }
    if len(records) != expected or unique_ids != expected or not quality["all_population_nonnegative"] or not quality["all_distances_nonnegative"]:
        raise RuntimeError("national routing-plan quality checks failed")

    digest = "|".join([sha256_file(config_path), *[sha256_file(path) for path in paths.values()]])
    run_id = "routing_plan_" + hashlib.sha256(digest.encode("utf-8")).hexdigest()[:16]
    processed_dir = repo_root / "data/processed/analysis" / config["plan_date"] / run_id
    report_dir = repo_root / "reports/analysis" / config["plan_date"] / run_id
    if processed_dir.exists() or report_dir.exists():
        raise RuntimeError(f"routing-plan directory already exists: {run_id}")
    processed_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)
    parquet_path = processed_dir / "national_routing_plan.parquet"
    csv_path = processed_dir / "national_routing_plan.csv"
    write_parquet(
        parquet_path,
        records,
        type_overrides={
            "origin_target_population_proxy": pa.float64(),
            "origin_latitude_wgs84": pa.float64(),
            "origin_longitude_wgs84": pa.float64(),
            "destination_latitude_wgs84": pa.float64(),
            "destination_longitude_wgs84": pa.float64(),
            "nearest_exit_straight_line_distance_metres": pa.float64(),
        },
    )
    write_csv(csv_path, records)
    quality_path = report_dir / "routing-plan-quality.json"
    write_json(quality_path, quality)
    report_path = report_dir / "routing-plan-summary.md"
    conservative_rate = int(config["planned_max_requests_per_minute"])
    minutes = len(records) / conservative_rate
    report_path.write_text(
        "\n".join(
            [
                "# National accessibility routing plan",
                "",
                f"Run ID: `{run_id}`  ",
                "Status: **planning complete; execution not authorised**",
                "",
                f"- Origins: {len(subzones)} MP2019 subzone centroids",
                f"- Destinations: closest preserved station exit for each of {len(nodes)} current MRT-area candidates",
                f"- Scenarios: {len(scenarios)} (weekday primary and weekend comparison)",
                f"- Planned primary PT requests: {len(records):,}",
                f"- Theoretical PT-only duration at the conservative {conservative_rate}/minute cap: {minutes / 60:.1f} hours",
                "- Missing PT results would add walking-fallback requests, so actual execution would take longer.",
                "- No authentication, route or other network request was made by this planning run.",
                "",
                "## Required approval",
                "",
                f"The approved main setting is `maxWalkDistance={config['primary_max_walk_distance_metres']}` metres. A bounded same-route comparison at {', '.join(str(value) for value in config['bounded_comparison_walk_distances_metres'])} metres is authorised.",
                "",
                "Only the bounded comparison is authorised. National execution remains unapproved.",
                "The route client must use resumable redacted caching, safe token handling, conservative pacing and immediate stop controls.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = report_dir / "manifest.json"
    write_json(
        manifest_path,
        {
            "run_id": run_id,
            "generated_at": utc_now(),
            "status": quality["status"],
            "network_requests_executed": 0,
            "inputs": [file_record(path, repo_root) for path in paths.values()] + [file_record(config_path, repo_root)],
            "outputs": [
                file_record(parquet_path, repo_root, len(records)),
                file_record(csv_path, repo_root, len(records)),
                file_record(quality_path, repo_root),
                file_record(report_path, repo_root),
            ],
        },
    )
    return {"run_id": run_id, "quality": quality, "processed_dir": str(processed_dir), "report_dir": str(report_dir)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the offline national accessibility routing plan")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    result = run(Path(args.repo_root))
    print(json.dumps({"run_id": result["run_id"], **result["quality"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
