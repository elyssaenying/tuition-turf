from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

import pyarrow as pa
import pyarrow.parquet as pq

from tuition_location_analytics.competitors.geocode import OneMapUnavailable, _authenticate
from tuition_location_analytics.foundation.common import file_record, sha256_file, utc_now, write_csv, write_json, write_parquet

from .routing_execute import RedactedRouteCache, execute_route_batch
from .routing_sample import expand_walk_comparison, select_balanced_pairs


def _repo_file(repo_root: Path, reference: str) -> Path:
    path = (repo_root / reference).resolve()
    if not path.is_relative_to(repo_root.resolve()) or not path.is_file():
        raise RuntimeError(f"configured input is missing or outside repository: {reference}")
    return path


def _load(repo_root: Path) -> tuple[Path, dict[str, Any], Path, str]:
    config_path = repo_root / "config/accessibility/bounded_walk_comparison.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config["execution_status"] != "approved_for_bounded_sample":
        raise RuntimeError("bounded route sample is not approved")
    if config["national_execution_authorised"]:
        raise RuntimeError("bounded sample config must not authorise national execution")
    source_path = _repo_file(repo_root, config["source_routing_plan"])
    digest = sha256_file(config_path) + "|" + sha256_file(source_path)
    run_id = "walk_comparison_" + hashlib.sha256(digest.encode("utf-8")).hexdigest()[:16]
    return config_path, config, source_path, run_id


