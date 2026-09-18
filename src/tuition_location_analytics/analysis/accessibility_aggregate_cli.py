from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import pyarrow as pa
import pyarrow.parquet as pq

from tuition_location_analytics.foundation.common import file_record, sha256_file, utc_now, write_csv, write_json, write_parquet

from .accessibility_aggregate import aggregate_accessibility, evaluate_h2, threshold_cases
from .routing_execute import RedactedRouteCache
from .routing_national_cli import build_progress, load_authorised_plan


def require_complete_cache(
    plan_rows: list[dict[str, Any]], cache_records: list[dict[str, Any]]
) -> dict[str, Any]:
    progress = build_progress(plan_rows, cache_records)
    if progress["status"] != "complete":
        raise RuntimeError(
            f"national route cache is incomplete: {progress['completed_pt_requests']}/{progress['planned_pt_requests']} PT outcomes"
        )
    return progress


def _summary_markdown(
    run_id: str,
    metrics: list[dict[str, Any]],
    h2: dict[str, Any],
) -> str:
    primary = sorted(
        [
            row
            for row in metrics
            if row["scenario_id"] == "primary_weekday_after_school"
            and row["is_primary_threshold_case"]
        ],
        key=lambda row: (-float(row["accessible_target_population_proxy"]), str(row["commercial_node_id"])),
    )
    lines = [
        "# National transit accessibility analysis",
        "",
        f"Run ID: `{run_id}`  ",
        "Status: **complete and quality-checked**",
        "",
        "The primary measure estimates the ages 7–16 population represented by subzone centroids that can reach each MRT area by public transport within 20 minutes, by the walking fallback within 10 minutes, or by the frozen 800 m straight-line proximity fallback when neither route method yields a usable result. The three contributions are reported separately; proximity is never presented as a travel-time result. It is an area-level accessibility proxy, not observed demand or customers.",
        "",
        "## Highest primary accessible-population proxies",
        "",
        "| Rank | MRT area | Accessible population proxy | PT-accessible | Walk-fallback accessible | Proximity-fallback accessible |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for index, row in enumerate(primary[:10], start=1):
        lines.append(
            f"| {index} | {row['node_name']} | {float(row['accessible_target_population_proxy']):.0f} | {float(row['pt_accessible_population_proxy']):.0f} | {float(row['walking_fallback_accessible_population_proxy']):.0f} | {float(row['proximity_fallback_accessible_population_proxy']):.0f} |"
        )
    difference = h2["median_node_absolute_percentage_difference"]
    correlation = h2["spearman_rank_correlation"]
    lines.extend(
        [
            "",
            "## H2 comparison",
            "",
            f"- Median absolute difference from the allocation-compatible 800 m centroid baseline: {difference:.1%}.",
            f"- Frozen materiality threshold: {float(h2['materiality_threshold']):.1%}.",
            f"- Material difference under the frozen rule: {'yes' if h2['material_difference'] else 'no'}.",
            f"- Spearman rank correlation: {float(correlation):.3f}." if correlation is not None else "- Spearman rank correlation: unavailable because one ordering is constant.",
            f"- Nodes moving at least 10 ranks: {h2['nodes_moving_at_least_10_ranks_count']} of {h2['valid_node_count']}.",
            "",
            "These results do not include national competitor evidence, financial feasibility or final recommendations.",
        ]
    )
    return "\n".join(lines) + "\n"


def run(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    routing_config, plan_rows = load_authorised_plan(repo_root)
    plan_run_id = routing_config["authorised_execution_plan_run_id"]
    run_name = "national_routing_execution_" + plan_run_id
    cache_path = repo_root / "data/interim/analysis" / routing_config["plan_date"] / run_name / "route-outcomes.sqlite"
    if not cache_path.is_file():
        raise RuntimeError("national route cache does not exist")
    cache = RedactedRouteCache(cache_path)
    cache_records = cache.records()
    cache.close()
    progress = require_complete_cache(plan_rows, cache_records)

    scenario_path = repo_root / "config/accessibility/scenarios.json"
    scenario_config = json.loads(scenario_path.read_text(encoding="utf-8"))
    cases = threshold_cases(scenario_config)
    proximity_metres = float(scenario_config["primary_scenario"]["straight_line_proximity_fallback_metres"])
    metrics = aggregate_accessibility(
        plan_rows,
        cache_records,
        cases,
        proximity_fallback_metres=proximity_metres,
    )
    expected = 146 * 2 * len(cases)
    if len(metrics) != expected or not all(row["route_coverage_complete"] for row in metrics):
        raise RuntimeError("national accessibility aggregation failed row-count or route-coverage checks")
    h2_config = scenario_config["h2_materiality_rule"]["primary_rule"]
    h2 = evaluate_h2(
        metrics,
        primary_scenario_id=scenario_config["primary_scenario"]["scenario_id"],
        materiality_threshold=float(h2_config["materiality_threshold"]),
    )

    digest = "|".join(
        [
            routing_config["authorised_execution_plan_sha256"],
            sha256_file(cache_path),
            sha256_file(scenario_path),
        ]
    )
    run_id = "accessibility_" + hashlib.sha256(digest.encode("utf-8")).hexdigest()[:16]
    processed_dir = repo_root / "data/processed/analysis" / routing_config["plan_date"] / run_id
    report_dir = repo_root / "reports/analysis" / routing_config["plan_date"] / run_id
    if processed_dir.exists() or report_dir.exists():
        raise RuntimeError(f"accessibility output directory already exists: {run_id}")
    processed_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)

    parquet_path = processed_dir / "node_accessibility_metrics.parquet"
    csv_path = processed_dir / "node_accessibility_metrics.csv"
    float_fields = {
        "accessible_target_population_proxy": pa.float64(),
        "pt_accessible_population_proxy": pa.float64(),
        "walking_fallback_accessible_population_proxy": pa.float64(),
        "proximity_fallback_accessible_population_proxy": pa.float64(),
        "transport_accessible_population_proxy": pa.float64(),
        "centroid_proximity_population_proxy_800m": pa.float64(),
        "transit_reach_share": pa.float64(),
        "combined_accessibility_reach_share": pa.float64(),
        "national_target_population_proxy": pa.float64(),
        "unresolved_route_population_proxy": pa.float64(),
    }
    write_parquet(parquet_path, metrics, type_overrides=float_fields)
    write_csv(csv_path, metrics)
    quality = {
        "status": "passed",
        "metric_row_count": len(metrics),
        "expected_metric_row_count": expected,
        "node_count": len({row["commercial_node_id"] for row in metrics}),
        "journey_scenario_count": len({row["scenario_id"] for row in metrics}),
        "threshold_case_count": len(cases),
        "all_route_coverage_complete": all(row["route_coverage_complete"] for row in metrics),
        "national_route_progress": progress,
        "claim_boundary": "Area-level accessibility proxy only; not observed demand, customers, competition, financial viability, shortlist or recommendation.",
    }
    quality_path = report_dir / "data-quality-report.json"
    h2_path = report_dir / "h2-results.json"
    report_path = report_dir / "analysis-summary.md"
    write_json(quality_path, quality)
    write_json(h2_path, h2)
    report_path.write_text(_summary_markdown(run_id, metrics, h2), encoding="utf-8")
    manifest_path = report_dir / "manifest.json"
    write_json(
        manifest_path,
        {
            "run_id": run_id,
            "generated_at": utc_now(),
            "status": "passed",
            "inputs": [
                file_record((repo_root / routing_config["authorised_execution_plan"]).resolve(), repo_root),
                file_record(cache_path, repo_root, len(cache_records)),
                file_record(scenario_path, repo_root),
            ],
            "outputs": [
                file_record(parquet_path, repo_root, len(metrics)),
                file_record(csv_path, repo_root, len(metrics)),
                file_record(quality_path, repo_root),
                file_record(h2_path, repo_root),
                file_record(report_path, repo_root),
            ],
        },
    )
    return {"run_id": run_id, "status": "passed", "metric_rows": len(metrics), "h2": h2}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate a complete national route cache into accessibility metrics and H2")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    print(json.dumps(run(args.repo_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
