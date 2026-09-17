from __future__ import annotations

from collections import defaultdict
from typing import Any

from .identity import branch_id as compute_branch_id
from .identity import normalize_address, normalize_brand_name, normalize_building_address, normalize_postal_code, review_id


def _append_identity_review(
    review_queue: list[dict[str, Any]],
    *,
    canonical_brand: str,
    building_key: str,
    category: str,
    description: str,
) -> None:
    review_queue.append(
        {
            "review_item_id": review_id("branch_group", f"{canonical_brand}|{building_key}", category),
            "entity_type": "branch_group",
            "entity_reference": f"{canonical_brand}|{building_key}",
            "issue_category": category,
            "description": description,
            "status": "open",
        }
    )


def _resolve_supported_missing_units(
    records: list[dict[str, Any]], review_queue: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Resolve missing unit fields only with one complete canonical identity.

    The building comparison is fixed-vocabulary lexical normalisation, not fuzzy
    matching. Multiple supported units, postal conflicts, or explicit conflict
    flags remain unresolved and reviewable.
    """
    by_building: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_building[(record["normalized_brand_name"], record["normalized_building_address"])].append(record)

    resolutions: list[dict[str, Any]] = []
    for (canonical_brand, building_key), grouped_records in sorted(by_building.items()):
        missing_unit_records = [record for record in grouped_records if record.get("unit") is None]
        if not missing_unit_records:
            continue
        supporting_identities: dict[tuple[str, str, str], dict[str, Any]] = {}
        for record in grouped_records:
            canonical_address = record.get("canonical_address")
            canonical_postal = normalize_postal_code(record.get("canonical_postal_code"))
            canonical_unit = record.get("canonical_unit")
            if not (canonical_address and canonical_postal and canonical_unit):
                continue
            if normalize_building_address(canonical_address) != building_key:
                continue
            supporting_identities.setdefault(
                (normalize_address(canonical_address), canonical_postal, canonical_unit), record
            )

        if not supporting_identities:
            continue
        explicit_units = {record["unit"] for record in grouped_records if record.get("unit") is not None}
        supported_postals = {identity[1] for identity in supporting_identities}
        known_postals = {record["normalized_postal_code"] for record in grouped_records if record["normalized_postal_code"]}
        has_conflict = any(record.get("identity_conflict") for record in grouped_records)
        can_resolve = (
            len(supporting_identities) == 1
            and len(explicit_units) == 1
            and len(supported_postals) == 1
            and not has_conflict
            and known_postals.issubset(supported_postals)
        )
        if not can_resolve:
            _append_identity_review(
                review_queue,
                canonical_brand=canonical_brand,
                building_key=building_key,
                category="conflicting_identity_evidence" if has_conflict or len(known_postals) > 1 else "ambiguous_missing_unit_identity",
                description=(
                    "Missing-unit observations were not merged because candidate-specific identity evidence "
                    "does not establish one non-conflicting physical branch."
                ),
            )
            continue

        (canonical_address, canonical_postal, canonical_unit), supporting_record = next(iter(supporting_identities.items()))
        for record in missing_unit_records:
            record.update(
                {
                    "address_raw": canonical_address,
                    "normalized_address": normalize_address(canonical_address),
                    "normalized_postal_code": canonical_postal,
                    "unit": canonical_unit,
                    "identity_resolution": "candidate_specific_single_branch_missing_unit",
                }
            )
        resolutions.append(
            {
                "normalized_brand_name": canonical_brand,
                "normalized_building_address": building_key,
                "canonical_postal_code": canonical_postal,
                "canonical_unit": canonical_unit,
                "supporting_candidate_id": supporting_record["candidate_id"],
                "resolved_candidate_ids": sorted(record["candidate_id"] for record in grouped_records),
            }
        )
    return resolutions


def deduplicate_branch_candidates(
    candidates: list[dict[str, Any]],
    *,
    brand_alias_to_canonical: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Group raw discovered branch-candidate records into deduplicated branches.

    Matching is exact on (canonical normalised brand name, postal code, unit)
    after candidate-specific canonical fields are applied. A missing unit may be
    resolved only when exactly one complete candidate-specific canonical identity
    supports the same deterministically normalised building; no fuzzy/similarity
    matching is performed. Known different units or conflicting evidence remain
    separate and are flagged for review.
    """
    alias_map = brand_alias_to_canonical or {}
    enriched_records: list[dict[str, Any]] = []
    for candidate in candidates:
        raw_brand = candidate["brand_name"]
        canonical_brand = alias_map.get(normalize_brand_name(raw_brand), normalize_brand_name(raw_brand))
        canonical_address = candidate.get("canonical_address") or candidate["address_raw"]
        canonical_postal = candidate.get("canonical_postal_code") or candidate.get("postal_code")
        canonical_unit = candidate.get("canonical_unit") or candidate.get("unit")
        postal = normalize_postal_code(canonical_postal)
        enriched = {
            **candidate,
            "normalized_brand_name": canonical_brand,
            "original_address_raw": candidate["address_raw"],
            "address_raw": canonical_address,
            "unit": canonical_unit,
            "normalized_address": normalize_address(canonical_address),
            "normalized_building_address": normalize_building_address(canonical_address),
            "normalized_postal_code": postal,
            "canonical_fields_applied": any(
                candidate.get(field) is not None
                for field in ("canonical_address", "canonical_postal_code", "canonical_unit")
            ),
        }
        enriched_records.append(enriched)
    branches: list[dict[str, Any]] = []
    review_queue: list[dict[str, Any]] = []

    identity_resolutions = _resolve_supported_missing_units(enriched_records, review_queue)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    unresolved_postal: list[dict[str, Any]] = []
    for record in enriched_records:
        postal = record["normalized_postal_code"]
        if postal is None:
            unresolved_postal.append(record)
        else:
            groups[(record["normalized_brand_name"], postal)].append(record)

    for (canonical_brand, postal), records in sorted(groups.items()):
        units = {(record.get("unit") or None) for record in records}
        has_missing_unit = None in units
        has_specific_unit = any(unit is not None for unit in units)
        if has_missing_unit and has_specific_unit and len(units) > 1:
            issue_id = review_id("branch_group", f"{canonical_brand}|{postal}", "ambiguous_unit_within_postal")
            review_queue.append(
                {
                    "review_item_id": issue_id,
                    "entity_type": "branch_group",
                    "entity_reference": f"{canonical_brand}|{postal}",
                    "issue_category": "ambiguous_unit_within_postal",
                    "description": (
                        f"{len(records)} candidate records share brand '{canonical_brand}' and postal "
                        f"code {postal} but disagree on unit ({sorted(u or 'MISSING' for u in units)}); "
                        "not auto-merged or auto-split."
                    ),
                    "status": "open",
                }
            )
        for unit in sorted(units, key=lambda value: value or ""):
            unit_records = [record for record in records if (record.get("unit") or None) == unit]
            representative = unit_records[0]
            new_branch_id = compute_branch_id(canonical_brand, representative["normalized_address"], unit)
            branches.append(
                {
                    "branch_id": new_branch_id,
                    "brand_name": representative["brand_name"],
                    "normalized_brand_name": canonical_brand,
                    "address_raw": representative["address_raw"],
                    "normalized_address": representative["normalized_address"],
                    "postal_code": postal,
                    "unit": unit,
                    "source_candidate_count": len(unit_records),
                    "source_candidate_ids": [record.get("candidate_id") for record in unit_records],
                }
            )

    unresolved_groups: dict[tuple[str, str, str | None], list[dict[str, Any]]] = defaultdict(list)
    for record in unresolved_postal:
        unresolved_groups[(record["normalized_brand_name"], record["normalized_address"], record.get("unit") or None)].append(record)

    for (canonical_brand, normalized_address, unit), records in sorted(unresolved_groups.items()):
        representative = records[0]
        issue_id = review_id(
            "branch_candidate", f"{canonical_brand}|{normalized_address}|{unit or ''}", "missing_or_invalid_postal_code"
        )
        review_queue.append(
            {
                "review_item_id": issue_id,
                "entity_type": "branch_candidate",
                "entity_reference": representative.get("candidate_id", representative["address_raw"]),
                "issue_category": "missing_or_invalid_postal_code",
                "description": (
                    f"Candidate '{representative['brand_name']}' at '{representative['address_raw']}' has no valid "
                    f"6-digit postal code; not deduplicated by postal or geocoded. {len(records)} identical-text "
                    "observation(s) of this brand/address/unit signature were merged by exact normalized-text match only."
                ),
                "status": "open",
            }
        )
        new_branch_id = compute_branch_id(canonical_brand, normalized_address, unit)
        branches.append(
            {
                "branch_id": new_branch_id,
                "brand_name": representative["brand_name"],
                "normalized_brand_name": canonical_brand,
                "address_raw": representative["address_raw"],
                "normalized_address": normalized_address,
                "postal_code": None,
                "unit": unit,
                "source_candidate_count": len(records),
                "source_candidate_ids": [record.get("candidate_id") for record in records],
            }
        )

    return {
        "branches": sorted(branches, key=lambda row: row["branch_id"]),
        "review_queue": review_queue,
        "quality": {
            "input_candidate_count": len(candidates),
            "deduplicated_branch_count": len(branches),
            "review_queue_count": len(review_queue),
            "missing_postal_count": len(unresolved_postal),
            "candidate_specific_missing_unit_resolution_count": len(identity_resolutions),
            "candidate_specific_missing_unit_resolutions": identity_resolutions,
        },
    }
