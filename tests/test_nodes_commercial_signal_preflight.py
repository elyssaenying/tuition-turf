from __future__ import annotations

from copy import deepcopy

from tuition_location_analytics.nodes.commercial_signal_preflight import (
    evaluate_gates,
    parse_pharmacy_points,
)
from tuition_location_analytics.nodes.commercial_signal_apply import apply_second_signal


def _config() -> dict:
    return {
        "method": {"primary_buffer_metres": 800},
        "predeclared_acceptance_gates": {
            "minimum_official_feature_count": 2,
            "minimum_valid_in_bounds_point_rate": 0.99,
            "maximum_source_age_months": 18,
            "required_planning_regions": 2,
            "minimum_source_points_per_region": 1,
            "maximum_unassigned_source_point_rate": 0.01,
            "maximum_unassigned_node_count": 0,
            "minimum_national_node_coverage_rate_at_primary_buffer": 0.5,
            "minimum_node_coverage_rate_per_region_at_primary_buffer": 0.5,
            "minimum_positive_nodes_nationally": 2,
            "minimum_positive_nodes_per_region": 1,
        },
    }


def test_parse_pharmacy_points_reports_invalid_and_out_of_bounds() -> None:
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "geometry": {"type": "Point", "coordinates": [103.8, 1.3]},
                "properties": {"OBJECTID_1": 1, "PHARMACY_NAME": "A"},
            },
            {
                "geometry": {"type": "LineString", "coordinates": []},
                "properties": {"OBJECTID_1": 2},
            },
            {
                "geometry": {"type": "Point", "coordinates": [120.0, 1.3]},
                "properties": {"OBJECTID_1": 3},
            },
        ],
    }

    points, quality = parse_pharmacy_points(payload)

    assert len(points) == 1
    assert quality["source_feature_count"] == 3
    assert quality["invalid_geometry_count"] == 1
    assert quality["out_of_bounds_count"] == 1
    assert quality["valid_in_bounds_point_rate"] == 1 / 3


def test_evaluate_gates_accepts_only_when_every_frozen_rule_passes() -> None:
    config = _config()
    source_quality = {"source_feature_count": 2, "valid_in_bounds_point_rate": 1.0}
    diagnostics = {
        "source_points_by_region": {"EAST": 1, "WEST": 1},
        "unassigned_source_point_rate": 0.0,
        "unassigned_node_count": 0,
    }
    coverage = [
        {"buffer_metres": 800, "planning_region": "EAST", "positive_signal": True},
        {"buffer_metres": 800, "planning_region": "WEST", "positive_signal": True},
    ]

    gates, metrics = evaluate_gates(
        config,
        source_quality,
        diagnostics,
        coverage,
        source_age_months=6,
    )

    assert all(gate["status"] == "pass" for gate in gates)
    assert metrics["positive_node_count"] == 2

    rejected = deepcopy(diagnostics)
    rejected["source_points_by_region"]["WEST"] = 0
    gates, _ = evaluate_gates(
        config,
        source_quality,
        rejected,
        coverage,
        source_age_months=6,
    )
    assert next(gate for gate in gates if gate["gate"] == "minimum_source_points_per_region")[
        "status"
    ] == "fail"


def test_apply_second_signal_qualifies_only_two_positive_families() -> None:
    candidates = [
        {
            "commercial_node_id": "N1",
            "station_complex_id": "S1",
            "node_name": "ONE",
            "node_definition_version": "old",
            "anchor_longitude_wgs84": "103.8",
            "anchor_latitude_wgs84": "1.3",
            "exit_count": "2",
            "commercial_signal_count": "1",
            "positive_signal_keys_json": '["official_land_use_zoning"]',
            "missing_signal_keys_json": '["old"]',
            "qualification_status": "provisional",
            "commercial_evidence_status": "partial",
        },
        {
            "commercial_node_id": "N2",
            "station_complex_id": "S2",
            "node_name": "TWO",
            "node_definition_version": "old",
            "anchor_longitude_wgs84": "103.9",
            "anchor_latitude_wgs84": "1.4",
            "exit_count": "1",
            "commercial_signal_count": "1",
            "positive_signal_keys_json": '["official_land_use_zoning"]',
            "missing_signal_keys_json": '["old"]',
            "qualification_status": "provisional",
            "commercial_evidence_status": "partial",
        },
    ]
    original_evidence = []
    coverage = []
    for node_id, station_id, pharmacy_positive in (("N1", "S1", True), ("N2", "S2", False)):
        for buffer_metres in (400, 800):
            original_evidence.append(
                {
                    "commercial_node_id": node_id,
                    "station_complex_id": station_id,
                    "evidence_signal_id": "zoning",
                    "independent_signal_key": "official_land_use_zoning",
                    "buffer_metres": str(buffer_metres),
                    "proximity_method": "buffers",
                    "measurement_status": "observed",
                    "positive_signal": "True",
                    "source_ids_json": '["S027"]',
                    "relevant_feature_count": "1",
                    "relevant_area_sqm": "10",
                    "buffer_area_sqm": "100",
                    "relevant_area_share": "0.1",
                    "nearest_relevant_feature_distance_metres": "1",
                    "category_area_sqm_json": "{}",
                    "missing_reason": "",
                    "interpretation_limit": "zoning only",
                }
            )
            coverage.append(
                {
                    "commercial_node_id": node_id,
                    "station_complex_id": station_id,
                    "source_id": "S034",
                    "evidence_signal_id": "pharmacy",
                    "independent_signal_key": "licensed_retail_presence",
                    "buffer_metres": str(buffer_metres),
                    "proximity_method": "buffers",
                    "measurement_status": "observed",
                    "positive_signal": str(pharmacy_positive),
                    "distinct_pharmacy_count": "1" if pharmacy_positive else "0",
                    "nearest_pharmacy_distance_metres": "5",
                    "interpretation_limit": "proxy only",
                }
            )

    updated, evidence, quality = apply_second_signal(candidates, original_evidence, coverage)

    assert [row["qualification_status"] for row in updated] == ["qualified", "provisional"]
    assert quality["qualified_node_count"] == 1
    assert len(evidence) == 8
