from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import Point, shape
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree


def process_land_use(
    raw_path: Path, accepted_categories: list[str]
) -> dict[str, Any]:
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection" or not isinstance(
        payload.get("features"), list
    ):
        raise RuntimeError("S027 is not a GeoJSON FeatureCollection")
    accepted = set(accepted_categories)
    if not accepted:
        raise RuntimeError("accepted MP2025 land-use categories must be frozen")
    forward = Transformer.from_crs(4326, 3414, always_xy=True)
    category_counts: Counter[str] = Counter()
    source_invalid_count = 0
    relevant_records: list[dict[str, Any]] = []
    relevant_geometries: list[Any] = []
    relevant_geometry_repair_count = 0
    missing_object_id_count = 0

    for feature in payload["features"]:
        properties = feature.get("properties") or {}
        category = str(properties.get("LU_DESC") or "").strip().upper()
        category_counts[category] += 1
        geometry = shape(feature.get("geometry"))
        if not geometry.is_valid:
            source_invalid_count += 1
        if category not in accepted:
            continue
        if not geometry.is_valid:
            geometry = make_valid(geometry)
            relevant_geometry_repair_count += 1
        if geometry.is_empty or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise RuntimeError("accepted S027 feature has unusable polygon geometry")
        object_id = str(properties.get("OBJECTID") or "")
        missing_object_id_count += int(not object_id)
        metric_geometry = transform(forward.transform, geometry)
        relevant_records.append(
            {
                "source_id": "S027",
                "source_object_id": object_id,
                "land_use_category": category,
                "gpr_source": (
                    None if properties.get("GPR") in {None, ""} else str(properties.get("GPR"))
                ),
                "area_sqm_3414": metric_geometry.area,
            }
        )
        relevant_geometries.append(metric_geometry)

    missing_categories = sorted(accepted - set(category_counts))
    if missing_categories:
        raise RuntimeError(
            "configured MP2025 land-use categories were not observed: "
            + ", ".join(missing_categories)
        )
    quality = {
        "source_feature_count": len(payload["features"]),
        "observed_land_use_categories": dict(sorted(category_counts.items())),
        "accepted_land_use_categories": sorted(accepted),
        "relevant_feature_count": len(relevant_records),
        "source_invalid_geometry_count": source_invalid_count,
        "relevant_geometry_repair_count": relevant_geometry_repair_count,
        "missing_relevant_object_id_count": missing_object_id_count,
        "duplicate_relevant_object_ids": sorted(
            key
            for key, count in Counter(
                record["source_object_id"] for record in relevant_records
            ).items()
            if key and count > 1
        ),
        "classification_rule": "Only explicitly commercial or explicitly commercial-mixed MP2025 categories are accepted. Business/industrial, White, hotel, educational and other unrelated categories are excluded.",
        "vintage_limitation": "MP2025 zoning is Dec 2025 context while population remains harmonised to MP2019 subzones. Zoning is not current occupancy, unit availability or tuition-use eligibility.",
    }
    return {
        "records": relevant_records,
        "geometries": relevant_geometries,
        "quality": quality,
    }


def _node_id(station_complex_id: str) -> str:
    digest = hashlib.sha256(station_complex_id.encode("utf-8")).hexdigest()[:16]
    return "NODE_" + digest.upper()


def _review_id(station_complex_id: str, issue_category: str) -> str:
    digest = hashlib.sha256(
        f"{station_complex_id}|{issue_category}".encode("utf-8")
    ).hexdigest()[:16]
    return "REV_" + digest.upper()


