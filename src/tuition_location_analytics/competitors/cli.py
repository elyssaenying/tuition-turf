from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import pyarrow as pa

from tuition_location_analytics.foundation.common import (
    file_record,
    scan_foundation_outputs_for_secrets,
    sha256_file,
    write_csv,
    write_json,
    write_parquet,
)
from tuition_location_analytics.preflight.common import read_env

from .dedup import deduplicate_branch_candidates
from .diagnostics import channel_overlap_diagnostics
from .gates import (
    evaluate_exact_observation_provenance_partition,
    evaluate_pilot_acceptance_gates,
    evaluate_retained_relational_integrity,
)
from .geocode import OneMapUnavailable, geocode_branches
from .geography import load_planning_area_polygons, planning_area_for_coordinate
from .identity import (
    brand_id as compute_brand_id,
    evidence_id as compute_evidence_id,
    normalize_address,
    normalize_brand_name,
    offering_id as compute_offering_id,
    review_id as compute_review_id,
)
from .reporting import completion_markdown, coverage_markdown
from .query_integrity import validate_query_integrity

SINGAPORE_BOUNDS = {
    "minimum_longitude": 103.5,
    "maximum_longitude": 104.2,
    "minimum_latitude": 1.1,
    "maximum_latitude": 1.6,
}
VAGUE_LEAD_MARKERS = ("discovery lead only",)
CONFIRMED_ATTEMPT_STATUS = "confirmed_operator_controlled"


def _config_paths(repo_root: Path) -> dict[str, Path]:
    run_config_path = repo_root / "config/competitors/pilot_run.json"
    run_config = json.loads(run_config_path.read_text(encoding="utf-8"))
    raw_ledger_ref = run_config["raw_observation_ledger_ref"]
    raw_ledger_path = repo_root / raw_ledger_ref
    if not raw_ledger_path.exists():
        raise RuntimeError(f"private raw-observation ledger is unavailable: {raw_ledger_ref}")
    validation_ledger_ref = run_config["validation_attempt_ledger_ref"]
    validation_ledger_path = repo_root / validation_ledger_ref
    if not validation_ledger_path.exists():
        raise RuntimeError(f"private validation-attempt ledger is unavailable: {validation_ledger_ref}")
    return {
        "run_config": run_config_path,
        "pilot_planning_areas": repo_root / "config/competitors/pilot_planning_areas.json",
        "raw_observations": raw_ledger_path,
        "query_log": repo_root / "config/competitors/pilot_query_log.json",
        "validation_attempts": validation_ledger_path,
        "inclusion_rules": repo_root / "config/competitors/inclusion_rules.json",
        "sources": repo_root / "config/competitors/sources.json",
        "discovery_templates": repo_root / "config/competitors/discovery_templates.json",
    }


def _is_vague_lead(observation: dict[str, Any]) -> bool:
    note = (observation.get("note") or "").lower()
    return any(marker in note for marker in VAGUE_LEAD_MARKERS)


