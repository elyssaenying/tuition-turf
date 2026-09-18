from __future__ import annotations

import csv
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Iterable

from tuition_location_analytics.analysis.routing_execute import (
    STOP_CATEGORIES,
    RedactedRouteCache,
    _route_url,
    parse_safe_route_outcome,
)
from tuition_location_analytics.competitors.geocode import _authenticate, _json_request
from tuition_location_analytics.foundation.common import utc_now, write_json


def _coordinate_key(longitude: float, latitude: float) -> str:
    return f"{longitude:.7f},{latitude:.7f}"


def build_walk_requests(
    branches: Iterable[dict[str, Any]],
    exits: Iterable[dict[str, Any]],
    node_members: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """Build one request per unique building coordinate, node and preserved exit.

    Multiple branches in the same building share the route result but remain
    separate branches when catchment membership is expanded later.
    """
    coordinate_branches: dict[str, list[str]] = {}
    coordinates: dict[str, tuple[float, float]] = {}
    for branch in branches:
        longitude = branch.get("longitude_wgs84")
        latitude = branch.get("latitude_wgs84")
        if longitude is None or latitude is None:
            continue
        key = _coordinate_key(float(longitude), float(latitude))
        coordinates[key] = (float(longitude), float(latitude))
        coordinate_branches.setdefault(key, []).append(str(branch["branch_id"]))

    station_to_node = {
        str(member["station_complex_id"]): str(member["commercial_node_id"])
        for member in node_members
    }
    rows: list[dict[str, Any]] = []
    for exit_row in exits:
        station_id = str(exit_row["station_complex_id"])
        node_id = station_to_node.get(station_id)
        if node_id is None:
            continue
        for coordinate_key, (longitude, latitude) in sorted(coordinates.items()):
            identity = "|".join(
                [node_id, str(exit_row["transit_point_id"]), coordinate_key, "walk"]
            )
            rows.append(
                {
                    "od_plan_id": "CW_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16].upper(),
                    "commercial_node_id": node_id,
                    "station_complex_id": station_id,
                    "transit_point_id": str(exit_row["transit_point_id"]),
                    "coordinate_key": coordinate_key,
                    "origin_longitude_wgs84": float(exit_row["longitude_wgs84"]),
                    "origin_latitude_wgs84": float(exit_row["latitude_wgs84"]),
                    "destination_longitude_wgs84": longitude,
                    "destination_latitude_wgs84": latitude,
                }
            )
    return rows, coordinate_branches


def summarise_memberships(
    requests: Iterable[dict[str, Any]],
    outcomes: dict[str, dict[str, Any]],
    coordinate_branches: dict[str, list[str]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in requests:
        grouped.setdefault((row["commercial_node_id"], row["coordinate_key"]), []).append(row)

    memberships: list[dict[str, Any]] = []
    for (node_id, coordinate_key), rows in sorted(grouped.items()):
        successful = []
        categories: set[str] = set()
        for row in rows:
            outcome = outcomes.get(row["od_plan_id"])
            if outcome is None:
                categories.add("not_attempted")
                continue
            categories.add(str(outcome["category"]))
            if outcome["category"] == "success" and outcome.get("duration_seconds") is not None:
                successful.append((float(outcome["duration_seconds"]), row, outcome))
        best = min(successful, key=lambda item: item[0]) if successful else None
        for branch_id in sorted(coordinate_branches[coordinate_key]):
            memberships.append(
                {
                    "branch_id": branch_id,
                    "commercial_node_id": node_id,
                    "route_status": "resolved" if best else "unresolved",
                    "minimum_walk_duration_seconds": best[0] if best else None,
                    "minimum_walk_distance_metres": best[2].get("distance_metres") if best else None,
                    "best_exit_transit_point_id": best[1]["transit_point_id"] if best else None,
                    "inside_10_minute_walk": best[0] <= 600 if best else None,
                    "inside_15_minute_walk": best[0] <= 900 if best else None,
                    "attempted_exit_count": len(rows),
                    "observed_route_categories": sorted(categories),
                }
            )
    return memberships


def run_private_ledger_walk(
    repo_root: Path,
    ledger_path: Path,
    node_members: Iterable[dict[str, Any]],
    *,
    output_stem: str,
    pace_seconds: float = 0.15,
    benchmark_id: str | None = None,
) -> dict[str, Any]:
    """Calculate walking memberships for one private evidence ledger.

    The ledger owns the validated branch list and its geocode-cache reference;
    callers provide the frozen node membership. Only branches explicitly marked
    eligible are routed. This keeps stale, online-only and out-of-scope leads in
    the audit trail without allowing them into competitor counts.
    """
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    geocode_ref = ledger.get("geocode_cache_ref")
    if not isinstance(geocode_ref, str) or not geocode_ref:
        raise RuntimeError("private ledger does not identify its geocode cache")
    geocode_path = repo_root / "data/interim/competitors/national" / geocode_ref
    geocodes = json.loads(geocode_path.read_text(encoding="utf-8"))["records"]
    eligible_branch_ids = {
        str(lead["branch_id"])
        for lead in ledger.get("leads", [])
        if lead.get("eligible_for_catchment") is True and lead.get("branch_id")
    }
    if eligible_branch_ids:
        geocodes = [row for row in geocodes if str(row.get("branch_id")) in eligible_branch_ids]

    with (repo_root / "data/processed/nodes/2026-09-13/station_complex_exits.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        exits = list(csv.DictReader(handle))
    requests, coordinate_branches = build_walk_requests(geocodes, exits, node_members)
    cache = RedactedRouteCache(
        repo_root / f"data/interim/competitors/national/{output_stem}-walk-routes.sqlite"
    )
    attempted = 0
    stop_category: str | None = None
    try:
        missing = [row for row in requests if cache.get(row["od_plan_id"], "walk") is None]
        token = _authenticate(repo_root) if missing else ""
        for row in missing:
            outcome = parse_safe_route_outcome(
                _json_request(_route_url(row, "walk"), token=token), mode="walk"
            )
            cache.put(row["od_plan_id"], "walk", outcome)
            attempted += 1
            if outcome.category in STOP_CATEGORIES:
                stop_category = outcome.category
                break
            if pace_seconds:
                time.sleep(pace_seconds)
        safe_outcomes = {
            row["od_plan_id"]: {
                "category": outcome.category,
                "http_status": outcome.http_status,
                "duration_seconds": outcome.duration_seconds,
                "distance_metres": outcome.distance_metres,
            }
            for row in requests
            if (outcome := cache.get(row["od_plan_id"], "walk")) is not None
        }
        memberships = summarise_memberships(requests, safe_outcomes, coordinate_branches)
        result = {
            "batch_id": ledger.get("batch_id"),
            "benchmark_id": benchmark_id or ledger.get("benchmark_id"),
            "executed_at": utc_now(),
            "status": "complete" if len(safe_outcomes) == len(requests) and stop_category is None else "incomplete",
            "privacy_boundary": ledger["privacy_boundary"],
            "planned_route_requests": len(requests),
            "attempted_route_requests_this_run": attempted,
            "completed_route_requests": len(safe_outcomes),
            "unique_branch_coordinates": len(coordinate_branches),
            "geocoded_branch_count": sum(len(ids) for ids in coordinate_branches.values()),
            "unresolved_geocode_branch_count": len(geocodes) - sum(len(ids) for ids in coordinate_branches.values()),
            "stop_category": stop_category,
            "memberships": memberships,
            "safety": {
                "token_persisted": False,
                "raw_authentication_response_recorded": False,
                "raw_route_responses_recorded": False,
            },
        }
        output_path = repo_root / f"data/interim/competitors/national/{output_stem}-walk-memberships.private.json"
        write_json(output_path, result)
        return result
    finally:
        cache.close()


def run_bukit_timah_benchmark(repo_root: Path, *, pace_seconds: float = 0.15) -> dict[str, Any]:
    benchmark_config = json.loads(
        (repo_root / "config/competitors/strategic_benchmarks.json").read_text(encoding="utf-8")
    )
    benchmark = next(
        row for row in benchmark_config["benchmarks"] if row["benchmark_id"] == "bukit_timah_tuition_hub"
    )
    ledger_path = repo_root / "data/interim/competitors/national/bukit_timah_benchmark_batch.private.json"
    return run_private_ledger_walk(
        repo_root,
        ledger_path,
        benchmark["node_members"],
        output_stem="bukit-timah",
        pace_seconds=pace_seconds,
        benchmark_id=benchmark["benchmark_id"],
    )


def run_national_batch(
    repo_root: Path,
    ledger_path: Path,
    *,
    output_stem: str,
    pace_seconds: float = 0.15,
) -> dict[str, Any]:
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    node_members = ledger.get("node_members")
    if not isinstance(node_members, list) or not node_members:
        raise RuntimeError("national batch ledger does not identify its node members")
    return run_private_ledger_walk(
        repo_root,
        ledger_path,
        node_members,
        output_stem=output_stem,
        pace_seconds=pace_seconds,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Calculate walking catchments for a validated competitor batch")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--pace-seconds", type=float, default=0.15)
    parser.add_argument(
        "--ledger",
        type=Path,
        help="Private national-batch ledger path, relative to the repository or absolute",
    )
    parser.add_argument("--output-stem", help="Safe filename stem for national-batch outputs")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    if args.ledger:
        if not args.output_stem:
            parser.error("--output-stem is required with --ledger")
        ledger_path = args.ledger if args.ledger.is_absolute() else repo_root / args.ledger
        result = run_national_batch(
            repo_root,
            ledger_path,
            output_stem=args.output_stem,
            pace_seconds=args.pace_seconds,
        )
    else:
        result = run_bukit_timah_benchmark(repo_root, pace_seconds=args.pace_seconds)
    print(json.dumps({key: value for key, value in result.items() if key != "memberships"}, indent=2))


if __name__ == "__main__":
    main()
