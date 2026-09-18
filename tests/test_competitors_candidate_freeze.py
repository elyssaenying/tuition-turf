from __future__ import annotations

from tuition_location_analytics.competitors.candidate_freeze import build_candidate_freeze


def test_candidate_freeze_uses_merit_then_balances_regions() -> None:
    nodes = []
    proximity = []
    accessibility = []
    regions = ["A", "A", "A", "B", "B", "C"]
    for index, region in enumerate(regions, start=1):
        node_id = f"N{index}"
        nodes.append(
            {
                "commercial_node_id": node_id,
                "station_complex_id": f"S{index}",
                "node_name": node_id,
                "qualification_status": "qualified",
                "commercial_signal_count": "2",
            }
        )
        proximity.append(
            {
                "commercial_node_id": node_id,
                "planning_area_name_at_anchor": region,
                "region_name_at_anchor": region,
                "proximity_target_population_proxy_800m": str(100 - index),
            }
        )
        accessibility.append(
            {
                "commercial_node_id": node_id,
                "scenario_id": "primary",
                "threshold_case_id": "main",
                "accessible_target_population_proxy": str(100 - index),
                "route_coverage_complete": "True",
            }
        )
    config = {
        "eligibility": {
            "qualification_status": "qualified",
            "accessibility_scenario_id": "primary",
            "accessibility_threshold_case_id": "main",
            "require_route_coverage_complete": True,
            "require_known_planning_region": True,
        },
        "screen": {
            "population_metric": "proximity_target_population_proxy_800m",
            "accessibility_metric": "accessible_target_population_proxy",
            "weights": {
                "population_proximity_percentile": 0.5,
                "accessibility_percentile": 0.5,
            },
        },
        "selection": {"maximum_nodes": 4, "merit_slots": 2, "regional_coverage_slots": 2},
    }

    eligible, selected, quality = build_candidate_freeze(nodes, proximity, accessibility, config)

    assert len(eligible) == 6
    assert [row["commercial_node_id"] for row in selected[:2]] == ["N1", "N2"]
    assert [row["planning_region"] for row in selected[2:]] == ["B", "C"]
    assert quality["selected_region_counts"] == {"A": 2, "B": 1, "C": 1}
    assert quality["competitor_inputs_used"] is False
