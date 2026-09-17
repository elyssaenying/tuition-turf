from __future__ import annotations

import json
import unittest
from pathlib import Path

from tuition_location_analytics.analysis.routing_plan import build_routing_plan, closest_exit


REPO_ROOT = Path(__file__).resolve().parents[1]


class ClosestExitTests(unittest.TestCase):
    def test_closest_exit_is_origin_specific_and_ties_use_stable_id(self) -> None:
        origin = {"centroid_easting_3414": 0, "centroid_northing_3414": 0}
        exits = [
            {"transit_point_id": "B", "easting_3414": 3, "northing_3414": 4},
            {"transit_point_id": "A", "easting_3414": -3, "northing_3414": -4},
        ]
        selected, distance = closest_exit(origin, exits)
        self.assertEqual(selected["transit_point_id"], "A")
        self.assertEqual(distance, 5)

    def test_missing_exits_fail(self) -> None:
        with self.assertRaises(ValueError):
            closest_exit({"centroid_easting_3414": 0, "centroid_northing_3414": 0}, [])


class RoutingPlanTests(unittest.TestCase):
    def test_cartesian_plan_count_and_no_network_outcome_fields(self) -> None:
        origins = [
            {
                "geo_id": "G1",
                "subzone_name": "ONE",
                "planning_area_name": "P",
                "region_name": "R",
                "centroid_easting_3414": 0,
                "centroid_northing_3414": 0,
                "centroid_latitude_wgs84": 1.3,
                "centroid_longitude_wgs84": 103.8,
            }
        ]
        nodes = [{"commercial_node_id": "N1", "node_name": "NODE", "station_complex_id": "S1"}]
        exits = [
            {
                "station_complex_id": "S1",
                "transit_point_id": "E1",
                "exit_label_official": "Exit A",
                "easting_3414": 3,
                "northing_3414": 4,
                "latitude_wgs84": 1.31,
                "longitude_wgs84": 103.81,
            }
        ]
        scenarios = [
            {"scenario_id": "weekday", "journey_timestamp": "2026-09-16T16:00:00+08:00", "pt_threshold_minutes": 20, "walking_threshold_minutes": 10, "proximity_fallback_metres": 800},
            {"scenario_id": "weekend", "journey_timestamp": "2026-09-19T10:00:00+08:00", "pt_threshold_minutes": 20, "walking_threshold_minutes": 10, "proximity_fallback_metres": 800},
        ]
        rows = build_routing_plan(origins, {"G1": 100}, nodes, exits, scenarios, max_walk_distance_metres=1000, num_itineraries=1)
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["scenario_id"] for row in rows}, {"weekday", "weekend"})
        self.assertTrue(all(row["nearest_exit_straight_line_distance_metres"] == 5 for row in rows))
        self.assertTrue(all("http_status" not in row for row in rows))

    def test_request_id_changes_when_max_walk_distance_changes(self) -> None:
        origins = [
            {
                "geo_id": "G1",
                "subzone_name": "ONE",
                "planning_area_name": "P",
                "region_name": "R",
                "centroid_easting_3414": 0,
                "centroid_northing_3414": 0,
                "centroid_latitude_wgs84": 1.3,
                "centroid_longitude_wgs84": 103.8,
            }
        ]
        nodes = [{"commercial_node_id": "N1", "node_name": "NODE", "station_complex_id": "S1"}]
        exits = [
            {
                "station_complex_id": "S1",
                "transit_point_id": "E1",
                "exit_label_official": "Exit A",
                "easting_3414": 3,
                "northing_3414": 4,
                "latitude_wgs84": 1.31,
                "longitude_wgs84": 103.81,
            }
        ]
        scenarios = [
            {"scenario_id": "weekday", "journey_timestamp": "2026-09-16T16:00:00+08:00", "pt_threshold_minutes": 20, "walking_threshold_minutes": 10, "proximity_fallback_metres": 800}
        ]
        row_500 = build_routing_plan(origins, {"G1": 100}, nodes, exits, scenarios, max_walk_distance_metres=500, num_itineraries=1)[0]
        row_1000 = build_routing_plan(origins, {"G1": 100}, nodes, exits, scenarios, max_walk_distance_metres=1000, num_itineraries=1)[0]
        self.assertNotEqual(row_500["od_plan_id"], row_1000["od_plan_id"])


class RoutingPlanConfigTests(unittest.TestCase):
    def test_chunked_national_execution_is_authorised_and_private_material_is_prohibited(self) -> None:
        config = json.loads((REPO_ROOT / "config/accessibility/national_routing_plan.json").read_text(encoding="utf-8"))
        self.assertEqual(config["execution_status"], "approved_for_national_execution")
        self.assertEqual(config["primary_max_walk_distance_metres"], 500)
        self.assertEqual(config["bounded_comparison_walk_distances_metres"], [300, 500, 1000])
        self.assertTrue(config["bounded_sample_authorised"])
        self.assertTrue(config["national_execution_authorised"])
        self.assertEqual(config["approved_chunk_request_limit"], 5000)
        self.assertEqual(config["execution_pace_seconds"], 0.25)
        self.assertEqual(config["concurrent_request_workers"], 6)
        boundary = config["persistence_boundary"].lower()
        for term in ("credentials", "token", "request headers", "raw route response"):
            self.assertIn(term, boundary)


if __name__ == "__main__":
    unittest.main()
