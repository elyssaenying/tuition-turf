from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from . import s001, s007
from .common import read_env, scan_reportable_files, sha256_file, utc_now, write_json


def _report_markdown(result: dict[str, Any]) -> str:
    first = result["s001"]
    second = result["s007"]
    validation = result["validation"]
    t3_candidates = first.get("inspection", {}).get("t3_candidates", [])
    lines = [
        "# Two-source preflight report",
        "",
        f"Generated: {result['generated_at']}",
        "",
        "## Boundary",
        "",
        "Only S001 was acquired. S007 was limited to the fixed fixture and was skipped if credentials were unavailable. No other dataset, competitor source, premises source or national routing matrix was acquired.",
        "",
        "## S001 — Population Trends 2025 geospatial ZIP",
        "",
        f"- Status: `{first['status']}`",
        f"- Storage: `{first.get('storage_ref', 'not created')}`",
        f"- Bytes: `{first.get('byte_size', 'unknown')}`",
        f"- SHA-256: `{first.get('sha256', 'unknown')}`",
        f"- Requested/final URL match: `{first.get('requested_url') == first.get('final_url')}`",
        f"- HTTP status: `{first.get('http_status', 'unknown')}`",
        f"- T3 candidates: `{', '.join(t3_candidates) if t3_candidates else 'none detected'}`",
        f"- Full dataset loaded/transformed: `{first.get('inspection', {}).get('complete_dataset_loaded', False)}`",
        f"- Raw redistribution: `{first.get('licence_assessment', {}).get('status', 'not assessed')}`",
        "",
        "The archive listing and bounded T3 header/schema inspection are recorded in the machine-readable result. Raw redistribution remains unapproved unless the resource-specific terms are established.",
        "",
        "## S007 — OneMap routing",
        "",
        f"- Status: `{second['status']}`",
        f"- Fixture: `{second['fixture_ref']}`",
        f"- Planned search requests: `{second['planned_search_requests']}`",
        f"- Executed search requests: `{second['executed_search_requests']}`",
        f"- Planned route requests: `{second['planned_route_requests']}`",
        f"- Executed route requests: `{second['executed_route_requests']}`",
        f"- Journey date/time: `{second['journey_date']} {second['journey_time']}`",
        "",
        second.get("limitation", second.get("persistence_limitation", "")),
        "",
        "## Validation",
        "",
        f"- Independent S001 checksum match: `{validation['independent_s001_checksum_match']}`",
        f"- S007 route boundary respected: `{validation['s007_route_request_boundary_respected']}`",
        f"- Secret-like values in reportable files: `{validation['secret_scan_findings']}`",
        "",
        "## Remaining blockers",
        "",
    ]
    blockers = result["remaining_blockers"]
    lines.extend(f"- {item}" for item in blockers)
    return "\n".join(lines) + "\n"


def run(repo_root: Path, output_dir: Path) -> dict[str, Any]:
    first = s001.run(repo_root)
    second = s007.run(repo_root)
    credentials = read_env(repo_root / ".env")
    independent_checksum = sha256_file(repo_root / first["storage_ref"])
    findings = scan_reportable_files(repo_root, credentials.values())
    validation = {
        "independent_s001_checksum_match": independent_checksum == first["sha256"],
        "s007_route_request_boundary_respected": second["executed_route_requests"]
        in {0, second["planned_route_requests"]},
        "secret_scan_findings": findings,
    }
    blockers = []
    if first["status"] not in {"completed", "completed_with_limitations"}:
        blockers.append("S001 T3 schema could not be fully established from the bounded inspection.")
    if first["licence_assessment"]["status"] != "raw_redistribution_permitted":
        blockers.append("S001 resource-specific raw redistribution permission remains unestablished.")
    if second["status"] != "completed":
        blockers.append("S007 remains blocked until the local ignored credentials are supplied and the fixed preflight succeeds.")
    if findings:
        blockers.append("Secret-redaction scan reported one or more findings.")
    result = {
        "schema_version": "0.3.0",
        "preflight_version": "0.1.0",
        "generated_at": utc_now(),
        "s001": first,
        "s007": second,
        "validation": validation,
        "remaining_blockers": blockers,
    }
    machine_path = output_dir / "preflight-result.json"
    report_path = output_dir / "preflight-report.md"
    write_json(machine_path, result)
    report_path.write_text(_report_markdown(result), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the bounded S001/S007 preflight")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=Path("reports/preflight/2026-09-12"))
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    result = run(repo_root, output_dir)
    summary = {
        "s001_status": result["s001"]["status"],
        "s007_status": result["s007"]["status"],
        "secret_scan_findings": len(result["validation"]["secret_scan_findings"]),
    }
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
