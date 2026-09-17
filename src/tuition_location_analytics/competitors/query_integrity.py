from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .identity import normalize_address, normalize_brand_name


def expected_query_records(
    pilot_areas: dict[str, Any], discovery_templates: dict[str, Any], run_config: dict[str, Any]
) -> list[dict[str, str]]:
    """Return the frozen 10-area × 2-channel × 2-template protocol.

    The expected records are generated only from independently frozen protocol
    configuration, never inferred from the execution log or observation ledger.
    """
    query_id_template = run_config["query_id_template"]
    expected: list[dict[str, str]] = []
    for area in pilot_areas["selected"]:
        for channel in discovery_templates["channels"]:
            for template in channel["query_templates"]:
                expected.append(
                    {
                        "query_id": query_id_template.format(
                            planning_area_code=run_config.get("query_id_area_code_overrides", {}).get(
                                area["planning_area_code"], area["planning_area_code"]
                            ),
                            channel_id=run_config.get("query_id_channel_codes", {}).get(
                                channel["channel_id"], channel["channel_id"]
                            ),
                            template_code=template["template_code"],
                        ),
                        "planning_area": area["planning_area_name"],
                        "channel": channel["channel_id"],
                        "template": template["template_id"],
                        "query_text": template["query_text_template"].format(
                            planning_area_name=area["planning_area_name"].title()
                        ),
                    }
                )
    return expected


def validate_query_integrity(
    *,
    queries: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    pilot_areas: dict[str, Any],
    discovery_templates: dict[str, Any],
    run_config: dict[str, Any],
) -> dict[str, Any]:
    """Validate the frozen protocol and reconcile every query to its ledger rows.

    `distinct_candidates_surfaced` is the number of observation IDs linked to a
    query. The ledger is one candidate mention per query, and a duplicate
    normalized (brand, address) signature within one query is invalid rather than
    silently de-duplicated for this count.
    """
    expected = expected_query_records(pilot_areas, discovery_templates, run_config)
    expected_by_id = {record["query_id"]: record for record in expected}
    actual_by_id: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for query in queries:
        query_id = query.get("query_id")
        if not isinstance(query_id, str) or not query_id:
            errors.append("query with missing query_id")
            continue
        if query_id in actual_by_id:
            errors.append(f"duplicate query_id: {query_id}")
            continue
        actual_by_id[query_id] = query

    if set(actual_by_id) != set(expected_by_id):
        missing = sorted(set(expected_by_id) - set(actual_by_id))
        unexpected = sorted(set(actual_by_id) - set(expected_by_id))
        if missing:
            errors.append(f"missing expected query IDs: {missing}")
        if unexpected:
            errors.append(f"unexpected query IDs: {unexpected}")

    observations_by_query: dict[str, list[dict[str, Any]]] = defaultdict(list)
    observation_ids: set[str] = set()
    for observation in observations:
        observation_id = observation.get("observation_id")
        if not isinstance(observation_id, str) or not observation_id:
            errors.append("observation with missing observation_id")
        elif observation_id in observation_ids:
            errors.append(f"duplicate observation_id: {observation_id}")
        else:
            observation_ids.add(observation_id)
        query_id = observation.get("query_id")
        if query_id not in expected_by_id:
            errors.append(f"observation links to unknown query_id: {query_id}")
        else:
            observations_by_query[query_id].append(observation)

    reconciliation: list[dict[str, Any]] = []
    for query_id in sorted(expected_by_id):
        expected_record = expected_by_id[query_id]
        actual = actual_by_id.get(query_id)
        linked = observations_by_query.get(query_id, [])
        signatures = [
            (normalize_brand_name(row["brand_name"]), normalize_address(row["address_raw"]))
            for row in linked
        ]
        duplicate_signature_count = sum(count - 1 for count in Counter(signatures).values() if count > 1)
        if duplicate_signature_count:
            errors.append(f"duplicate candidate signature(s) within query: {query_id}")
        record = {
            "query_id": query_id,
            "linked_observation_count": len(linked),
            "duplicate_candidate_signature_count": duplicate_signature_count,
            "reported_distinct_candidates_surfaced": actual.get("distinct_candidates_surfaced") if actual else None,
            "matches_expected_protocol": actual is not None
            and all(actual.get(field) == value for field, value in expected_record.items() if field != "query_id"),
            "count_reconciled": actual is not None
            and actual.get("distinct_candidates_surfaced") == len(linked),
            "zero_result_consistent": actual is not None and actual.get("zero_result") == (len(linked) == 0),
        }
        if not record["matches_expected_protocol"]:
            errors.append(f"protocol fields differ from frozen expectation: {query_id}")
        if not record["count_reconciled"]:
            errors.append(f"distinct_candidates_surfaced mismatch: {query_id}")
        if not record["zero_result_consistent"]:
            errors.append(f"zero_result mismatch: {query_id}")
        reconciliation.append(record)

    return {
        "expected_query_count": len(expected),
        "logged_query_count": len(queries),
        "linked_observation_count": sum(len(rows) for rows in observations_by_query.values()),
        "counting_rule": "one unique observation_id per query after rejecting duplicate normalized (brand, address) candidate signatures",
        "per_query": reconciliation,
        "errors": errors,
        "valid": not errors and len(expected) == 40,
    }
