from __future__ import annotations

from typing import Any


def coverage_markdown(report: dict[str, Any]) -> str:
    diag = report["channel_diagnostics"]
    gates = report["acceptance_gates"]
    lines = [
        "# Pilot competitor-discovery coverage report",
        "",
        f"Run ID: `{report['run_id']}`",
        f"Analysis cutoff: `{report['analysis_cutoff']}`",
        "",
        "**This is a PILOT report (10 of 55 planning areas). It is not national coverage and must not be used to rank locations.**",
        "",
        "## Protocol completion",
        "",
        f"- {report['protocol_completion']}",
        "",
        "## Discovery observation grain",
        "",
        f"- Raw discovery observations: `{report['raw_observation_count']}`",
        f"- Exact-address observations: `{report['exact_address_observation_count']}`",
        f"- Vague/no-exact-address leads (kept as leads, never branches): `{report['vague_lead_count']}`",
        f"- Unique candidate branches (post-canonicalisation and exact deduplication): `{report['unique_candidate_address_count']}`",
        f"- Excluded for wrong planning area: `{report['excluded_wrong_area_count']}`",
        f"- Deduplicated branches: `{report['branch_count']}`",
        f"- Distinct brands: `{report['brand_count']}`",
        "",
        "## Channel overlap diagnostics (descriptive only — no population estimator)",
        "",
        f"- {diag['S010_count']} canonical branches via S010; {diag['WEB_SEARCH_count']} via WEB_SEARCH",
        f"- Overlap: `{diag['overlap_count']}`; unique to S010: `{diag['unique_to_S010']}`; unique to WEB_SEARCH: `{diag['unique_to_WEB_SEARCH']}`",
        f"- Jaccard overlap: `{diag['jaccard_overlap']:.3f}`",
        f"- {diag['estimator_statement']}",
        "",
        "## Evidence and validation-attempt coverage",
        "",
        f"- Evidence status counts: `{report['evidence_status_counts']}`",
        f"- Branch-specific validation attempted: `{report['validation_attempted_count']}` / `{report['unique_candidate_address_count']}` canonical branches (`{report['validation_attempt_coverage_rate']:.1%}`)",
        f"- Brand-level access diagnostics (not validation coverage): `{report['brand_level_access_diagnostic_count']}`",
        "",
        "## Geocoding and postal coverage",
        "",
        f"- Missing postal code: `{report['missing_postal_count']}` (`{report['missing_postal_rate']:.1%}`)",
        f"- Geocode status counts: `{report['geocode_status_counts']}`",
        "",
        "## Planning-area diagnostics",
        "",
        f"- Discovery-query yield by searched area (diagnostic only): `{report['per_planning_area_discovery_yield']}`",
        f"- Retained physical locations by coordinate-derived planning area: `{report['per_planning_area_location_count']}`",
        "",
        "## Review queue",
        "",
        f"- Open review items: `{report['open_review_queue_count']}`",
        "",
        "## Pilot acceptance gates",
        "",
        f"- All gates met: `{gates['all_gates_met']}`",
        f"- Unmet gates: `{gates['unmet_gates']}`",
        f"- Ready for national-design approval: `{gates['ready_for_national_design_approval']}`",
        "",
        "## Coverage limitations",
        "",
        *[f"- {item}" for item in report["limitations"]],
        "",
        "## Publication boundary",
        "",
        f"- S010 evidence: `{report['publication_boundary']['s010_evidence']}`; public release authorised: `{report['publication_boundary']['public_release_authorized']}`.",
        "- Test execution is external to this production pipeline and is not represented as an acceptance-gate pass here.",
    ]
    return "\n".join(lines) + "\n"


def completion_markdown(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    lines = [
        "# Pilot competitor-discovery completion report",
        "",
        f"Run ID: `{payload['run_id']}`",
        f"Status: `{payload['status']}`",
        f"Ready for national-design approval: `{payload['ready_for_national_design_approval']}`",
        "",
        "**PILOT ONLY — not national coverage, not evidence of completeness, not used to rank locations.**",
        "",
        f"- Planning areas covered: `{counts['planning_area_count']}`",
        f"- Brands: `{counts['brand_count']}`",
        f"- Branches (deduplicated): `{counts['branch_count']}`",
        f"- Branch offerings: `{counts['offering_count']}`",
        f"- Evidence observations: `{counts['evidence_count']}`",
        f"- Evidence status counts: `{counts['evidence_status_counts']}`",
        f"- Review queue rows: `{counts['review_queue_count']}`",
        f"- Geocode status counts: `{counts['geocode_status_counts']}`",
        f"- Secret scan: `{payload['secret_scan']['status']}` with `{payload['secret_scan']['assurance']}` assurance and `{payload['secret_scan']['finding_count']}` finding files.",
    ]
    if payload["unmet_gates"]:
        lines += ["", "## Unmet acceptance gates", "", *[f"- {gate}" for gate in payload["unmet_gates"]]]
    lines += [
        "",
        "No ranking, scoring, financial model, recommendation or dashboard was produced.",
        "",
        "## Exact next task",
        "",
        (
            "Do not treat this pilot as ready for national acquisition until every acceptance gate above is met. "
            "Resolve the open review queue and remaining unresolved/possible branches where feasible, "
            "then decide and freeze the national discovery protocol (query templates, channels, validation-attempt rule) "
            "before any national-scale competitor acquisition begins."
            if payload["unmet_gates"]
            else "Freeze the national discovery protocol (query templates, channels, validation-attempt rule) and proceed to a scoped national design proposal — not acquisition, routing, scoring or financial modelling yet."
        ),
    ]
    return "\n".join(lines) + "\n"