def build_sample_plan(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    config_path, config, source_path, run_id = _load(repo_root)
    processed_dir = repo_root / "data/processed/analysis" / config["analysis_date"] / run_id
    report_dir = repo_root / "reports/analysis" / config["analysis_date"] / run_id
    parquet_path = processed_dir / "bounded_walk_comparison_plan.parquet"
    csv_path = processed_dir / "bounded_walk_comparison_plan.csv"
    if parquet_path.exists() and csv_path.exists():
        records = pq.read_table(parquet_path).to_pylist()
        return {"run_id": run_id, "records": records, "processed_dir": processed_dir, "report_dir": report_dir, "reused": True}
    if processed_dir.exists() or report_dir.exists():
        raise RuntimeError(f"partial bounded-sample directory already exists: {run_id}")

    source_rows = pq.read_table(source_path).to_pylist()
    pairs = select_balanced_pairs(
        source_rows,
        scenario_id=config["scenario_id"],
        distance_bands=config["distance_bands_metres"],
        pairs_per_band=int(config["pairs_per_distance_band"]),
        seed=config["selection_seed"],
    )
    records = expand_walk_comparison(pairs, [int(value) for value in config["walk_distances_metres"]])
    expected = len(config["distance_bands_metres"]) * int(config["pairs_per_distance_band"]) * len(config["walk_distances_metres"])
    if len(records) != expected or len({row["od_plan_id"] for row in records}) != expected:
        raise RuntimeError("bounded comparison plan failed count or identity checks")
    processed_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)
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
    summary_path = report_dir / "sample-plan-summary.md"
    summary_path.write_text(
        "\n".join(
            [
                "# Bounded walking-distance comparison plan",
                "",
                f"Run ID: `{run_id}`  ",
                f"Base origin–destination pairs: **{len(pairs)}**  ",
                f"Planned PT requests: **{len(records)}**",
                "",
                "The same deterministic five pairs from each straight-line distance band are tested at 300 m, 500 m and 1,000 m maximum walking distance. Selection uses identifiers and distance only, never route outcomes. This diagnostic cannot rank MRT areas or estimate national accessibility.",
                "",
                "Only this bounded sample is authorised. National execution remains blocked.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    write_json(
        report_dir / "sample-plan-manifest.json",
        {
            "run_id": run_id,
            "generated_at": utc_now(),
            "status": "bounded_sample_planned",
            "network_requests_executed": 0,
            "inputs": [file_record(config_path, repo_root), file_record(source_path, repo_root)],
            "outputs": [file_record(parquet_path, repo_root, len(records)), file_record(csv_path, repo_root, len(records)), file_record(summary_path, repo_root)],
        },
    )
    return {"run_id": run_id, "records": records, "processed_dir": processed_dir, "report_dir": report_dir, "reused": False}


def _safe_results(records: list[dict[str, Any]], cache_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    outcomes = {(row["od_plan_id"], row["method"]): row for row in cache_records}
    results: list[dict[str, Any]] = []
    for row in records:
        pt = outcomes.get((row["od_plan_id"], "pt"))
        walk = outcomes.get((row["od_plan_id"], "walk"))
        duration = pt["duration_seconds"] if pt else None
        results.append(
            {
                "sample_pair_id": row["sample_pair_id"],
                "sample_distance_band": row["sample_distance_band"],
                "origin_geo_id": row["origin_geo_id"],
                "origin_subzone_name": row["origin_subzone_name"],
                "commercial_node_id": row["commercial_node_id"],
                "node_name": row["node_name"],
                "max_walk_distance_metres": row["max_walk_distance_metres"],
                "pt_category": pt["category"] if pt else "not_attempted",
                "pt_duration_seconds": duration,
                "pt_distance_metres": pt["distance_metres"] if pt else None,
                "within_primary_20_minutes": bool(duration is not None and float(duration) <= 1200),
                "walking_fallback_category": walk["category"] if walk else None,
                "walking_fallback_duration_seconds": walk["duration_seconds"] if walk else None,
            }
        )
    return results


def _summary(results: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    by_walk: dict[str, Any] = {}
    for walk in config["walk_distances_metres"]:
        subset = [row for row in results if row["max_walk_distance_metres"] == walk]
        success_durations = [float(row["pt_duration_seconds"]) for row in subset if row["pt_category"] == "success" and row["pt_duration_seconds"] is not None]
        by_walk[str(walk)] = {
            "planned_pairs": len(subset),
            "status_counts": dict(sorted(Counter(row["pt_category"] for row in subset).items())),
            "within_primary_20_minutes_count": sum(row["within_primary_20_minutes"] for row in subset),
            "median_successful_pt_minutes": round(statistics.median(success_durations) / 60, 2) if success_durations else None,
        }
    pt_complete = all(row["pt_category"] != "not_attempted" for row in results)
    fallback_complete = all(
        row["pt_category"] != "missing_route" or row["walking_fallback_category"] is not None
        for row in results
    )
    return {
        "status": "complete" if pt_complete and fallback_complete else "incomplete",
        "planned_pt_requests": len(results),
        "pt_results_complete": pt_complete,
        "required_walking_fallbacks_complete": fallback_complete,
        "by_max_walk_distance_metres": by_walk,
        "raw_response_persisted": False,
        "token_persisted": False,
        "national_execution_authorised": False,
    }


def execute_sample(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    config_path, config, _, run_id = _load(repo_root)
    plan = build_sample_plan(repo_root)
    records = plan["records"]
    cache_dir = repo_root / "data/interim/analysis" / config["analysis_date"] / run_id
    cache = RedactedRouteCache(cache_dir / "route-outcomes.sqlite")
    pending = any(not cache.has(str(row["od_plan_id"]), "pt") for row in records)
    prior_summary_path = plan["report_dir"] / "execution-summary.json"
    if pending and prior_summary_path.exists():
        prior_summary = json.loads(prior_summary_path.read_text(encoding="utf-8"))
        if prior_summary.get("status") == "complete":
            cache.close()
            return {
                "run_id": run_id,
                "status": "blocked_completed_sample_cache_incomplete",
                "authentication_requests": 0,
                "routing_requests": 0,
                "national_execution_authorised": False,
            }
    authentication_requests = 0
    execution: dict[str, Any] = {
        "attempted_requests": 0,
        "skipped_cached_primary_rows": 0,
        "walking_fallback_requests": 0,
        "stop_category": None,
        "cache_record_count": cache.count(),
        "raw_response_persisted": False,
        "token_persisted": False,
    }
    if pending:
        try:
            token = _authenticate(repo_root)
            authentication_requests = 1
        except OneMapUnavailable as error:
            cache.close()
            return {
                "run_id": run_id,
                "status": f"blocked_{error.category}",
                "authentication_requests": 0 if error.category == "missing_credentials" else 1,
                "routing_requests": 0,
                "national_execution_authorised": False,
            }
        execution = execute_route_batch(
            records,
            token=token,
            cache=cache,
            pace_seconds=float(config["pace_seconds"]),
            limit=int(config["maximum_total_route_requests"]),
        )
        token = ""
    cache_records = cache.records()
    cache.close()
    results = _safe_results(records, cache_records)
    summary = _summary(results, config)
    summary.update(
        {
            "run_id": run_id,
            "authentication_requests": authentication_requests,
            "routing_requests_this_invocation": execution["attempted_requests"],
            "stop_category": execution["stop_category"],
        }
    )
    report_dir = plan["report_dir"]
    results_path = report_dir / "bounded-walk-comparison-results.csv"
    write_csv(results_path, results)
    summary_path = report_dir / "execution-summary.json"
    write_json(summary_path, summary)
    markdown_path = report_dir / "analysis-summary.md"
    table_lines = [
        "| Maximum walking | Successful PT routes | Missing PT routes | Within 20 minutes | Median successful PT time |",
        "|---:|---:|---:|---:|---:|",
    ]
    for walk in config["walk_distances_metres"]:
        item = summary["by_max_walk_distance_metres"][str(walk)]
        counts = item["status_counts"]
        median = item["median_successful_pt_minutes"]
        table_lines.append(
            f"| {walk} m | {counts.get('success', 0)} | {counts.get('missing_route', 0)} | {item['within_primary_20_minutes_count']} | {median if median is not None else 'n/a'} min |"
        )
    markdown_path.write_text(
        "\n".join(
            [
                "# Bounded walking-distance comparison",
                "",
                f"Status: **{summary['status']}**  ",
                f"Route requests in this invocation: **{summary['routing_requests_this_invocation']}**",
                "",
                *table_lines,
                "",
                "This 20-pair diagnostic compares route behaviour only. It is not a national accessibility estimate or location ranking. The main proposed setting remains 500 m unless the comparison reveals a material coverage problem.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or execute the approved bounded OneMap walk-distance comparison")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    result = execute_sample(args.repo_root) if args.execute else build_sample_plan(args.repo_root)
    safe = {key: value for key, value in result.items() if key not in {"records", "processed_dir", "report_dir"}}
    if not args.execute:
        safe["planned_pt_requests"] = len(result["records"])
    print(json.dumps(safe, sort_keys=True, default=str))
    return 0 if result.get("status", "planned").startswith(("complete", "planned")) or not args.execute else 2


if __name__ == "__main__":
    raise SystemExit(main())
