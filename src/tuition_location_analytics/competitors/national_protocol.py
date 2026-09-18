from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from tuition_location_analytics.foundation.common import sha256_file, write_json


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _place_name(node_name: str) -> str:
    upper = " ".join(node_name.strip().upper().split())
    suffix = " MRT STATION"
    return upper[: -len(suffix)] if upper.endswith(suffix) else upper


def build_query_schedule(
    candidate_rows: list[dict[str, Any]],
    audit_rows: list[dict[str, Any]],
    templates: list[dict[str, str]],
    benchmark_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    raw_targets: list[tuple[str, dict[str, Any]]] = [
        ("candidate", row) for row in candidate_rows
    ] + [("outside_audit", row) for row in audit_rows] + [
        ("strategic_benchmark", row) for row in (benchmark_rows or [])
    ]
    targets: dict[str, dict[str, Any]] = {}
    roles: dict[str, set[str]] = {}
    benchmark_ids: dict[str, set[str]] = {}
    for role, row in raw_targets:
        node_id = str(row["commercial_node_id"])
        existing = targets.get(node_id)
        if existing is not None:
            for field in ("station_complex_id", "node_name", "planning_region"):
                if str(existing[field]) != str(row[field]):
                    raise RuntimeError(f"conflicting target identity for {node_id}: {field}")
        else:
            targets[node_id] = row
        roles.setdefault(node_id, set()).add(role)
        if role == "strategic_benchmark":
            benchmark_ids.setdefault(node_id, set()).add(str(row["benchmark_id"]))
    if not templates:
        raise RuntimeError("at least one discovery query template is required")

    schedule: list[dict[str, Any]] = []
    for node_id, row in sorted(targets.items()):
        node_roles = roles[node_id]
        target_type = (
            "candidate"
            if "candidate" in node_roles
            else "outside_audit"
            if "outside_audit" in node_roles
            else "strategic_benchmark"
        )
        place_name = _place_name(str(row["node_name"]))
        for template in templates:
            query_text = template["query_text_template"].format(place_name=place_name)
            digest = hashlib.sha256(
                f"{target_type}|{row['commercial_node_id']}|{template['template_id']}|{query_text}".encode(
                    "utf-8"
                )
            ).hexdigest()[:16]
            schedule.append(
                {
                    "query_id": f"NQ_{digest.upper()}",
                    "target_set": target_type,
                    "target_sets_json": json.dumps(sorted(node_roles)),
                    "strategic_benchmark": "strategic_benchmark" in node_roles,
                    "benchmark_ids_json": json.dumps(sorted(benchmark_ids.get(node_id, set()))),
                    "commercial_node_id": row["commercial_node_id"],
                    "station_complex_id": row["station_complex_id"],
                    "node_name": row["node_name"],
                    "place_name": place_name,
                    "planning_region": row["planning_region"],
                    "template_id": template["template_id"],
                    "template_code": template["template_code"],
                    "channel": "WEB_SEARCH",
                    "query_text": query_text,
                    "execution_status": "not_started",
                }
            )
    if len({row["query_id"] for row in schedule}) != len(schedule):
        raise RuntimeError("generated national query IDs are not unique")
    return schedule


def run(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    config_path = repo_root / "config/competitors/national_discovery.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    inputs = {
        key: (repo_root / reference).resolve() for key, reference in config["inputs"].items()
    }
    for path in inputs.values():
        if not path.is_relative_to(repo_root) or not path.is_file():
            raise RuntimeError(f"national-protocol input is missing or outside repository: {path}")
    candidates = _read_csv(inputs["candidate_freeze_ref"])
    audit = _read_csv(inputs["outside_audit_ref"])
    benchmark_config = json.loads(inputs["strategic_benchmarks_ref"].read_text(encoding="utf-8"))
    benchmark_rows = [
        {**member, "benchmark_id": benchmark["benchmark_id"]}
        for benchmark in benchmark_config["benchmarks"]
        for member in benchmark["node_members"]
    ]
    schedule = build_query_schedule(
        candidates, audit, config["query_templates"], benchmark_rows
    )
    unique_target_ids = {row["commercial_node_id"] for row in schedule}
    output_path = repo_root / "config/competitors/national_query_schedule.json"
    payload = {
        "schedule_version": "2026-09-18.1",
        "frozen_at": "2026-09-18",
        "status": "frozen_not_executed",
        "protocol_config_ref": config_path.relative_to(repo_root).as_posix(),
        "protocol_config_sha256": sha256_file(config_path),
        "candidate_node_count": len(candidates),
        "outside_audit_node_count": len(audit),
        "strategic_benchmark_node_count": len(
            {row["commercial_node_id"] for row in benchmark_rows}
        ),
        "unique_target_node_count": len(unique_target_ids),
        "template_count": len(config["query_templates"]),
        "query_count": len(schedule),
        "queries": schedule,
    }
    write_json(output_path, payload)
    return {
        "status": payload["status"],
        "candidate_node_count": len(candidates),
        "outside_audit_node_count": len(audit),
        "strategic_benchmark_node_count": len(
            {row["commercial_node_id"] for row in benchmark_rows}
        ),
        "unique_target_node_count": len(unique_target_ids),
        "query_count": len(schedule),
        "output_ref": output_path.relative_to(repo_root).as_posix(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze the national competitor query schedule")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(run(args.repo_root), indent=2))


if __name__ == "__main__":
    main()