def _load_validation_index(
    attempts: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """Build an explicit, auditable join from raw observation_id to its validation
    attempt. This is never a free-text address match: the raw-observation and
    validation-attempt ledgers were authored independently, and their address_raw
    strings are not always byte-identical even where they denote the same physical
    branch (differing abbreviations, unit presence, parenthetical annotations).
    AGGREGATE_ALL_ADDRESSES rows are brand-level access diagnostics. They are
    deliberately never joined to a candidate or branch.
    """
    by_observation_id: dict[str, dict[str, Any]] = {}
    aggregate_by_brand: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in attempts:
        if row["address_key"] == "AGGREGATE_ALL_ADDRESSES":
            aggregate_by_brand[normalize_brand_name(row["brand_name"])].append(row)
            continue
        for observation_id in row.get("source_observation_ids", []):
            if observation_id in by_observation_id:
                raise RuntimeError(f"observation_id is linked to multiple validation attempts: {observation_id}")
            by_observation_id[observation_id] = row
    return by_observation_id, aggregate_by_brand


def _lookup_validation_for_branch(
    branch: dict[str, Any],
    by_observation_id: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    validations = _validations_for_branch(branch, by_observation_id)
    return validations[0] if validations else None


def _validations_for_branch(
    branch: dict[str, Any],
    by_observation_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return every distinct candidate-specific validation linked to a branch.

    Identity resolution may merge observations that were validated in different
    batches. Coverage remains one credit per physical branch, while every linked
    validation remains available for output provenance.
    """
    validations: list[dict[str, Any]] = []
    seen: set[int] = set()
    for observation_id in branch["source_candidate_ids"]:
        validation = by_observation_id.get(observation_id)
        if validation is not None and id(validation) not in seen:
            validations.append(validation)
            seen.add(id(validation))
    return validations


def _blocked_geocoding_result(error: OneMapUnavailable, geocode_input: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a safe blocked-geocoding result for a global OneMap access failure.

    Never a credential, token, request-body or response-body value: only
    ``error.category`` (one of OneMapUnavailable's fixed safe categories) and
    the safe exception message. A branch with no postal code was never going
    to be attempted and keeps its accurate ``missing_postal_code`` status;
    only a branch that needed a lookup receives the blocked_* status.
    """
    blocked_status = "blocked_" + error.category
    return {
        "records": [
            {
                "branch_id": row["branch_id"],
                "status": "missing_postal_code" if not row["postal_code"] else blocked_status,
                "exact_postal_candidate_count": None,
                "unique_coordinate_count": None,
                "longitude_wgs84": None,
                "latitude_wgs84": None,
            }
            for row in geocode_input
        ],
        "summary": {
            "purpose": "Exact-postal coordinate resolution for competitor branches",
            "limitation": str(error),
            "blocked_category": error.category,
            "token_persisted": False,
            "raw_authentication_response_recorded": False,
            "raw_search_responses_recorded": False,
        },
        "source": "blocked",
    }


def _canonical_fields_for_observation(validation: dict[str, Any] | None) -> dict[str, Any]:
    if validation is None:
        return {}
    canonical = validation.get("canonical_branch")
    if not isinstance(canonical, dict):
        return {}
    return {
        "canonical_address": canonical.get("address"),
        "canonical_postal_code": canonical.get("postal_code"),
        "canonical_unit": canonical.get("unit"),
    }


def _excluded_wrong_area_record(
    branch: dict[str, Any], validations: list[dict[str, Any]], *, reason: str | None = None
) -> dict[str, Any]:
    """Retain canonical branch and validation provenance for an exclusion.

    The JSON fields are deterministic, machine-readable copies for CSV and
    Parquet inspection within the ignored private output boundary. They retain
    identifiers only, never private page text or raw authentication material.
    """
    source_ids = sorted(branch["source_candidate_ids"])
    validation_source_ids = sorted(
        {
            observation_id
            for validation in validations
            for observation_id in validation.get("source_observation_ids", [])
            if observation_id in branch["source_candidate_ids"]
        }
    )
    return {
        "branch_id": branch["branch_id"],
        "brand_name": branch["brand_name"],
        "address_raw": branch["address_raw"],
        "source_candidate_ids_json": json.dumps(source_ids),
        "validation_attempt_count": len(validations),
        "validation_attempt_source_observation_ids_json": json.dumps(validation_source_ids),
        "reason": reason or (validations[0] if validations else {}).get("failure_reason"),
    }


def _apply_coordinate_geography_policy(
    *,
    branches: list[dict[str, Any]],
    geocode_by_branch: dict[str, dict[str, Any]],
    polygons: Any,
    selected_pilot_areas: set[str],
    validation_index: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Retain only coordinate-resolved branches inside the frozen pilot set.

    Query area is a discovery diagnostic only. It never overrides a resolved
    coordinate-derived planning area; an inside-set mismatch is retained with a
    review item, while an outside-set result is a provenance-preserving
    exclusion. No coordinate means no area is inferred.
    """
    retained: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    for branch in branches:
        geocode = geocode_by_branch.get(branch["branch_id"], {})
        branch["geocode_status"] = geocode.get("status")
        branch["longitude_wgs84"] = geocode.get("longitude_wgs84")
        branch["latitude_wgs84"] = geocode.get("latitude_wgs84")
        resolved_area = planning_area_for_coordinate(
            geocode.get("longitude_wgs84"), geocode.get("latitude_wgs84"), polygons
        )
        if resolved_area is None:
            branch["planning_area"] = None
            branch["planning_area_source"] = "unresolved_no_coordinate"
            reviews.append(
                {
                    "review_item_id": compute_review_id("branch", branch["branch_id"], "planning_area_unresolved"),
                    "entity_type": "branch",
                    "entity_reference": branch["branch_id"],
                    "issue_category": "planning_area_unresolved",
                    "description": f"No verified coordinate available to derive a planning area; searched under {branch['planning_area_searched']} but not assigned there without coordinate confirmation.",
                    "status": "open",
                }
            )
            retained.append(branch)
            continue

        branch["planning_area"] = resolved_area
        branch["planning_area_source"] = "coordinate_derived"
        if resolved_area not in selected_pilot_areas:
            excluded.append(
                _excluded_wrong_area_record(
                    branch,
                    _validations_for_branch(branch, validation_index),
                    reason="coordinate_derived_outside_pilot_geography",
                )
            )
            continue
        if branch["planning_area_searched"] != resolved_area:
            reviews.append(
                {
                    "review_item_id": compute_review_id(
                        "branch", branch["branch_id"], "planning_area_searched_derived_mismatch"
                    ),
                    "entity_type": "branch",
                    "entity_reference": branch["branch_id"],
                    "issue_category": "planning_area_searched_derived_mismatch",
                    "description": "The coordinate-derived planning area differs from the discovery-query area; retained because the coordinate-derived area remains inside the frozen pilot geography.",
                    "status": "open",
                }
            )
        retained.append(branch)
    return retained, excluded, reviews


def _retained_branch_records_only(
    records: list[dict[str, Any]], retained_branch_ids: set[str]
) -> list[dict[str, Any]]:
    """Keep a branch-keyed analytical table within the final retained set."""
    return [row for row in records if row.get("branch_id") in retained_branch_ids]


def compute_run_id(
    *,
    material_input_checksums: list[str],
    analysis_cutoff: str,
    geocode_decisions: list[dict[str, Any]],
    geocode_cache_checksum: str | None,
) -> str:
    """Hash all material inputs plus complete geocode decisions, including coordinates."""
    digest_source = "|".join(material_input_checksums) + f"|cutoff={analysis_cutoff}"
    digest_source += "|geocode_decisions=" + json.dumps(
        geocode_decisions, sort_keys=True, separators=(",", ":")
    )
    digest_source += f"|geocode_cache_checksum={geocode_cache_checksum or 'none'}"
    return "competitors_pilot_" + hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:16]


def _prepare_run_output_directories(
    repo_root: Path,
    *,
    reportable_output_root: str,
    analysis_cutoff: str,
    run_id: str,
) -> tuple[Path, Path]:
    """Create immutable, run-ID-keyed private output directories.

    A prior run's directory is never reused or overwritten. Both destinations
    are checked before either is created so an existing processed or report
    directory always stops the run before output writing begins.
    """
    processed_dir = repo_root / "data/processed/competitors" / f"pilot-{analysis_cutoff}" / run_id
    report_dir = repo_root / reportable_output_root / f"pilot-{analysis_cutoff}" / run_id
    existing = [path for path in (processed_dir, report_dir) if path.exists()]
    if existing:
        joined = ", ".join(str(path.relative_to(repo_root)) for path in existing)
        raise RuntimeError(f"refusing to overwrite existing competitor run output directory: {joined}")
    processed_dir.mkdir(parents=True, exist_ok=False)
    report_dir.mkdir(parents=True, exist_ok=False)
    return processed_dir, report_dir


def _evidence_status_from_validation(validation: dict[str, Any] | None) -> str:
    if validation is None:
        return "unresolved"
    address_ok = validation["address_validation_status"] == CONFIRMED_ATTEMPT_STATUS
    math_ok = "confirmed" in validation["mathematics_validation_status"]
    level_ok = (
        "confirmed" in validation["p1_s4_level_validation_status"]
        and "not_mapped" not in validation["p1_s4_level_validation_status"]
    )
    if address_ok and math_ok and level_ok:
        return "confirmed"
    if any(
        status.startswith("attempted_") or "possible" in status
        for status in (
            validation["address_validation_status"],
            validation["mathematics_validation_status"],
            validation["p1_s4_level_validation_status"],
        )
    ):
        return "possible"
    return "unresolved"


def run(repo_root: Path, *, credential_values: Iterable[str] | None = None) -> dict[str, Any]:
    paths = _config_paths(repo_root)
    run_config = json.loads(paths["run_config"].read_text(encoding="utf-8"))
    analysis_cutoff = run_config["analysis_cutoff"]
    pilot_areas = json.loads(paths["pilot_planning_areas"].read_text(encoding="utf-8"))
    raw = json.loads(paths["raw_observations"].read_text(encoding="utf-8"))
    query_log = json.loads(paths["query_log"].read_text(encoding="utf-8"))
    validations_config = json.loads(paths["validation_attempts"].read_text(encoding="utf-8"))
    by_observation_id, aggregate_by_brand = _load_validation_index(validations_config["attempts"])

    if credential_values is None:
        credential_values = read_env(repo_root / ".env").values()
    credential_values = tuple(credential_values)

    observations = raw["observations"]
    queries = query_log["queries"]
    discovery_templates = json.loads(paths["discovery_templates"].read_text(encoding="utf-8"))
    query_integrity = validate_query_integrity(
        queries=queries,
        observations=observations,
        pilot_areas=pilot_areas,
        discovery_templates=discovery_templates,
        run_config=run_config,
    )
    if not query_integrity["valid"]:
        raise RuntimeError(f"query-integrity gate failed: {query_integrity['errors']}")

    # --- Step 1: split observations into exact-address leads vs vague leads ---
    exact_observations = [o for o in observations if not _is_vague_lead(o)]
    vague_leads = [o for o in observations if _is_vague_lead(o)]
    obs_by_id = {o["observation_id"]: o for o in exact_observations}

    # --- Step 2: exact-match dedup (brand, postal, unit) via the tested dedup module ---
    dedup_input = []
    for o in exact_observations:
        validation = by_observation_id.get(o["observation_id"])
        dedup_input.append({
            "candidate_id": o["observation_id"],
            "brand_name": o["brand_name"],
            "address_raw": o["address_raw"],
            "postal_code": o.get("postal_code_hint"),
            "unit": o.get("unit_hint"),
            **_canonical_fields_for_observation(validation),
        })
    dedup_result = deduplicate_branch_candidates(dedup_input)
    unique_candidate_count = len(dedup_result["branches"])
    review_queue: list[dict[str, Any]] = list(dedup_result["review_queue"])

    # --- Step 3: attach brand identity, discovery provenance and evidence status ---
    brands: dict[str, dict[str, Any]] = {}
    evidence_rows: list[dict[str, Any]] = []
    excluded_wrong_area: list[dict[str, Any]] = []
    branches: list[dict[str, Any]] = []
    validation_attempted_count = 0

    for branch in dedup_result["branches"]:
        bid = compute_brand_id(branch["normalized_brand_name"])
        branch["brand_id"] = bid

        source_observations = [obs_by_id[cid] for cid in branch["source_candidate_ids"] if cid in obs_by_id]
        channels_observed = sorted({o["channel"] for o in source_observations})
        queries_observed = sorted({o["query_id"] for o in source_observations})
        branch["planning_area_searched"] = source_observations[0]["planning_area_searched"] if source_observations else None

        validations = _validations_for_branch(branch, by_observation_id)
        validation = validations[0] if validations else None
        if validations:
            validation_attempted_count += 1
        evidence_status = _evidence_status_from_validation(validation)
        if validation is None and "S010" in channels_observed:
            # A directory observation is sufficient for possible at most. A
            # brand-level access diagnostic is deliberately not a validation.
            evidence_status = "possible"
        brand_access_diagnostics = aggregate_by_brand.get(branch["normalized_brand_name"], [])

        if validation is not None and "wrong_planning_area" in validation["address_validation_status"]:
            excluded_wrong_area.append(_excluded_wrong_area_record(branch, validations))
            continue

        for observation in source_observations:
            evidence_rows.append(
                {
                    "evidence_id": compute_evidence_id(
                        branch["branch_id"], observation["observation_id"], observation["observed_at"], "discovery_observation"
                    ),
                    "branch_id": branch["branch_id"],
                    "observation_id": observation["observation_id"],
                    "query_id": observation["query_id"],
                    "channel": observation["channel"],
                    "evidence_scope": "directory" if observation["channel"] == "S010" else "search_snippet",
                    "discovery_source_url": observation.get("discovery_source_url"),
                    "observed_at": observation["observed_at"],
                }
            )
        for validation_index, validation_provenance in enumerate(validations, start=1):
            linked_ids = sorted(
                set(branch["source_candidate_ids"]) & set(validation_provenance.get("source_observation_ids", []))
            )
            provenance_ref = linked_ids[0] if linked_ids else f"validation_attempt_{validation_index}"
            evidence_rows.append(
                {
                    "evidence_id": compute_evidence_id(
                        branch["branch_id"], provenance_ref, validation_provenance["observed_at"], "operator_validation"
                    ),
                    "branch_id": branch["branch_id"],
                    "observation_id": provenance_ref if linked_ids else None,
                    "query_id": None,
                    "channel": "OPERATOR_VALIDATION_ATTEMPT",
                    "evidence_scope": "operator_controlled" if evidence_status == "confirmed" else "attempted",
                    "discovery_source_url": validation_provenance.get("operator_controlled_url"),
                    "observed_at": validation_provenance["observed_at"],
                }
            )

        has_fresh_operator_evidence = evidence_status == "confirmed"
        likely_current_unconfirmed = evidence_status == "possible"
        current_op_status = validation["current_operating_status_validation"] if validation else "unresolved"
        status_value = "current" if current_op_status == CONFIRMED_ATTEMPT_STATUS else "unresolved"

        branch.update(
            {
                "planning_area": None,
                "planning_area_source": "pending_geocode",
                "evidence_status": evidence_status,
                "status": status_value,
                "likely_current_unconfirmed": likely_current_unconfirmed,
                "has_fresh_operator_evidence": has_fresh_operator_evidence,
                "address_signature_is_exact": True,
                "counts_toward_primary_competition": evidence_status == "confirmed" and status_value == "current",
                "operator_controlled_url": validation.get("operator_controlled_url") if validation else None,
                "validation_failure_reason": validation.get("failure_reason") if validation else "no validation attempt recorded",
                "has_branch_specific_validation_attempt": validation is not None,
                "validation_attempt_count": len(validations),
                "validation_attempt_source_observation_ids_json": json.dumps(
                    sorted(
                        {
                            observation_id
                            for validation_provenance in validations
                            for observation_id in validation_provenance.get("source_observation_ids", [])
                            if observation_id in branch["source_candidate_ids"]
                        }
                    )
                ),
                "source_candidate_ids_json": json.dumps(sorted(branch["source_candidate_ids"])),
                "brand_level_access_diagnostic_count": len(brand_access_diagnostics),
                "brand_level_access_diagnostic_statuses_json": json.dumps(
                    sorted({row["address_validation_status"] for row in brand_access_diagnostics})
                ),
                "discovery_channels_json": json.dumps(channels_observed),
                "discovery_query_ids_json": json.dumps(queries_observed),
            }
        )
        branches.append(branch)
        if evidence_status != "confirmed":
            review_queue.append(
                {
                    "review_item_id": compute_review_id("branch", branch["branch_id"], f"evidence_status_{evidence_status}"),
                    "entity_type": "branch",
                    "entity_reference": branch["branch_id"],
                    "issue_category": f"evidence_status_{evidence_status}",
                    "description": (validation or {}).get("failure_reason") or "No operator-controlled validation attempt recorded for this branch.",
                    "status": "open",
                }
            )

    # --- Step 4: address ambiguity review (same address, different brand claims) ---
    address_to_brands: dict[str, set[str]] = defaultdict(set)
    for observation in exact_observations:
        address_to_brands[normalize_address(observation["address_raw"])].add(normalize_brand_name(observation["brand_name"]))
    for address, brand_set in address_to_brands.items():
        if len(brand_set) > 1:
            review_queue.append(
                {
                    "review_item_id": compute_review_id("address", address, "ambiguous_brand_at_address"),
                    "entity_type": "address",
                    "entity_reference": address,
                    "issue_category": "ambiguous_brand_at_address",
                    "description": f"Discovery observations attribute this address to multiple brands: {sorted(brand_set)}; not auto-merged or auto-split.",
                    "status": "open",
                }
            )

    # --- Step 5: vague/no-address leads go to a separate table, never branches ---
    candidate_leads_table = [
        {
            "observation_id": o["observation_id"],
            "brand_name": o["brand_name"],
            "planning_area_searched": o["planning_area_searched"],
            "address_as_stated": o["address_raw"],
            "channel": o["channel"],
            "query_id": o["query_id"],
            "discovery_source_url": o.get("discovery_source_url"),
            "reason_not_a_branch_record": o.get("note"),
        }
        for o in vague_leads
    ]
    for lead in candidate_leads_table:
        review_queue.append(
            {
                "review_item_id": compute_review_id("lead", lead["observation_id"], "no_exact_address"),
                "entity_type": "candidate_lead",
                "entity_reference": lead["observation_id"],
                "issue_category": "no_exact_address",
                "description": f"{lead['brand_name']}: {lead['reason_not_a_branch_record']}",
                "status": "open",
            }
        )

    # --- Step 6: geocode branches with a postal code ---
    interim_dir = repo_root / "data/interim/competitors"
    interim_dir.mkdir(parents=True, exist_ok=True)
    geocode_input = [{"branch_id": b["branch_id"], "postal_code": b["postal_code"]} for b in branches]
    try:
        geocoding = geocode_branches(
            repo_root, geocode_input, pace_seconds=0.5, singapore_bounds=SINGAPORE_BOUNDS, cache_dir=interim_dir
        )
    except OneMapUnavailable as error:
        geocoding = _blocked_geocoding_result(error, geocode_input)
    geocode_by_branch = {row["branch_id"]: row for row in geocoding["records"]}

    # --- Step 7: planning area strictly from geocoded coordinates ---
    polygons = load_planning_area_polygons(repo_root / "data/processed/foundation/2026-09-12/mp2019_subzones.parquet")
    selected_pilot_areas = {
        row["planning_area_name"] for row in pilot_areas["selected"]
    }
    retained_after_geography, coordinate_exclusions, geography_reviews = _apply_coordinate_geography_policy(
        branches=branches,
        geocode_by_branch=geocode_by_branch,
        polygons=polygons,
        selected_pilot_areas=selected_pilot_areas,
        validation_index=by_observation_id,
    )
    excluded_wrong_area.extend(coordinate_exclusions)
    review_queue.extend(geography_reviews)
    coordinate_excluded_branch_ids = {row["branch_id"] for row in coordinate_exclusions}

    # Excluded branches preserve their separate provenance record but cannot
    # participate in retained analytical tables or their review disclosures.
    branches = retained_after_geography
    if coordinate_excluded_branch_ids:
        evidence_rows = _retained_branch_records_only(
            evidence_rows, {branch["branch_id"] for branch in branches}
        )
        review_queue = [
            item
            for item in review_queue
            if not (
                item.get("entity_type") == "branch"
                and item.get("entity_reference") in coordinate_excluded_branch_ids
            )
        ]

    # Brands are an analytical retained-branch entity, never a catalogue of
    # every discovered or excluded name. Reconstruct only after geography
    # exclusion so no orphan brand can enter the retained outputs.
    brands = {
        branch["brand_id"]: {
            "brand_id": branch["brand_id"],
            "brand_name": branch["brand_name"],
            "normalized_brand_name": branch["normalized_brand_name"],
        }
        for branch in branches
    }

    # --- Step 8: offerings only for confirmed/possible branches (never excluded/unresolved) ---
    offerings: list[dict[str, Any]] = []
    for branch in branches:
        if branch["evidence_status"] not in {"confirmed", "possible"}:
            continue
        validation = _lookup_validation_for_branch(branch, by_observation_id)
        levels = (validation or {}).get("levels_confirmed") or []
        for level in levels or ["unspecified"]:
            offerings.append(
                {
                    "offering_id": compute_offering_id(branch["branch_id"], "mathematics", level),
                    "branch_id": branch["branch_id"],
                    "subject": "mathematics",
                    "level": level,
                    "evidence_status": branch["evidence_status"],
                }
            )

    # --- Step 9: coverage diagnostics (no capture-recapture estimator) ---
    channel_branch_ids: dict[str, set[str]] = {"S010": set(), "WEB_SEARCH": set()}
    for branch in branches:
        for observation_id in branch["source_candidate_ids"]:
            observation = obs_by_id.get(observation_id)
            if observation and observation["channel"] in channel_branch_ids:
                channel_branch_ids[observation["channel"]].add(branch["branch_id"])
    overlap_diag = channel_overlap_diagnostics(
        channel_branch_ids["S010"], channel_branch_ids["WEB_SEARCH"], label_a="S010", label_b="WEB_SEARCH"
    )
    overlap_diag["unit_of_comparison"] = "canonical branch_id after candidate-specific canonicalisation and deduplication"

    # Discovery yield is deliberately query-area based. Actual location counts
    # use only coordinate-derived planning areas of retained branches.
    per_area_discovery_yield: dict[str, int] = Counter(
        b["planning_area_searched"] for b in dedup_result["branches"]
    )
    per_area_location_count: dict[str, int] = Counter(
        b["planning_area"]
        for b in branches
        if b["planning_area_source"] == "coordinate_derived" and b["planning_area"] is not None
    )

    evidence_status_counts = dict(sorted(Counter(b["evidence_status"] for b in branches).items()))
    geocode_status_counts = dict(sorted(Counter(b["geocode_status"] for b in branches).items()))
    missing_postal_count = sum(1 for b in branches if not b["postal_code"])

    # --- Step 10: run identity from checksums of every material input ---
    material_inputs = [
        paths["run_config"],
        paths["pilot_planning_areas"],
        paths["raw_observations"],
        paths["query_log"],
        paths["validation_attempts"],
        paths["inclusion_rules"],
        paths["sources"],
        paths["discovery_templates"],
    ]
    geocode_cache_checksum = geocoding.get("cache_checksum")
    run_id = compute_run_id(
        material_input_checksums=[sha256_file(path) for path in material_inputs],
        analysis_cutoff=analysis_cutoff,
        geocode_decisions=geocoding["records"],
        geocode_cache_checksum=geocode_cache_checksum,
    )

    processed_dir, report_dir = _prepare_run_output_directories(
        repo_root,
        reportable_output_root=run_config["publication_boundary"]["reportable_output_root"],
        analysis_cutoff=analysis_cutoff,
        run_id=run_id,
    )

    exact_observation_provenance_partition = evaluate_exact_observation_provenance_partition(
        expected_observation_ids={row["observation_id"] for row in exact_observations},
        retained_branches=branches,
        excluded_branches=excluded_wrong_area,
    )
    retained_relational_integrity = evaluate_retained_relational_integrity(
        branch_records=branches,
        brand_records=list(brands.values()),
        evidence_records=evidence_rows,
        offering_records=offerings,
    )

    output_specs = [
        ("brands", list(brands.values())),
        ("branches", branches),
        ("branch_offerings", offerings),
        ("evidence_observations", evidence_rows),
        ("discovery_queries", queries),
        ("geocode_decisions", geocoding["records"]),
        ("aliases", []),
        ("relocations_status_history", []),
        ("review_queue", review_queue),
        ("candidate_leads_unresolved", candidate_leads_table),
        ("excluded_wrong_area", excluded_wrong_area),
    ]
    outputs: list[tuple[Path, int]] = []
    for name, records in output_specs:
        csv_path = processed_dir / f"{name}.csv"
        parquet_path = processed_dir / f"{name}.parquet"
        if records:
            write_csv(csv_path, records)
            overrides = {"longitude_wgs84": pa.float64(), "latitude_wgs84": pa.float64()}
            type_overrides = {k: v for k, v in overrides.items() if k in records[0]}
            write_parquet(parquet_path, records, type_overrides=type_overrides or None)
            outputs.append((csv_path, len(records)))
            outputs.append((parquet_path, len(records)))
        else:
            empty_path = processed_dir / f"{name}.empty.json"
            write_json(empty_path, {"note": f"no {name} rows in this pilot"})
            outputs.append((empty_path, 0))

    # --- Step 11: URL validity check across every *_url field ---
    url_fields: list[Any] = []
    for branch in branches:
        url_fields.append(branch.get("operator_controlled_url"))
    for observation in exact_observations:
        url_fields.append(observation.get("discovery_source_url"))
    for row in validations_config["attempts"]:
        url_fields.append(row.get("operator_controlled_url"))

    # --- Step 12: CSV/Parquet parity check (row counts) ---
    import csv as csv_module

    import pyarrow.parquet as pq

    parity_ok = True
    for name, records in output_specs:
        if not records:
            continue
        csv_rows = sum(1 for _ in csv_module.reader(open(processed_dir / f"{name}.csv"))) - 1
        parquet_rows = pq.read_table(processed_dir / f"{name}.parquet").num_rows
        if csv_rows != parquet_rows or csv_rows != len(records):
            parity_ok = False

    processed_file_records = [file_record(path, repo_root, count) for path, count in outputs]
    checksums_ok = all(
        record["sha256"] == sha256_file(repo_root / record["path"])
        for record in processed_file_records
    )
    gate_kwargs = dict(
        total_queries=40,
        logged_queries=len(queries),
        query_integrity=query_integrity,
        unique_candidate_count=unique_candidate_count,
        attempted_candidate_count=validation_attempted_count,
        url_fields=url_fields,
        branch_records=branches,
        review_queue=review_queue,
        csv_parquet_parity_ok=parity_ok,
        checksums_ok=checksums_ok,
        geocoding_source=geocoding.get("source", "executed"),
        exact_observation_provenance_partition=exact_observation_provenance_partition,
        selected_pilot_areas=selected_pilot_areas,
        retained_relational_integrity=retained_relational_integrity,
    )
    gate_result = evaluate_pilot_acceptance_gates(secret_scan_status="pending", **gate_kwargs)

    coverage_report = {
        "run_id": run_id,
        "status": "pilot",
        "analysis_cutoff": analysis_cutoff,
        "protocol_completion": f"{len(queries)}/40 frozen queries logged",
        "raw_observation_count": len(observations),
        "exact_address_observation_count": len(exact_observations),
        "vague_lead_count": len(vague_leads),
        "unique_candidate_address_count": unique_candidate_count,
        "excluded_wrong_area_count": len(excluded_wrong_area),
        "branch_count": len(branches),
        "brand_count": len(brands),
        "evidence_status_counts": evidence_status_counts,
        "validation_attempted_count": validation_attempted_count,
        "validation_attempt_coverage_rate": validation_attempted_count / unique_candidate_count if unique_candidate_count else 0.0,
        "geocode_status_counts": geocode_status_counts,
        "missing_postal_count": missing_postal_count,
        "missing_postal_rate": missing_postal_count / len(branches) if branches else 0.0,
        "per_planning_area_discovery_yield": dict(
            sorted((k, v) for k, v in per_area_discovery_yield.items() if k is not None)
        ),
        "per_planning_area_location_count": dict(
            sorted((k, v) for k, v in per_area_location_count.items() if k is not None)
        ),
        "channel_diagnostics": overlap_diag,
        "query_integrity": query_integrity,
        "exact_observation_provenance_partition": exact_observation_provenance_partition,
        "retained_relational_integrity": retained_relational_integrity,
        "brand_level_access_diagnostic_count": sum(len(rows) for rows in aggregate_by_brand.values()),
        "publication_boundary": run_config["publication_boundary"],
        "production_pipeline_test_execution": "not_run_by_pipeline",
        "open_review_queue_count": sum(1 for r in review_queue if r["status"] == "open"),
        "acceptance_gates": gate_result,
        "limitations": [
            "Pilot covers 10 of 55 planning areas only; not national coverage.",
            f"Validation-attempt coverage is {validation_attempted_count}/{unique_candidate_count} unique candidates; see acceptance_gates for whether this meets the 100% gate.",
            "Kumon's own mathematics programme is not natively expressed in P1-S4 school-level terms; its level element is left unmet, not assumed.",
            "Mandai returned zero candidates on all four of its queries; reported as a genuine finding.",
            "A branch is marked 'current' only when current-operating-status validation succeeded; all others are 'unresolved' with likely_current_unconfirmed disclosed separately where applicable.",
            f"Deduplication uses candidate-specific validated canonical address/postal/unit fields where recorded, then exact (brand, postal code, unit); {missing_postal_count} of {len(branches)} branches have no postal code and are each kept as a separate, flagged branch rather than fuzzy-merged, which likely overstates the true unique branch count for those brands until a human resolves the review queue.",
            "Brand-level access attempts are diagnostics only and do not satisfy branch-specific validation coverage or create validation evidence for a branch.",
            "S010-derived evidence and all pilot outputs retaining it are private ignored local material; no public redistribution is authorised.",
        ],
    }
    write_json(report_dir / "data-quality-report.json", coverage_report)
    (report_dir / "coverage-report.md").write_text(coverage_markdown(coverage_report), encoding="utf-8")

    preliminary_secret_scan = scan_foundation_outputs_for_secrets(
        repo_root, processed_dir=processed_dir, report_dir=report_dir, credential_values=credential_values
    )
    coverage_report["acceptance_gates"] = evaluate_pilot_acceptance_gates(
        secret_scan_status=preliminary_secret_scan["status"], **gate_kwargs
    )
    write_json(report_dir / "data-quality-report.json", coverage_report)
    (report_dir / "coverage-report.md").write_text(coverage_markdown(coverage_report), encoding="utf-8")

    completion_status = (
        "failed_secret_scan"
        if preliminary_secret_scan["status"] == "fail"
        else "pilot_ready_for_national_design_approval"
        if coverage_report["acceptance_gates"]["all_gates_met"]
        else "pilot_blocked"
    )
    completion = {
        "run_id": run_id,
        "status": completion_status,
        "ready_for_national_design_approval": coverage_report["acceptance_gates"]["ready_for_national_design_approval"],
        "unmet_gates": coverage_report["acceptance_gates"]["unmet_gates"],
        "counts": {
            "planning_area_count": len(pilot_areas["selected"]),
            "brand_count": len(brands),
            "branch_count": len(branches),
            "offering_count": len(offerings),
            "evidence_count": len(evidence_rows),
            "evidence_status_counts": evidence_status_counts,
            "review_queue_count": len(review_queue),
            "geocode_status_counts": geocode_status_counts,
        },
        "secret_scan": preliminary_secret_scan,
        "verification": {
            "production_pipeline_test_execution": "not_run_by_pipeline",
            "external_verification_required": True,
        },
    }
    write_json(report_dir / "completion-report.json", completion)
    (report_dir / "completion-report.md").write_text(completion_markdown(completion), encoding="utf-8")

    manifest = {
        "run_id": run_id,
        "status": completion["status"],
        "material_inputs": [
            {"reference": str(p.relative_to(repo_root)), "sha256": sha256_file(p)} for p in material_inputs
        ],
        "processed_files": processed_file_records,
        "processed_checksum_verification": {"status": "pass" if checksums_ok else "fail", "file_count": len(processed_file_records)},
        "geocode_cache_checksum": geocode_cache_checksum,
        "secret_scan": preliminary_secret_scan,
        "publication_boundary": run_config["publication_boundary"],
    }
    write_json(report_dir / "acquisition-provenance-manifest.json", manifest)

    # This is deliberately the last reportable-output action. If it finds a
    # secret, no successful completion is returned and no later write can hide
    # the finding in an overwritten predecessor report.
    final_secret_scan = scan_foundation_outputs_for_secrets(
        repo_root, processed_dir=processed_dir, report_dir=report_dir, credential_values=credential_values
    )
    if final_secret_scan["status"] == "fail":
        raise RuntimeError(
            "final reportable-output secret scan failed; see safe finding paths/counts in the local scan result"
        )
    if final_secret_scan["status"] != preliminary_secret_scan["status"]:
        raise RuntimeError("final reportable-output secret scan status changed after final report creation")

    return {
        "run_id": run_id,
        "status": completion["status"],
        "ready_for_national_design_approval": completion["ready_for_national_design_approval"],
        "unmet_gates": completion["unmet_gates"],
        "coverage_report": str((report_dir / "data-quality-report.json").relative_to(repo_root)),
        "completion_report": str((report_dir / "completion-report.md").relative_to(repo_root)),
        "manifest": str((report_dir / "acquisition-provenance-manifest.json").relative_to(repo_root)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the corrected bounded pilot competitor-discovery pass")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = run(args.repo_root.resolve())
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
