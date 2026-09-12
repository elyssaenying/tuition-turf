from __future__ import annotations

from typing import Any


def data_quality_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Foundational data-quality report",
        "",
        f"Run ID: `{report['run_id']}`",
        f"Overall status: `{report['overall_status']}`",
        "",
        "## Check results",
        "",
        "| Check | Source/table | Status | Observation |",
        "|---|---|---|---|",
    ]
    for check in report["checks"]:
        observation = str(check["observation"]).replace("|", "\\|")
        lines.append(
            f"| `{check['check_id']}` | {check['source_id']} / `{check['table']}` | "
            f"`{check['status']}` | {observation} |"
        )
    lines.extend(
        [
            "",
            "Warnings preserve the affected limitation; failures block release of the affected table. No failed check is downgraded to make the run pass.",
        ]
    )
    return "\n".join(lines) + "\n"


def geography_join_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# S001–S003 geography join report",
        "",
        f"Run ID: `{report['run_id']}`",
        "",
        f"- Population planning-area/subzone pairs: `{summary['population_pair_count']}`",
        f"- Exact normalized matches: `{summary['matched_count']}`",
        f"- Unmatched population pairs: `{summary['unmatched_count']}`",
        f"- Ambiguous population pairs: `{summary['ambiguous_count']}`",
        f"- Boundary-only subzones: `{summary['boundary_only_count']}`",
        f"- Fuzzy matching used: `{summary['fuzzy_matching_used']}`",
        f"- Normalization: {summary['normalization']}",
        "",
        "## Unmatched population pairs",
        "",
    ]
    if summary["unmatched"]:
        lines.extend(
            f"- {item['planning_area_name']} / {item['subzone_name']}"
            for item in summary["unmatched"]
        )
    else:
        lines.append("None.")
    lines.extend(["", "## Ambiguous population pairs", ""])
    if summary["ambiguous"]:
        lines.extend(
            f"- {item['planning_area_name']} / {item['subzone_name']}: "
            + ", ".join(item["candidate_subzone_codes"])
            for item in summary["ambiguous"]
        )
    else:
        lines.append("None.")
    lines.extend(["", "## Boundary-only subzones", ""])
    if summary["boundary_only"]:
        lines.extend(
            f"- {item['planning_area_name']} / {item['subzone_name']} (`{item['subzone_code']}`)"
            for item in summary["boundary_only"]
        )
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def completion_markdown(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    s007 = payload["s007_preflight"]
    geocode = payload["school_geocoding"]
    secret_scan = payload.get("foundation_secret_scan")
    lines = [
        "# Foundational nationwide acquisition completion report",
        "",
        f"Run ID: `{payload['run_id']}`",
        f"Status: `{payload['status']}`",
        "",
        "## Completed",
        "",
        f"- S001: `{counts['population_age_rows']}` target-age rows and `{counts['population_subzones']}` subzone proxy rows.",
        f"- S003: `{counts['boundary_subzones']}` MP2019 subzone geometries.",
        f"- S004: `{counts['schools']}` schools; `{counts['schools_with_coordinates']}` have exact-postal OneMap coordinates.",
        f"- S005: `{counts['mrt_exits']}` MRT exit points.",
        f"- S006: `{counts['bus_stops']}` bus-stop points.",
        f"- S001–S003 geography matches: `{counts['geography_matches']}`; unmatched `{counts['geography_unmatched']}`; ambiguous `{counts['geography_ambiguous']}`.",
        *(
            [
                f"- Foundation output secret scan: `{secret_scan['status']}` with `{secret_scan['assurance']}` assurance; generic scan `{secret_scan['generic_pattern_scan_status']}`; exact-value comparison `{secret_scan['exact_credential_comparison_status']}`; `{secret_scan['finding_count']}` finding files across `{secret_scan['scanned_file_count']}` scanned text outputs."
            ]
            if secret_scan
            else []
        ),
        "",
        "## Preserved limitations",
        "",
        "- S001 counts are rounded to the nearest 10; summed ages compound that source precision limitation. The raw ZIP remains excluded from publication because resource-specific redistribution permission is unestablished.",
        "- S003 is the indicative MP2019 no-sea boundary layer.",
        f"- S004 contains no native coordinates. Exact-postal S007 search resolved `{geocode['status_counts'].get('resolved_exact_postal_unique_coordinate', 0)}` records; unresolved/ambiguous records remain null.",
        f"- S007 preflight walking routes succeeded `{s007['walking_success']}/30`; PT routes succeeded `{s007['pt_success']}/30` with `{s007['pt_missing_route']}` explicit missing routes and no rate limiting. Missing PT routes require the documented walking/proximity fallback and were not imputed.",
        "- MRT exits are access points, not station schedules or travel-time observations; bus stops contain no service or timetable information.",
        "",
        "## Unresolved school coordinates",
        "",
    ]
    if payload["unresolved_school_coordinates"]:
        lines.extend(
            f"- {item['school_name']} (`{item['postal_code']}`): `{item['coordinate_status']}`"
            for item in payload["unresolved_school_coordinates"]
        )
    else:
        lines.append("None.")
    lines.extend(
        [
        "",
        "## Reproduce and validate",
        "",
        "```sh",
        "python3.12 -m venv .venv",
        ".venv/bin/python -m pip install -r requirements.lock",
        "PYTHONPATH=src .venv/bin/python -m tuition_location_analytics.foundation.cli --repo-root .",
        "PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v",
        ".venv/bin/python -m compileall -q src tests",
        ".venv/bin/python -m pip check",
        "```",
        "",
        "An identical rerun reuses checksum-verified immutable snapshots and the redacted school-geocode cache; it makes no further network request and reproduces the processed/report file checksums.",
        "",
        "## Boundary respected",
        "",
        "No competitor source, national routing matrix, node score, financial model or dashboard was created.",
        "",
        "## Exact next implementation task",
        "",
        "Construct and manually audit versioned MRT station complexes and the evidence-qualified commercial-node inventory from these foundational layers. Resolve any remaining school-coordinate exceptions explicitly. Do not run national routing or scoring until the candidate inventory and travel thresholds are frozen.",
        ]
    )
    return "\n".join(lines) + "\n"
