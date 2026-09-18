from __future__ import annotations

import unittest

from tuition_location_analytics.analysis.accessibility_aggregate import (
    aggregate_accessibility,
    evaluate_h2,
    threshold_cases,
)
from tuition_location_analytics.analysis.accessibility_aggregate_cli import require_complete_cache


class AccessibilityAggregationTests(unittest.TestCase):
    def test_pt_walk_and_thresholds_are_kept_separate(self) -> None:
        plan = [
            {"od_plan_id": "A", "origin_geo_id": "G1", "origin_target_population_proxy": 100, "commercial_node_id": "N1", "node_name": "NODE", "scenario_id": "weekday", "nearest_exit_straight_line_distance_metres": 500},
            {"od_plan_id": "B", "origin_geo_id": "G2", "origin_target_population_proxy": 200, "commercial_node_id": "N1", "node_name": "NODE", "scenario_id": "weekday", "nearest_exit_straight_line_distance_metres": 900},
        ]
        outcomes = [
            {"od_plan_id": "A", "method": "pt", "category": "success", "duration_seconds": 900},
            {"od_plan_id": "B", "method": "pt", "category": "missing_route", "duration_seconds": None},
            {"od_plan_id": "B", "method": "walk", "category": "success", "duration_seconds": 500},
        ]
        cases = [{"threshold_case_id": "primary", "pt_minutes": 20, "walk_minutes": 10, "is_primary": True}]
        result = aggregate_accessibility(plan, outcomes, cases, proximity_fallback_metres=800)[0]
        self.assertEqual(result["pt_accessible_population_proxy"], 100)
        self.assertEqual(result["walking_fallback_accessible_population_proxy"], 200)
        self.assertEqual(result["proximity_fallback_accessible_population_proxy"], 0)
        self.assertEqual(result["accessible_target_population_proxy"], 300)
        self.assertEqual(result["centroid_proximity_population_proxy_800m"], 100)
        self.assertTrue(result["route_coverage_complete"])

    def test_unavailable_routes_use_frozen_proximity_fallback(self) -> None:
        plan = [{"od_plan_id": "A", "origin_geo_id": "G1", "origin_target_population_proxy": 100, "commercial_node_id": "N1", "node_name": "NODE", "scenario_id": "weekday", "nearest_exit_straight_line_distance_metres": 500}]
        outcomes = [
            {"od_plan_id": "A", "method": "pt", "category": "missing_route", "duration_seconds": None},
            {"od_plan_id": "A", "method": "walk", "category": "missing_route", "duration_seconds": None},
        ]
        cases = [{"threshold_case_id": "primary", "pt_minutes": 20, "walk_minutes": 10, "is_primary": True}]
        result = aggregate_accessibility(plan, outcomes, cases, proximity_fallback_metres=800)[0]
        self.assertEqual(result["accessible_target_population_proxy"], 100)
        self.assertEqual(result["proximity_fallback_accessible_population_proxy"], 100)
        self.assertEqual(result["transit_reach_share"], 0)
        self.assertTrue(result["route_coverage_complete"])

    def test_repeated_invalid_pt_response_uses_walk_then_proximity(self) -> None:
        plan = [{"od_plan_id": "A", "origin_geo_id": "G1", "origin_target_population_proxy": 100, "commercial_node_id": "N1", "node_name": "NODE", "scenario_id": "weekday", "nearest_exit_straight_line_distance_metres": 900}]
        outcomes = [
            {"od_plan_id": "A", "method": "pt", "category": "invalid_response", "duration_seconds": None},
            {"od_plan_id": "A", "method": "walk", "category": "success", "duration_seconds": 500},
        ]
        cases = [{"threshold_case_id": "primary", "pt_minutes": 20, "walk_minutes": 10, "is_primary": True}]
        result = aggregate_accessibility(plan, outcomes, cases, proximity_fallback_metres=800)[0]
        self.assertEqual(result["accessible_target_population_proxy"], 100)
        self.assertEqual(result["walking_fallback_accessible_population_proxy"], 100)
        self.assertEqual(result["pt_invalid_response_count"], 1)

    def test_missing_primary_or_fallback_outcome_fails(self) -> None:
        plan = [{"od_plan_id": "A", "origin_geo_id": "G1", "origin_target_population_proxy": 100, "commercial_node_id": "N1", "node_name": "NODE", "scenario_id": "weekday", "nearest_exit_straight_line_distance_metres": 500}]
        cases = [{"threshold_case_id": "primary", "pt_minutes": 20, "walk_minutes": 10, "is_primary": True}]
        with self.assertRaises(ValueError):
            aggregate_accessibility(plan, [], cases, proximity_fallback_metres=800)
        with self.assertRaises(ValueError):
            aggregate_accessibility(plan, [{"od_plan_id": "A", "method": "pt", "category": "missing_route", "duration_seconds": None}], cases, proximity_fallback_metres=800)

    def test_threshold_config_expands_one_way_sensitivities(self) -> None:
        config = {
            "primary_scenario": {"public_transport_threshold_minutes": 20, "walking_threshold_minutes": 10},
            "sensitivity_scenarios": {"public_transport_threshold_minutes": [15, 25], "walking_threshold_minutes": [5, 15]},
        }
        cases = threshold_cases(config)
        self.assertEqual(len(cases), 5)
        self.assertEqual(sum(case["is_primary"] for case in cases), 1)

    def test_h2_uses_frozen_median_and_rank_diagnostics(self) -> None:
        metrics = []
        for index in range(12):
            metrics.append(
                {
                    "commercial_node_id": f"N{index:02d}",
                    "scenario_id": "weekday",
                    "is_primary_threshold_case": True,
                    "accessible_target_population_proxy": float(120 - index * 10),
                    "centroid_proximity_population_proxy_800m": float(100 + index * 10),
                }
            )
        result = evaluate_h2(metrics, primary_scenario_id="weekday", materiality_threshold=0.10)
        self.assertTrue(result["material_difference"])
        self.assertEqual(result["valid_node_count"], 12)
        self.assertEqual(result["nodes_moving_at_least_10_ranks_count"], 2)

    def test_export_guard_rejects_partial_route_cache(self) -> None:
        with self.assertRaises(RuntimeError):
            require_complete_cache(
                [{"od_plan_id": "A"}, {"od_plan_id": "B"}],
                [{"od_plan_id": "A", "method": "pt", "category": "success"}],
            )


if __name__ == "__main__":
    unittest.main()
