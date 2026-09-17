from __future__ import annotations

from typing import Any


def quality_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Station-complex and commercial-node data-quality report",
        "",
        f"Run ID: `{report['run_id']}`",
        f"Overall status: `{report['overall_status']}`",
        "",
        "| Check | Table | Status | Observation |",
        "|---|---|---|---|",
    ]
    for check in report["checks"]:
        observation = str(check["observation"]).replace("|", "\\|")
        lines.append(
            f"| `{check['check_id']}` | `{check['table']}` | `{check['status']}` | {observation} |"
        )
    lines.extend(
        [
            "",
            "A failure blocks phase approval. Warnings and limited assurance remain explicit and are not converted to passes.",
        ]
    )
    return "\n".join(lines) + "\n"


def station_audit_markdown(report: dict[str, Any]) -> str:
    quality = report["quality"]
    lines = [
        "# MRT station-complex grouping audit",
        "",
        f"Run ID: `{report['run_id']}`",
        f"Station-override config version: `{report.get('override_config_version', 'n/a')}`",
        f"Review-disposition config version: `{report.get('disposition_config_version', 'n/a')}`",
        "",
        f"- Input S005 exits: `{quality['input_exit_count']}`",
        f"- Membership rows: `{quality['membership_row_count']}`",
        f"- Exact-name station complexes: `{quality['station_complex_count']}`",
        f"- Named MRT complexes: `{quality['mrt_complex_count']}`",
        f"- LRT complexes retained but not promoted to MRT node candidates: `{quality['lrt_complex_count']}`",
        f"- Code-only or unknown complexes: `{quality['code_only_or_unknown_complex_count']}`",
        f"- Complexes with repeated exit labels: `{quality['repeated_exit_label_complex_count']}`",
        f"- Complexes exceeding the dispersion review threshold: `{quality['dispersed_complex_count']}`",
        f"- S026 exact-name corroboration matches: `{quality['s026_exact_match_complex_count']}`",
        f"- S026 unmatched complexes retained: `{quality['s026_unmatched_complex_count']}`",
        f"- Station overrides applied (source labels resolved): `{quality['station_override_source_label_count']}`",
        f"- Configured override labels not found in this exit snapshot: `{quality['unused_station_override_labels']}`",
        f"- Operational-status counts: `{quality['operational_status_counts']}`",
        f"- Station-level review items open/closed: `{quality['open_review_item_count']}` / `{quality['closed_review_item_count']}`",
        "",
        "Grouping rule: " + quality["grouping_method"],
        "",
        "Review-threshold rationale: " + quality["dispersion_threshold_rationale"],
        "",
        "No fuzzy matching, distance-based merging or silent splitting was used. Every merge or rename is backed by an authoritative station-code or opening-date override, never coordinates alone. Later accessibility must use the closest valid member exit, not the representative point or centroid.",
        "",
        "## Previous-to-current station-complex mapping",
        "",
        "| Previous label | Previous complex ID | Resolution | New station name | New complex ID | Merged into pre-existing complex | Operational status |",
        "|---|---|---|---|---|---|---|",
    ]
    crosswalk = report.get("station_complex_id_crosswalk", [])
    if crosswalk:
        for row in crosswalk:
            lines.append(
                f"| `{row['previous_normalized_station_name']}` | `{row['previous_station_complex_id']}` | "
                f"{row['resolution']} | `{row['new_normalized_station_name']}` | `{row['new_station_complex_id']}` | "
                f"{row['merged_into_pre_existing_complex']} | `{row['operational_status']}` |"
            )
    else:
        lines.append("| _none_ | | | | | | |")
    return "\n".join(lines) + "\n"


def commercial_method_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Commercial-evidence methodology",
        "",
        f"Run ID: `{report['run_id']}`",
        "",
        "## Frozen evidence definition",
        "",
        "MP2025 accepted categories:",
        "",
        *[f"- `{category}`" for category in report["accepted_land_use_categories"]],
        "",
        "Business/industrial, White, hotel, educational and unrelated land uses are excluded. The accepted categories are explicit commercial or explicit commercial-mixed zoning labels.",
        "",
        "Evidence is calculated inside unioned 400 m and 800 m straight-line buffers around every valid exit in a complex, using EPSG:3414. These bands are proximity measurements, not walking times. Intersections report relevant area, buffer share, feature count, category areas and nearest distance.",
        "",
        "## Independence and qualification",
        "",
        f"A `qualified` node requires at least `{report['minimum_independent_signals_for_qualified']}` independent positive signal families at 800 m. The two MP2025 bands are measurements of one zoning signal, not two independent signals. A station is an accessibility anchor and is never counted as commercial evidence.",
        "",
        "The HDB property table's commercial flag could not be deterministically linked to HDB building geometry: the tables expose no shared stable identifier, and the building layer's street code is opaque. No uncertain address join or large OneMap geocode was performed. The missing HDB signal remains null rather than zero.",
        "",
        "## Second independent-signal validation protocol (documented, not yet implemented)",
        "",
        f"Status: `{report['second_independent_signal_validation_protocol']['status']}`. "
        + report["second_independent_signal_validation_protocol"]["reason_not_implemented_now"],
        "",
        *[f"{step}" for step in report["second_independent_signal_validation_protocol"]["protocol"]],
        "",
        "No node may be marked `qualified` until this protocol is executed and passes; `provisional` nodes remain in the analytical candidate pool in the meantime.",
        "",
        "## Interpretation limits",
        "",
        "MP2025 is Dec 2025 zoning context, while population remains on MP2019 subzones. Zoning does not prove current occupancy, availability, quoted rent, owner consent, permitted tuition use or URA/SCDF eligibility.",
    ]
    return "\n".join(lines) + "\n"


def completion_markdown(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    scan = payload["secret_scan"]
    lines = [
        "# Station-complex and commercial-node phase completion report",
        "",
        f"Run ID: `{payload['run_id']}`",
        f"Status: `{payload['status']}`",
        "",
        f"- Station complexes: `{counts['station_complexes']}` from `{counts['station_exits']}` preserved exits.",
        f"- Station overrides applied: `{counts['station_overrides_applied']}`; crosswalk rows: `{counts['station_complex_id_crosswalk_rows']}`.",
        f"- Operational-status counts: `{counts['operational_status_counts']}`.",
        f"- Commercial-node candidates: `{counts['commercial_node_candidates']}` (`{counts['excluded_not_yet_operational']}` excluded as not yet operational within the decision horizon).",
        f"- Qualification statuses: `{counts['qualification_status_counts']}`.",
        f"- Commercial-evidence rows: `{counts['commercial_evidence_rows']}`.",
        f"- Review-queue rows: `{counts['review_queue_rows']}` (`{counts['review_queue_open_rows']}` open, `{counts['review_queue_closed_rows']}` closed); by category `{counts['review_issue_category_counts']}`.",
        f"- Secret scan: `{scan['status']}` with `{scan['assurance']}` assurance and `{scan['finding_count']}` finding files.",
        "",
        "No competitor acquisition, national routing, scoring, financial modelling, recommendations or dashboard work was performed.",
        "",
        "## Exact next task",
        "",
        "Complete the bounded human review queue and approve the versioned station-complex/commercial-node inventory, then freeze travel thresholds and the competitor-discovery audit design before any competitor acquisition or nationwide routing.",
    ]
    return "\n".join(lines) + "\n"