def build_commercial_nodes(
    complexes: list[dict[str, Any]],
    memberships: list[dict[str, Any]],
    station_review_items: list[dict[str, Any]],
    land_use: dict[str, Any],
    *,
    buffer_metres: list[int],
    minimum_independent_signals: int,
) -> dict[str, Any]:
    if sorted(buffer_metres) != buffer_metres or not buffer_metres:
        raise ValueError("commercial buffer distances must be nonempty and sorted")
    members_by_complex: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in memberships:
        members_by_complex[row["station_complex_id"]].append(row)
    excluded_not_yet_operational = [
        row
        for row in complexes
        if row["rail_mode"] in {"mrt", "mrt_code_only_unverified"}
        and row.get("operational_status")
        in {"verified_opening_within_decision_horizon", "not_operational"}
    ]
    candidate_complexes = [
        row
        for row in complexes
        if row["rail_mode"] in {"mrt", "mrt_code_only_unverified"}
        and row.get("operational_status")
        not in {"verified_opening_within_decision_horizon", "not_operational"}
    ]
    candidate_ids = {row["station_complex_id"] for row in candidate_complexes}
    seen_review_keys: set[tuple[str, str]] = set()
    review_items: list[dict[str, Any]] = []
    for item in station_review_items:
        if item["station_complex_id"] not in candidate_ids:
            continue
        key = (item["station_complex_id"], item["issue_category"])
        if key in seen_review_keys:
            continue
        seen_review_keys.add(key)
        copy = dict(item)
        copy["commercial_node_id"] = _node_id(item["station_complex_id"])
        review_items.append(copy)
    for row in excluded_not_yet_operational:
        key = (row["station_complex_id"], "excluded_not_yet_operational")
        if key in seen_review_keys:
            continue
        seen_review_keys.add(key)
        review_items.append(
            {
                "review_item_id": _review_id(row["station_complex_id"], "excluded_not_yet_operational"),
                "station_complex_id": row["station_complex_id"],
                "commercial_node_id": _node_id(row["station_complex_id"]),
                "issue_category": "excluded_not_yet_operational",
                "relevant_values": f"{row['station_name']}; operational_status={row['operational_status']}",
                "evidence_refs_json": row.get("operational_status_evidence_json", "[]"),
                "suggested_resolution": "Do not include in current accessibility or commercial-node calculations until the decision horizon is extended and re-approved, or the station is confirmed operational.",
                "human_decision_required": "Approve a separately labelled forward-looking scenario before any accessibility use, or reconfirm current operational status.",
                "status": "open",
                "resolution_summary": None,
                "semantic_ambiguity_quality_flag": False,
            }
        )

    geometries = land_use["geometries"]
    records = land_use["records"]
    tree = STRtree(geometries) if geometries else None
    evidence_rows: list[dict[str, Any]] = []
    evidence_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for complex_record in candidate_complexes:
        complex_id = complex_record["station_complex_id"]
        node_id = _node_id(complex_id)
        exit_points = [
            Point(float(row["easting_3414"]), float(row["northing_3414"]))
            for row in members_by_complex[complex_id]
        ]
        for distance in buffer_metres:
            buffer_geometry = unary_union([point.buffer(distance) for point in exit_points])
            intersecting_indices = (
                [int(index) for index in tree.query(buffer_geometry, predicate="intersects")]
                if tree is not None
                else []
            )
            intersections_by_category: dict[str, list[Any]] = defaultdict(list)
            for index in intersecting_indices:
                intersection = geometries[index].intersection(buffer_geometry)
                if not intersection.is_empty and intersection.area > 0:
                    intersections_by_category[records[index]["land_use_category"]].append(
                        intersection
                    )
            category_areas = {
                category: unary_union(parts).area
                for category, parts in sorted(intersections_by_category.items())
            }
            covered_geometry = unary_union(
                [part for parts in intersections_by_category.values() for part in parts]
            )
            covered_area = 0.0 if covered_geometry.is_empty else covered_geometry.area
            nearest_distance = None
            if tree is not None and exit_points:
                nearest_distance = min(
                    point.distance(geometries[int(tree.nearest(point))])
                    for point in exit_points
                )
            landuse_evidence = {
                "commercial_node_id": node_id,
                "station_complex_id": complex_id,
                "evidence_signal_id": "mp2025_relevant_commercial_zoning",
                "independent_signal_key": "official_land_use_zoning",
                "buffer_metres": distance,
                "proximity_method": "union_of_straight_line_buffers_from_all_valid_exits_epsg3414",
                "measurement_status": "observed",
                "positive_signal": covered_area > 0,
                "source_ids_json": json.dumps(["S027"]),
                "relevant_feature_count": sum(
                    len(parts) for parts in intersections_by_category.values()
                ),
                "relevant_area_sqm": covered_area,
                "buffer_area_sqm": buffer_geometry.area,
                "relevant_area_share": covered_area / buffer_geometry.area,
                "nearest_relevant_feature_distance_metres": nearest_distance,
                "category_area_sqm_json": json.dumps(category_areas, sort_keys=True),
                "missing_reason": None,
                "interpretation_limit": "Indicative MP2025 zoning context only; not occupancy, availability or premises eligibility.",
            }
            evidence_rows.append(landuse_evidence)
            evidence_by_node[node_id].append(landuse_evidence)
            missing_hdb_evidence = {
                "commercial_node_id": node_id,
                "station_complex_id": complex_id,
                "evidence_signal_id": "validated_hdb_commercial_building_proximity",
                "independent_signal_key": "hdb_commercial_building",
                "buffer_metres": distance,
                "proximity_method": "not_calculated",
                "measurement_status": "missing",
                "positive_signal": None,
                "source_ids_json": json.dumps([]),
                "relevant_feature_count": None,
                "relevant_area_sqm": None,
                "buffer_area_sqm": buffer_geometry.area,
                "relevant_area_share": None,
                "nearest_relevant_feature_distance_metres": None,
                "category_area_sqm_json": None,
                "missing_reason": "HDB property commercial flags cannot be joined deterministically to HDB building geometry without a shared identifier or a separately approved geocode step.",
                "interpretation_limit": "Missing evidence is unknown, not measured zero.",
            }
            evidence_rows.append(missing_hdb_evidence)
            evidence_by_node[node_id].append(missing_hdb_evidence)

    candidates: list[dict[str, Any]] = []
    largest_buffer = max(buffer_metres)
    for complex_record in candidate_complexes:
        complex_id = complex_record["station_complex_id"]
        node_id = _node_id(complex_id)
        largest_band_evidence = [
            row for row in evidence_by_node[node_id] if row["buffer_metres"] == largest_buffer
        ]
        positive_signals = sorted(
            {
                row["independent_signal_key"]
                for row in largest_band_evidence
                if row["measurement_status"] == "observed" and row["positive_signal"] is True
            }
        )
        missing_signals = sorted(
            {
                row["independent_signal_key"]
                for row in largest_band_evidence
                if row["measurement_status"] == "missing"
            }
        )
        if not positive_signals:
            zoning_key = (complex_id, "no_commercial_zoning_signal")
            if zoning_key not in seen_review_keys:
                seen_review_keys.add(zoning_key)
                review_items.append(
                    {
                        "review_item_id": _review_id(complex_id, "no_commercial_zoning_signal"),
                        "station_complex_id": complex_id,
                        "commercial_node_id": node_id,
                        "issue_category": "no_commercial_zoning_signal",
                        "relevant_values": f"{complex_record['station_name']}; 0 relevant zoning area within {largest_buffer} m exit-union buffer",
                        "evidence_refs_json": json.dumps(["S027"]),
                        "suggested_resolution": "Check whether a separate current, systematic and legally reusable commercial signal exists; retain missing evidence if none exists.",
                        "human_decision_required": "Confirm provisional commercial-node evidence or exclude the node from later comparison.",
                        "status": "open",
                        "resolution_summary": None,
                        "semantic_ambiguity_quality_flag": False,
                    }
                )
        if complex_record.get("operational_status") == "unresolved":
            operational_key = (complex_id, "unresolved_operational_status")
            if operational_key not in seen_review_keys:
                seen_review_keys.add(operational_key)
                review_items.append(
                    {
                        "review_item_id": _review_id(complex_id, "unresolved_operational_status"),
                        "station_complex_id": complex_id,
                        "commercial_node_id": node_id,
                        "issue_category": "unresolved_operational_status",
                        "relevant_values": f"{complex_record['station_name']}; operational_status=unresolved",
                        "evidence_refs_json": complex_record.get(
                            "operational_status_evidence_json", "[]"
                        ),
                        "suggested_resolution": "Individually confirm current operational status against a primary LTA source, or add a station-override entry once evidence is found.",
                        "human_decision_required": "Confirm operational status before this node is used in any accessibility or commercial-node calculation.",
                        "status": "open",
                        "resolution_summary": None,
                        "semantic_ambiguity_quality_flag": False,
                    }
                )
        # Every independent review issue for this node (ambiguous identity, repeated
        # labels, unusual dispersion, unresolved operational status, no zoning signal,
        # etc.) is appended above/earlier and deduplicated only by (complex_id,
        # issue_category). Multiple simultaneous issues never suppress one another:
        # qualification looks at the full, independently-built review-item list.
        open_review_for_node = [
            item
            for item in review_items
            if item["station_complex_id"] == complex_id and item["status"] == "open"
        ]
        if open_review_for_node:
            qualification_status = "needs_manual_review"
        elif len(positive_signals) >= minimum_independent_signals:
            qualification_status = "qualified"
        elif positive_signals:
            qualification_status = "provisional"
        else:
            qualification_status = "needs_manual_review"
        candidates.append(
            {
                "commercial_node_id": node_id,
                "station_complex_id": complex_id,
                "node_name": complex_record["station_name"],
                "node_type": "rail_station_complex",
                "node_definition_version": "station-complex-commercial-evidence-v2-corrected",
                "operational_status": complex_record["operational_status"],
                "operational_status_basis": complex_record["operational_status_basis"],
                "anchor_method": "station_complex_representative_exit_medoid",
                "anchor_longitude_wgs84": complex_record[
                    "representative_longitude_wgs84"
                ],
                "anchor_latitude_wgs84": complex_record[
                    "representative_latitude_wgs84"
                ],
                "exit_count": complex_record["exit_count"],
                "commercial_signal_count": len(positive_signals),
                "positive_signal_keys_json": json.dumps(positive_signals),
                "missing_signal_keys_json": json.dumps(missing_signals),
                "qualification_status": qualification_status,
                "commercial_evidence_status": (
                    "partial" if positive_signals else "missing"
                ),
                "qualification_rule": f"At least {minimum_independent_signals} independent positive signal families at the {largest_buffer} m evidence band.",
                "commercial_context_limitation": "A station is only an accessibility anchor. Zoning and any later building signal do not prove occupancy, availability or tuition-centre eligibility.",
            }
        )

    status_counts = Counter(row["qualification_status"] for row in candidates)
    operational_status_counts = Counter(row["operational_status"] for row in candidates)
    issue_category_counts = Counter(row["issue_category"] for row in review_items)
    issue_category_open_counts = Counter(
        row["issue_category"] for row in review_items if row["status"] == "open"
    )
    quality = {
        "station_complex_count": len(complexes),
        "commercial_node_candidate_count": len(candidates),
        "lrt_complexes_not_promoted_to_mrt_candidates": sum(
            row["rail_mode"] == "lrt" for row in complexes
        ),
        "excluded_not_yet_operational_count": len(excluded_not_yet_operational),
        "qualification_status_counts": dict(sorted(status_counts.items())),
        "operational_status_counts_among_candidates": dict(sorted(operational_status_counts.items())),
        "commercial_evidence_row_count": len(evidence_rows),
        "review_queue_row_count": len(review_items),
        "review_queue_open_count": sum(row["status"] == "open" for row in review_items),
        "review_queue_closed_count": sum(row["status"] == "closed" for row in review_items),
        "review_issue_category_counts": dict(sorted(issue_category_counts.items())),
        "review_issue_category_open_counts": dict(sorted(issue_category_open_counts.items())),
        "review_queue_deduplication_rule": "One review item per (station_complex_id, issue_category); multiple distinct issue categories on the same node are all retained independently.",
        "minimum_independent_signals_for_qualified": minimum_independent_signals,
        "buffer_metres": buffer_metres,
        "buffer_semantics": "Straight-line union buffers from every valid station exit in EPSG:3414; not walking time.",
        "qualified_nodes_without_minimum_signals": sum(
            row["qualification_status"] == "qualified"
            and row["commercial_signal_count"] < minimum_independent_signals
            for row in candidates
        ),
        "missing_evidence_treated_as_zero": False,
    }
    return {
        "candidates": candidates,
        "evidence": evidence_rows,
        "review_items": sorted(review_items, key=lambda row: row["review_item_id"]),
        "excluded_not_yet_operational": excluded_not_yet_operational,
        "quality": quality,
    }
