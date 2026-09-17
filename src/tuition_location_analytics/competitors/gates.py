from __future__ import annotations

import re
from typing import Any

_URL_PATTERN = re.compile(r"^https?://[^\s]+$")
GATE_IDS = [
    "all_queries_logged",
    "query_integrity_reconciled",
    "validation_attempts_complete",
    "urls_valid",
    "no_placeholder_branches",
    "planning_areas_coordinate_derived_or_unresolved",
    "confirmed_branches_have_fresh_operator_evidence",
    "primary_competition_uses_confirmed_current_only",
    "possible_branches_retained_not_silently_confirmed",
    "review_items_enumerated",
    "csv_parquet_parity",
    "checksums_verify",
    "secret_scan_pass",
    "geocoding_executed_or_validated_cache",
    "exact_observation_provenance_partition_complete",
    "resolved_retained_branches_within_pilot_geography",
    "retained_relational_integrity",
]

#: Only these sources prove that geocoding was ready for this exact fixture:
#: a real fresh execution or a cache whose fixture checksum was verified by
#: ``geocode_branches``. Every other value, including null/empty/unknown and
#: any global blocker, fails the separate readiness gate.
_GEOCODING_READY_SOURCES = frozenset({"executed", "cache"})


def _is_valid_url_or_none(value: Any) -> bool:
    return value is None or bool(_URL_PATTERN.match(str(value)))


