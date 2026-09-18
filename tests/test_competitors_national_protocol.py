from __future__ import annotations

from tuition_location_analytics.competitors.national_protocol import build_query_schedule


def test_query_schedule_applies_every_template_to_disjoint_target_sets() -> None:
    candidates = [
        {
            "commercial_node_id": "N1",
            "station_complex_id": "S1",
            "node_name": "ALPHA MRT STATION",
            "planning_region": "EAST",
        }
    ]
    audit = [
        {
            "commercial_node_id": "N2",
            "station_complex_id": "S2",
            "node_name": "BETA MRT STATION",
            "planning_region": "WEST",
        }
    ]
    templates = [
        {"template_id": "p", "template_code": "P", "query_text_template": "{place_name} primary"},
        {"template_id": "s", "template_code": "S", "query_text_template": "{place_name} secondary"},
    ]

    schedule = build_query_schedule(candidates, audit, templates)

    assert len(schedule) == 4
    assert len({row["query_id"] for row in schedule}) == 4
    assert {row["target_set"] for row in schedule} == {"candidate", "outside_audit"}
    assert {row["execution_status"] for row in schedule} == {"not_started"}
    assert {row["query_text"] for row in schedule} == {
        "ALPHA primary",
        "ALPHA secondary",
        "BETA primary",
        "BETA secondary",
    }


def test_benchmark_roles_are_added_without_duplicate_queries() -> None:
    candidate = {
        "commercial_node_id": "N1",
        "station_complex_id": "S1",
        "node_name": "ALPHA MRT STATION",
        "planning_region": "EAST",
    }
    benchmark_overlap = {**candidate, "benchmark_id": "hub"}
    benchmark_only = {
        "commercial_node_id": "N2",
        "station_complex_id": "S2",
        "node_name": "BETA MRT STATION",
        "planning_region": "WEST",
        "benchmark_id": "hub",
    }
    template = [
        {"template_id": "p", "template_code": "P", "query_text_template": "{place_name} primary"}
    ]

    schedule = build_query_schedule([candidate], [], template, [benchmark_overlap, benchmark_only])

    assert len(schedule) == 2
    overlap = next(row for row in schedule if row["commercial_node_id"] == "N1")
    assert overlap["target_set"] == "candidate"
    assert overlap["strategic_benchmark"] is True
    assert overlap["target_sets_json"] == '["candidate", "strategic_benchmark"]'
