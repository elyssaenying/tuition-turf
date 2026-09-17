from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from typing import Any

from pyproj import Transformer

from tuition_location_analytics.foundation.common import duplicate_values, normalize_name


def station_complex_id(normalized_station_name: str) -> str:
    digest = hashlib.sha256(normalized_station_name.encode("utf-8")).hexdigest()[:16]
    return "STC_" + digest.upper()


def station_base_name(value: str) -> str:
    return re.sub(r"\s+(?:MRT|LRT)\s+STATION$", "", normalize_name(value))


def _rail_mode(normalized_station_name: str) -> str:
    if normalized_station_name.endswith(" LRT STATION"):
        return "lrt"
    if normalized_station_name.endswith(" MRT STATION"):
        return "mrt"
    if re.fullmatch(r"[A-Z]{2}\d+[A-Z]?", normalized_station_name):
        return "mrt_code_only_unverified"
    return "unknown"


def process_train_name_rows(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("success") is not True or not isinstance(payload.get("result"), dict):
        raise RuntimeError("S026 DataStore snapshot did not report success")
    source_rows = payload["result"].get("records")
    if not isinstance(source_rows, list):
        raise RuntimeError("S026 DataStore snapshot has no records array")
    rows: list[dict[str, Any]] = []
    for row in source_rows:
        rows.append(
            {
                "source_id": "S026",
                "source_record_id": str(row.get("_id") or ""),
                "station_code": str(row.get("stn_code") or "").strip(),
                "station_name_english": str(row.get("mrt_station_english") or "").strip(),
                "station_name_chinese": str(row.get("mrt_station_chinese") or "").strip(),
                "line_name_english": str(row.get("mrt_line_english") or "").strip(),
                "line_name_chinese": str(row.get("mrt_line_chinese") or "").strip(),
                "normalized_station_base_name": normalize_name(
                    str(row.get("mrt_station_english") or "")
                ),
            }
        )
    quality = {
        "source_row_count": len(source_rows),
        "processed_row_count": len(rows),
        "duplicate_source_record_ids": duplicate_values(
            row["source_record_id"] for row in rows
        ),
        "missing_station_code_count": sum(not row["station_code"] for row in rows),
        "missing_station_name_count": sum(
            not row["station_name_english"] for row in rows
        ),
        "distinct_station_name_count": len(
            {row["normalized_station_base_name"] for row in rows}
        ),
        "coverage_limitation": "June 2017 name/code/line coverage is corroborative only and cannot exclude newer or unmatched S005 complexes.",
    }
    return {"records": rows, "quality": quality}


def _maximum_pairwise_distance(records: list[dict[str, Any]]) -> float:
    return max(
        (
            math.hypot(
                float(first["easting_3414"]) - float(second["easting_3414"]),
                float(first["northing_3414"]) - float(second["northing_3414"]),
            )
            for index, first in enumerate(records)
            for second in records[index + 1 :]
        ),
        default=0.0,
    )


def _representative_exit(records: list[dict[str, Any]]) -> dict[str, Any]:
    def total_distance(candidate: dict[str, Any]) -> tuple[float, str]:
        distance = sum(
            math.hypot(
                float(candidate["easting_3414"]) - float(other["easting_3414"]),
                float(candidate["northing_3414"]) - float(other["northing_3414"]),
            )
            for other in records
        )
        return distance, str(candidate["transit_point_id"])

    return min(records, key=total_distance)


OPERATIONAL_STATUS_VALUES = {
    "verified_operational",
    "verified_opening_within_decision_horizon",
    "not_operational",
    "unresolved",
}


def _index_overrides(station_overrides: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for entry in station_overrides:
        key = normalize_name(str(entry["normalized_source_label"]))
        if key in indexed:
            raise RuntimeError(f"duplicate station override source label: {key}")
        indexed[key] = entry
    return indexed


def _index_dispositions(
    review_dispositions: list[dict[str, Any]]
) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in review_dispositions:
        key = (
            normalize_name(str(entry["normalized_station_name"])),
            str(entry["issue_category"]),
        )
        if key in indexed:
            raise RuntimeError(f"duplicate review disposition for {key}")
        indexed[key] = entry
    return indexed


def _index_known_exceptions(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for entry in entries:
        key = normalize_name(str(entry["normalized_station_name"]))
        if key in indexed:
            raise RuntimeError(f"duplicate known operational-status exception for {key}")
        indexed[key] = entry
    return indexed


def build_station_complexes(
    exit_records: list[dict[str, Any]],
    train_name_records: list[dict[str, Any]],
    *,
    dispersion_review_threshold_metres: float,
    implausible_extent_threshold_metres: float,
    station_overrides: list[dict[str, Any]] | None = None,
    review_dispositions: list[dict[str, Any]] | None = None,
    operational_status_evidence: dict[str, Any] | None = None,
    system_map_roster: dict[str, Any] | None = None,
) -> dict[str, Any]:
    overrides_by_label = _index_overrides(station_overrides or [])
    dispositions_by_key = _index_dispositions(review_dispositions or [])
    operational_status_evidence = operational_status_evidence or {"known_exceptions": []}
    known_exceptions_by_name = _index_known_exceptions(
        operational_status_evidence.get("known_exceptions", [])
    )
    roster_base_names = {
        normalize_name(str(name))
        for name in (system_map_roster or {}).get("operational_base_names", [])
    }
    roster_source_id = (system_map_roster or {}).get("source_id")
    roster_version = (system_map_roster or {}).get("roster_version")
    used_roster_names: set[str] = set()

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    group_overrides: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in exit_records:
        raw_normalized = normalize_name(str(record["station_name"]))
        override = overrides_by_label.get(raw_normalized)
        if override is not None:
            target = normalize_name(str(override["target_normalized_station_name"]))
            groups[target].append(record)
            group_overrides[target].append(override)
        else:
            groups[raw_normalized].append(record)

    applied_override_labels = sorted(overrides_by_label)
    used_override_labels = sorted(
        {
            override["normalized_source_label"]
            for overrides in group_overrides.values()
            for override in overrides
        }
    )
    unused_overrides = sorted(set(applied_override_labels) - set(used_override_labels))

    train_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in train_name_records:
        train_by_name[record["normalized_station_base_name"]].append(record)

    reverse = Transformer.from_crs(3414, 4326, always_xy=True)
    complexes: list[dict[str, Any]] = []
    memberships: list[dict[str, Any]] = []
    review_items: list[dict[str, Any]] = []
    crosswalk: list[dict[str, Any]] = []
    matched_train_names: set[str] = set()
    used_known_exceptions: set[str] = set()

    for normalized_name, records in sorted(groups.items()):
        records = sorted(records, key=lambda row: str(row["transit_point_id"]))
        complex_id = station_complex_id(normalized_name)
        base_name = station_base_name(normalized_name)
        corroboration = train_by_name.get(base_name, [])
        if corroboration:
            matched_train_names.add(base_name)
        station_codes = sorted({row["station_code"] for row in corroboration if row["station_code"]})
        line_names = sorted(
            {row["line_name_english"] for row in corroboration if row["line_name_english"]}
        )
        chinese_names = sorted(
            {row["station_name_chinese"] for row in corroboration if row["station_name_chinese"]}
        )
        official_name_variants = sorted({str(row["station_name"]) for row in records})
        group_override_entries = group_overrides.get(normalized_name, [])
        explained_variant_labels = {entry["source_label"] for entry in group_override_entries}
        unexplained_variants = [
            variant for variant in official_name_variants if variant not in explained_variant_labels
        ]
        if unexplained_variants:
            display_name = unexplained_variants[0]
        elif group_override_entries:
            display_name = str(group_override_entries[0]["target_normalized_station_name"])
        else:
            display_name = official_name_variants[0]
        label_counts = Counter(normalize_name(str(row["exit_code"])) for row in records)
        duplicate_labels = {
            label: count for label, count in sorted(label_counts.items()) if count > 1
        }
        maximum_distance = _maximum_pairwise_distance(records)
        representative = _representative_exit(records)
        centroid_easting = sum(float(row["easting_3414"]) for row in records) / len(records)
        centroid_northing = sum(float(row["northing_3414"]) for row in records) / len(records)
        centroid_lon, centroid_lat = reverse.transform(centroid_easting, centroid_northing)
        rail_mode = _rail_mode(normalized_name)
        flags: list[str] = []
        if maximum_distance > dispersion_review_threshold_metres:
            flags.append("unusually_dispersed")
        if maximum_distance > implausible_extent_threshold_metres:
            flags.append("implausible_extent")
        if duplicate_labels:
            flags.append("repeated_exit_labels")
        if len(unexplained_variants) > 1:
            flags.append("normalized_name_collision")
        if rail_mode in {"mrt_code_only_unverified", "unknown"}:
            flags.append("ambiguous_station_name")

        known_exception = known_exceptions_by_name.get(normalized_name)
        on_map_roster = base_name in roster_base_names
        if group_override_entries:
            # Rule 1: an identity override (merge/rename) carries its own operational_status,
            # backed by its own dated station-specific evidence.
            operational_status = group_override_entries[0]["operational_status"]
            complex_operational_evidence = group_override_entries[0]["evidence"]
            operational_status_basis = group_override_entries[0]["operational_status_basis"]
        elif known_exception is not None:
            # Rule 2: an explicit, individually evidenced exception (e.g. Marina South). This
            # is the only remaining route to not_operational / opening-within-horizon.
            used_known_exceptions.add(normalized_name)
            operational_status = known_exception["operational_status"]
            complex_operational_evidence = known_exception["evidence"]
            operational_status_basis = known_exception["basis"]
        elif rail_mode in {"mrt", "lrt"} and on_map_roster:
            # Rule 3: the complex's base name appears on the current, dated official system
            # map roster (S032), which is checked against its own legend for an explicit
            # under-construction marker rather than assumed. S026 (Jun 2017) corroboration
            # plays no role here: S026 can carry names/codes for stations that were not yet
            # operating at the time (e.g. Teck Lee LRT, which only opened 15 Aug 2024), so
            # exact-name S026 corroboration alone is never used as operational evidence.
            used_roster_names.add(base_name)
            operational_status = "verified_operational"
            complex_operational_evidence = []
            operational_status_basis = (
                f"Base name matches the current dated System Map roster ({roster_source_id}, "
                f"roster version {roster_version}), whose legend was directly inspected and "
                "which marks under-construction stations distinctly; this station carries no "
                "such marker. S026 exact-name corroboration, where present, is identity "
                "corroboration only and plays no role in this determination."
            )
        elif rail_mode in {"mrt", "lrt"}:
            # Rule 4: named, but not covered by an override, exception or the current map
            # roster. Neither S026 corroboration nor mere presence in the S005 exit layer is,
            # by itself, ever sufficient evidence of current operational status.
            operational_status = "unresolved"
            complex_operational_evidence = []
            operational_status_basis = (
                "Not found on the current System Map roster and not otherwise resolved. S026 "
                "exact-name corroboration, where present, is identity corroboration only and is "
                "never treated as operational evidence by itself; presence in the S005 exit "
                "layer alone is likewise not evidence of current operational status."
            )
        else:
            operational_status = "unresolved"
            complex_operational_evidence = []
            operational_status_basis = (
                "Bare code-only or unrecognized official label with no station-override entry; "
                "operational status has not been individually verified against a primary source."
            )
        if operational_status not in OPERATIONAL_STATUS_VALUES:
            raise RuntimeError(f"invalid operational_status: {operational_status}")

        complexes.append(
            {
                "station_complex_id": complex_id,
                "definition_version": "exact-normalized-station-name-v2-with-overrides",
                "station_name": display_name,
                "normalized_station_name": normalized_name,
                "station_base_name": base_name,
                "rail_mode": rail_mode,
                "exit_count": len(records),
                "representative_method": "exit_medoid_minimum_total_euclidean_distance_epsg3414",
                "representative_exit_id": representative["transit_point_id"],
                "representative_longitude_wgs84": float(representative["longitude_wgs84"]),
                "representative_latitude_wgs84": float(representative["latitude_wgs84"]),
                "representative_easting_3414": float(representative["easting_3414"]),
                "representative_northing_3414": float(representative["northing_3414"]),
                "centroid_longitude_wgs84": centroid_lon,
                "centroid_latitude_wgs84": centroid_lat,
                "centroid_easting_3414": centroid_easting,
                "centroid_northing_3414": centroid_northing,
                "minimum_easting_3414": min(float(row["easting_3414"]) for row in records),
                "minimum_northing_3414": min(float(row["northing_3414"]) for row in records),
                "maximum_easting_3414": max(float(row["easting_3414"]) for row in records),
                "maximum_northing_3414": max(float(row["northing_3414"]) for row in records),
                "maximum_pairwise_exit_distance_metres": maximum_distance,
                "has_duplicate_exit_labels": bool(duplicate_labels),
                "duplicate_exit_labels_json": json.dumps(duplicate_labels, sort_keys=True),
                "name_variant_count": len(official_name_variants),
                "name_variants_json": json.dumps(official_name_variants, ensure_ascii=False),
                "corroboration_source_id": "S026" if corroboration else None,
                "corroboration_status": (
                    "exact_base_name_match" if corroboration else "unmatched_older_source"
                ),
                "station_codes_json": json.dumps(station_codes),
                "line_names_json": json.dumps(line_names),
                "station_names_chinese_json": json.dumps(chinese_names, ensure_ascii=False),
                "coordinate_quality_status": "all_exits_validated_in_foundation",
                "exchange_crs": "EPSG:4326",
                "metric_crs": "EPSG:3414",
                "review_flags_json": json.dumps(flags),
                "manual_review_required": bool(flags),
                "closest_exit_required_for_later_accessibility": True,
                "operational_status": operational_status,
                "operational_status_basis": operational_status_basis,
                "operational_status_evidence_json": json.dumps(
                    complex_operational_evidence, ensure_ascii=False
                ),
                "operational_status_map_roster_match": on_map_roster,
                "station_override_applied": bool(group_override_entries),
                "station_override_source_labels_json": json.dumps(
                    sorted(entry["source_label"] for entry in group_override_entries)
                ),
            }
        )
        for record in records:
            memberships.append(
                {
                    "station_complex_id": complex_id,
                    "source_id": "S005",
                    "transit_point_id": record["transit_point_id"],
                    "source_unique_id": record["source_unique_id"],
                    "station_name_official": record["station_name"],
                    "normalized_station_name": normalized_name,
                    "exit_label_official": record["exit_code"],
                    "normalized_exit_label": normalize_name(str(record["exit_code"])),
                    "longitude_wgs84": float(record["longitude_wgs84"]),
                    "latitude_wgs84": float(record["latitude_wgs84"]),
                    "easting_3414": float(record["easting_3414"]),
                    "northing_3414": float(record["northing_3414"]),
                    "membership_method": (
                        "exact_normalized_station_name"
                        if not group_override_entries
                        else "exact_normalized_station_name_with_authoritative_override"
                    ),
                }
            )
        for flag in flags:
            review_id = "REV_" + hashlib.sha256(
                f"{complex_id}|{flag}".encode("utf-8")
            ).hexdigest()[:16].upper()
            if flag == "unusually_dispersed":
                relevant_value = f"{display_name}; {maximum_distance:.3f} m maximum exit distance"
                suggested = "Confirm that all official exit points belong to one operational complex; do not split without authoritative evidence."
                decision = "Keep the exact-name group or provide an authoritative split mapping."
            elif flag == "repeated_exit_labels":
                relevant_value = f"{display_name}; " + json.dumps(
                    duplicate_labels, sort_keys=True
                )
                suggested = "Retain every source point and verify whether official duplicate labels represent separate structures or a source-label issue."
                decision = "Accept the duplicates or provide an authoritative corrected label/membership mapping."
            elif flag == "ambiguous_station_name":
                relevant_value = f"{display_name}; normalized label {normalized_name}"
                suggested = "Resolve the code-only or unclassified official label against a current authoritative station reference."
                decision = "Confirm the operational station name and MRT eligibility without merging by proximity."
            elif flag == "implausible_extent":
                relevant_value = f"{display_name}; {maximum_distance:.3f} m maximum exit distance"
                suggested = "Inspect coordinates and official membership before any downstream use."
                decision = "Confirm, correct or exclude the affected official point membership."
            else:
                relevant_value = json.dumps(official_name_variants, ensure_ascii=False)
                suggested = "Review the exact source labels that collapse after case/whitespace normalization."
                decision = "Confirm that the normalized-name grouping is valid."
            disposition = dispositions_by_key.get((normalized_name, flag))
            status = "open"
            resolution_summary = None
            semantic_ambiguity_quality_flag = False
            if disposition is not None:
                status = disposition["status"]
                resolution_summary = disposition["resolution_summary"]
                semantic_ambiguity_quality_flag = bool(
                    disposition.get("semantic_ambiguity_quality_flag", False)
                )
            review_items.append(
                {
                    "review_item_id": review_id,
                    "station_complex_id": complex_id,
                    "commercial_node_id": None,
                    "issue_category": flag,
                    "relevant_values": relevant_value,
                    "evidence_refs_json": json.dumps(
                        [f"S005:{row['source_unique_id']}" for row in records]
                    ),
                    "suggested_resolution": suggested,
                    "human_decision_required": decision,
                    "status": status,
                    "resolution_summary": resolution_summary,
                    "semantic_ambiguity_quality_flag": semantic_ambiguity_quality_flag,
                }
            )
        distinct_overrides = list({entry["source_label"]: entry for entry in group_override_entries}.values())
        for override in distinct_overrides:
            crosswalk.append(
                {
                    "previous_station_complex_id": station_complex_id(
                        normalize_name(str(override["source_label"]))
                    ),
                    "previous_normalized_station_name": normalize_name(
                        str(override["source_label"])
                    ),
                    "new_station_complex_id": complex_id,
                    "new_normalized_station_name": normalized_name,
                    "resolution": override["resolution"],
                    "merged_into_pre_existing_complex": bool(unexplained_variants),
                    "operational_status": operational_status,
                    "override_config_version": override.get("override_config_version"),
                    "rationale": override["rationale"],
                    "evidence_json": json.dumps(override["evidence"], ensure_ascii=False),
                }
            )

    membership_ids = [row["transit_point_id"] for row in memberships]
    input_ids = [str(row["transit_point_id"]) for row in exit_records]
    quality = {
        "input_exit_count": len(exit_records),
        "membership_row_count": len(memberships),
        "station_complex_count": len(complexes),
        "mrt_complex_count": sum(row["rail_mode"] == "mrt" for row in complexes),
        "lrt_complex_count": sum(row["rail_mode"] == "lrt" for row in complexes),
        "code_only_or_unknown_complex_count": sum(
            row["rail_mode"] in {"mrt_code_only_unverified", "unknown"}
            for row in complexes
        ),
        "duplicate_membership_exit_ids": duplicate_values(membership_ids),
        "missing_membership_exit_ids": sorted(set(input_ids) - set(membership_ids)),
        "unexpected_membership_exit_ids": sorted(set(membership_ids) - set(input_ids)),
        "repeated_exit_label_complex_count": sum(
            row["has_duplicate_exit_labels"] for row in complexes
        ),
        "dispersed_complex_count": sum(
            row["maximum_pairwise_exit_distance_metres"]
            > dispersion_review_threshold_metres
            for row in complexes
        ),
        "implausible_extent_complex_count": sum(
            row["maximum_pairwise_exit_distance_metres"]
            > implausible_extent_threshold_metres
            for row in complexes
        ),
        "manual_review_complex_count": sum(
            row["manual_review_required"] for row in complexes
        ),
        "s026_exact_match_complex_count": sum(
            row["corroboration_status"] == "exact_base_name_match" for row in complexes
        ),
        "s026_unmatched_complex_count": sum(
            row["corroboration_status"] != "exact_base_name_match" for row in complexes
        ),
        "s026_train_only_names": sorted(set(train_by_name) - matched_train_names),
        "grouping_method": "Exact case/whitespace-normalized S005 station name; no fuzzy or distance-based merge/split. Authoritative station overrides are applied before grouping, never by proximity alone.",
        "dispersion_review_threshold_metres": dispersion_review_threshold_metres,
        "dispersion_threshold_rationale": "The 400 m threshold equals the smallest fixed commercial-evidence proximity band, so a wider exit set can materially change exit-union buffer evidence. It is a review trigger, never a grouping rule.",
        "operational_status_counts": dict(
            sorted(Counter(row["operational_status"] for row in complexes).items())
        ),
        "station_overrides_applied_count": sum(row["station_override_applied"] for row in complexes),
        "station_override_source_label_count": len(used_override_labels),
        "unused_station_override_labels": unused_overrides,
        "open_review_item_count": sum(item["status"] == "open" for item in review_items),
        "closed_review_item_count": sum(item["status"] == "closed" for item in review_items),
        "station_complex_id_crosswalk_count": len(crosswalk),
        "known_operational_exceptions_applied": sorted(used_known_exceptions),
        "unused_known_operational_exceptions": sorted(
            set(known_exceptions_by_name) - used_known_exceptions
        ),
        "system_map_roster_source_id": roster_source_id,
        "system_map_roster_version": roster_version,
        "system_map_roster_names_matched_count": len(used_roster_names),
        "system_map_roster_unmatched_names": sorted(roster_base_names - used_roster_names),
    }
    return {
        "complexes": complexes,
        "memberships": memberships,
        "review_items": review_items,
        "station_complex_id_crosswalk": crosswalk,
        "quality": quality,
    }
