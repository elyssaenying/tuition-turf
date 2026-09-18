from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

import pyarrow.parquet as pq

from tuition_location_analytics.competitors.geocode import OneMapUnavailable, _authenticate
from tuition_location_analytics.foundation.common import sha256_file, write_json

from .routing_execute import (
    WALK_FALLBACK_PT_CATEGORIES,
    RedactedRouteCache,
    execute_route_batch_concurrent,
)


def _repo_file(repo_root: Path, reference: str) -> Path:
    path = (repo_root / reference).resolve()
    if not path.is_relative_to(repo_root.resolve()) or not path.is_file():
        raise RuntimeError(f"configured execution input is missing or outside repository: {reference}")
    return path


def load_authorised_plan(repo_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    config = json.loads(
        (repo_root / "config/accessibility/national_routing_plan.json").read_text(encoding="utf-8")
    )
    if config.get("execution_status") != "approved_for_national_execution":
        raise RuntimeError("national route execution is not approved")
    if config.get("national_execution_authorised") is not True:
        raise RuntimeError("national route execution authority is false")
    path = _repo_file(repo_root, config["authorised_execution_plan"])
    if sha256_file(path) != config["authorised_execution_plan_sha256"]:
        raise RuntimeError("authorised national route plan checksum mismatch")
    rows = pq.read_table(path).to_pylist()
    if len(rows) != 96_944 or len({row["od_plan_id"] for row in rows}) != len(rows):
        raise RuntimeError("authorised national route plan count or identity check failed")
    if {int(row["max_walk_distance_metres"]) for row in rows} != {500}:
        raise RuntimeError("authorised national route plan does not use only 500 m max walking")
    if {str(row["scenario_id"]) for row in rows} != {
        "primary_weekday_after_school",
        "weekend_comparison",
    }:
        raise RuntimeError("authorised national route plan scenario check failed")
    return config, rows


def build_progress(
    rows: list[dict[str, Any]], cache_records: list[dict[str, Any]]
) -> dict[str, Any]:
    pt = {row["od_plan_id"]: row for row in cache_records if row["method"] == "pt"}
    walk = {row["od_plan_id"]: row for row in cache_records if row["method"] == "walk"}
    pt_counts = Counter(row["category"] for row in pt.values())
    fallback_ids = {
        od_id
        for od_id, row in pt.items()
        if row["category"] in WALK_FALLBACK_PT_CATEGORIES
    }
    fallback_complete = sum(od_id in walk for od_id in fallback_ids)
    planned = len(rows)
    pt_complete = len(pt)
    complete = pt_complete == planned and fallback_complete == len(fallback_ids)
    return {
        "status": "complete" if complete else "in_progress",
        "planned_pt_requests": planned,
        "completed_pt_requests": pt_complete,
        "completed_pt_percent": round(100 * pt_complete / planned, 3),
        "pt_status_counts": dict(sorted(pt_counts.items())),
        "walking_fallbacks_required": len(fallback_ids),
        "walking_fallbacks_completed": fallback_complete,
        "total_cached_safe_outcomes": len(cache_records),
        "raw_response_persisted": False,
        "token_persisted": False,
    }


def _write_progress(report_dir: Path, progress: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    write_json(report_dir / "progress.json", progress)
    counts = progress["pt_status_counts"]
    (report_dir / "progress.md").write_text(
        "\n".join(
            [
                "# National OneMap routing progress",
                "",
                f"- Status: **{progress['status']}**",
                f"- PT routes completed: **{progress['completed_pt_requests']:,} / {progress['planned_pt_requests']:,} ({progress['completed_pt_percent']:.3f}%)**",
                f"- Successful PT routes: **{counts.get('success', 0):,}**",
                f"- Missing PT routes: **{counts.get('missing_route', 0):,}**",
                f"- Walking fallbacks completed: **{progress['walking_fallbacks_completed']:,} / {progress['walking_fallbacks_required']:,}**",
                "",
                "Only safe status, duration and distance outcomes are cached. Credentials, tokens and raw responses are not persisted.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def execute_one_chunk(repo_root: Path, *, request_limit: int | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    config, rows = load_authorised_plan(repo_root)
    run_name = "national_routing_execution_" + config["authorised_execution_plan_run_id"]
    cache_path = repo_root / "data/interim/analysis" / config["plan_date"] / run_name / "route-outcomes.sqlite"
    report_dir = repo_root / "reports/analysis" / config["plan_date"] / run_name
    cache = RedactedRouteCache(cache_path)
    before = build_progress(rows, cache.records())
    if before["status"] == "complete":
        cache.close()
        return {**before, "routing_requests_this_chunk": 0, "authentication_requests_this_chunk": 0}
    try:
        token = _authenticate(repo_root)
    except OneMapUnavailable as error:
        cache.close()
        blocked = {
            **before,
            "status": f"blocked_{error.category}",
            "routing_requests_this_chunk": 0,
            "authentication_requests_this_chunk": 0 if error.category == "missing_credentials" else 1,
        }
        _write_progress(report_dir, blocked)
        return blocked
    approved_limit = int(config["approved_chunk_request_limit"])
    active_limit = approved_limit if request_limit is None else int(request_limit)
    if active_limit <= 0 or active_limit > approved_limit:
        cache.close()
        raise ValueError("request limit must be positive and no greater than the approved chunk limit")
    execution = execute_route_batch_concurrent(
        rows,
        token=token,
        cache=cache,
        request_start_interval_seconds=float(config["execution_pace_seconds"]),
        max_workers=int(config["concurrent_request_workers"]),
        limit=active_limit,
    )
    token = ""
    progress = build_progress(rows, cache.records())
    cache.close()
    progress.update(
        {
            "routing_requests_this_chunk": execution["attempted_requests"],
            "walking_fallback_requests_this_chunk": execution["walking_fallback_requests"],
            "authentication_requests_this_chunk": 1,
            "stop_category": execution["stop_category"],
            "execution_plan_run_id": config["authorised_execution_plan_run_id"],
            "chunk_request_limit": active_limit,
            "pace_seconds": config["execution_pace_seconds"],
            "concurrent_workers": config["concurrent_request_workers"],
        }
    )
    if execution["stop_category"] is not None:
        progress["status"] = "stopped_" + str(execution["stop_category"])
    _write_progress(report_dir, progress)
    return progress


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute the approved national OneMap plan in safe resumable chunks")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--continuous", action="store_true")
    parser.add_argument("--request-limit", type=int)
    args = parser.parse_args(argv)
    while True:
        result = execute_one_chunk(args.repo_root, request_limit=args.request_limit)
        print(json.dumps(result, sort_keys=True), flush=True)
        if result["status"] == "complete":
            return 0
        if result["status"].startswith(("blocked_", "stopped_")):
            return 2
        if int(result.get("routing_requests_this_chunk", 0)) <= 0:
            return 3
        if not args.continuous:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