def evaluate_exact_observation_provenance_partition(
    *,
    expected_observation_ids: set[str],
    retained_branches: list[dict[str, Any]],
    excluded_branches: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check the exact-address observation partition without exposing IDs.

    Every exact discovery observation belongs to exactly one canonical physical
    branch: either retained or excluded. Vague leads are deliberately absent
    from ``expected_observation_ids`` and are not eligible for this partition.
    The returned report contains counts only, never private observation IDs.
    """
    observed_ids: list[str] = []
    invalid_provenance_record_count = 0
    for branch in [*retained_branches, *excluded_branches]:
        encoded = branch.get("source_candidate_ids_json")
        if not isinstance(encoded, str):
            invalid_provenance_record_count += 1
            continue
        try:
            import json

            source_ids = json.loads(encoded)
        except json.JSONDecodeError:
            invalid_provenance_record_count += 1
            continue
        if not isinstance(source_ids, list) or not all(isinstance(value, str) for value in source_ids):
            invalid_provenance_record_count += 1
            continue
        observed_ids.extend(source_ids)

    from collections import Counter

    counts = Counter(observed_ids)
    missing_count = sum(counts.get(value, 0) == 0 for value in expected_observation_ids)
    duplicated_count = sum(count > 1 for count in counts.values() if count)
    unexpected_count = sum(value not in expected_observation_ids for value in counts)
    represented_exactly_once_count = sum(counts.get(value, 0) == 1 for value in expected_observation_ids)
    return {
        "expected_exact_observation_count": len(expected_observation_ids),
        "represented_exactly_once_count": represented_exactly_once_count,
        "missing_count": missing_count,
        "duplicated_count": duplicated_count,
        "unexpected_count": unexpected_count,
        "invalid_provenance_record_count": invalid_provenance_record_count,
        "valid": (
            missing_count == 0
            and duplicated_count == 0
            and unexpected_count == 0
            and invalid_provenance_record_count == 0
        ),
    }


def evaluate_retained_relational_integrity(
    *,
    branch_records: list[dict[str, Any]],
    brand_records: list[dict[str, Any]],
    evidence_records: list[dict[str, Any]],
    offering_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate retained-table foreign keys and orphan brands with safe counts.

    Excluded branches intentionally do not participate: they keep their
    provenance in the separate exclusion output but cannot leak back into the
    analytical branch, evidence, offering or brand tables.
    """
    branch_ids = {str(row.get("branch_id")) for row in branch_records if row.get("branch_id")}
    brand_ids = {str(row.get("brand_id")) for row in brand_records if row.get("brand_id")}
    invalid_branch_brand_count = sum(
        row.get("brand_id") not in brand_ids for row in branch_records
    )
    invalid_evidence_branch_count = sum(
        row.get("branch_id") not in branch_ids for row in evidence_records
    )
    invalid_offering_branch_count = sum(
        row.get("branch_id") not in branch_ids for row in offering_records
    )
    referenced_brand_ids = {row.get("brand_id") for row in branch_records}
    orphan_brand_count = sum(row.get("brand_id") not in referenced_brand_ids for row in brand_records)
    return {
        "retained_branch_count": len(branch_ids),
        "retained_brand_count": len(brand_ids),
        "invalid_branch_brand_count": invalid_branch_brand_count,
        "invalid_evidence_branch_count": invalid_evidence_branch_count,
        "invalid_offering_branch_count": invalid_offering_branch_count,
        "orphan_brand_count": orphan_brand_count,
        "valid": (
            invalid_branch_brand_count == 0
            and invalid_evidence_branch_count == 0
            and invalid_offering_branch_count == 0
            and orphan_brand_count == 0
        ),
    }


def evaluate_pilot_acceptance_gates(
    *,
    total_queries: int,
    logged_queries: int,
    query_integrity: dict[str, Any],
    unique_candidate_count: int,
    attempted_candidate_count: int,
    url_fields: list[Any],
    branch_records: list[dict[str, Any]],
    review_queue: list[dict[str, Any]],
    csv_parquet_parity_ok: bool,
    checksums_ok: bool,
    secret_scan_status: str,
    geocoding_source: str | None,
    exact_observation_provenance_partition: dict[str, Any],
    selected_pilot_areas: set[str],
    retained_relational_integrity: dict[str, Any],
) -> dict[str, Any]:
    invalid_urls = [u for u in url_fields if not _is_valid_url_or_none(u)]
    placeholder_branches = [
        b for b in branch_records
        if not b.get("postal_code") and not b.get("unit") and b.get("address_signature_is_exact") is False
    ]
    unresolved_planning_area_ok = all(
        b.get("planning_area") is None or b.get("planning_area_source") == "coordinate_derived"
        for b in branch_records
    )
    confirmed_without_fresh_evidence = [
        b for b in branch_records
        if b.get("evidence_status") == "confirmed" and not b.get("has_fresh_operator_evidence", False)
    ]
    non_current_marked_current = [
        b for b in branch_records
        if b.get("status") == "current" and b.get("evidence_status") not in {"confirmed", "possible"}
    ]
    possible_marked_confirmed_in_primary = [
        b for b in branch_records
        if b.get("counts_toward_primary_competition") and b.get("evidence_status") != "confirmed"
    ]
    non_confirmed_branches = [b for b in branch_records if b.get("evidence_status") != "confirmed"]
    review_pairs = {
        (item.get("entity_reference"), item.get("issue_category")) for item in review_queue
    }
    missing_status_review = [
        b.get("branch_id", "<missing branch_id>")
        for b in non_confirmed_branches
        if (b.get("branch_id"), f"evidence_status_{b['evidence_status']}") not in review_pairs
    ]
    possible_branches = [b for b in branch_records if b.get("evidence_status") == "possible"]

    def _possible_branch_properly_separated(b: dict[str, Any]) -> bool:
        # status == "current" is legitimate here: current operation can be
        # independently proven while branch-specific subject/level (P1-S4)
        # evidence remains incomplete, which keeps evidence_status "possible"
        # rather than "confirmed". Such a branch must still never count toward
        # primary competition, and it must carry an explicit review/
        # uncertainty disclosure -- it may not be retained silently.
        not_primary = not b.get("counts_toward_primary_competition", False)
        has_review_disclosure = (b.get("branch_id"), "evidence_status_possible") in review_pairs
        return not_primary and has_review_disclosure

    possible_separation_ok = all(_possible_branch_properly_separated(b) for b in possible_branches)
    geocoding_ready = geocoding_source in _GEOCODING_READY_SOURCES
    resolved_retained = [
        b for b in branch_records if b.get("planning_area_source") == "coordinate_derived"
    ]
    resolved_outside_pilot = [
        b for b in resolved_retained if b.get("planning_area") not in selected_pilot_areas
    ]

    results = {
        "all_queries_logged": logged_queries == total_queries == 40,
        "query_integrity_reconciled": bool(query_integrity.get("valid")),
        "validation_attempts_complete": attempted_candidate_count >= unique_candidate_count,
        "urls_valid": len(invalid_urls) == 0,
        "no_placeholder_branches": len(placeholder_branches) == 0,
        "planning_areas_coordinate_derived_or_unresolved": unresolved_planning_area_ok,
        "confirmed_branches_have_fresh_operator_evidence": len(confirmed_without_fresh_evidence) == 0,
        "primary_competition_uses_confirmed_current_only": len(possible_marked_confirmed_in_primary) == 0
        and len(non_current_marked_current) == 0,
        "possible_branches_retained_not_silently_confirmed": possible_separation_ok,
        "review_items_enumerated": len(missing_status_review) == 0,
        "csv_parquet_parity": csv_parquet_parity_ok,
        "checksums_verify": checksums_ok,
        "secret_scan_pass": secret_scan_status in {"pass", "warning"},
        "geocoding_executed_or_validated_cache": geocoding_ready,
        "exact_observation_provenance_partition_complete": bool(
            exact_observation_provenance_partition.get("valid")
        ),
        "resolved_retained_branches_within_pilot_geography": len(resolved_outside_pilot) == 0,
        "retained_relational_integrity": bool(retained_relational_integrity.get("valid")),
    }
    details = {
        "logged_queries": logged_queries,
        "total_queries": total_queries,
        "unique_candidate_count": unique_candidate_count,
        "attempted_candidate_count": attempted_candidate_count,
        "query_integrity_error_count": len(query_integrity.get("errors", [])),
        "invalid_url_count": len(invalid_urls),
        "invalid_urls": invalid_urls,
        "placeholder_branch_count": len(placeholder_branches),
        "confirmed_without_fresh_evidence_count": len(confirmed_without_fresh_evidence),
        "non_current_marked_current_count": len(non_current_marked_current),
        "possible_branch_count": len(possible_branches),
        "possible_branches_with_current_operation_count": sum(
            b.get("status") == "current" for b in possible_branches
        ),
        "possible_branches_failing_separation_count": sum(
            not _possible_branch_properly_separated(b) for b in possible_branches
        ),
        "missing_evidence_status_review_count": len(missing_status_review),
        "geocoding_source": geocoding_source,
        "geocoding_readiness_source_accepted": geocoding_ready,
        "resolved_retained_branch_count": len(resolved_retained),
        "resolved_retained_outside_pilot_geography_count": len(resolved_outside_pilot),
        "retained_relational_integrity": {
            key: retained_relational_integrity.get(key)
            for key in (
                "retained_branch_count",
                "retained_brand_count",
                "invalid_branch_brand_count",
                "invalid_evidence_branch_count",
                "invalid_offering_branch_count",
                "orphan_brand_count",
            )
        },
        "exact_observation_provenance_partition": {
            key: exact_observation_provenance_partition.get(key)
            for key in (
                "expected_exact_observation_count",
                "represented_exactly_once_count",
                "missing_count",
                "duplicated_count",
                "unexpected_count",
                "invalid_provenance_record_count",
            )
        },
    }
    unmet = [gate_id for gate_id in GATE_IDS if not results[gate_id]]
    return {
        "gates": results,
        "details": details,
        "all_gates_met": len(unmet) == 0,
        "unmet_gates": unmet,
        "ready_for_national_design_approval": len(unmet) == 0,
    }
