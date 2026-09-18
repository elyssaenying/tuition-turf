from __future__ import annotations

import unittest

from tuition_location_analytics.competitors.walking_catchment import (
    build_walk_requests,
    summarise_memberships,
)


class WalkingCatchmentTests(unittest.TestCase):
    def test_same_building_branches_share_route_requests_but_get_separate_memberships(self) -> None:
        branches = [
            {"branch_id": "B1", "longitude_wgs84": 103.8, "latitude_wgs84": 1.3},
            {"branch_id": "B2", "longitude_wgs84": 103.8, "latitude_wgs84": 1.3},
        ]
        exits = [
            {
                "station_complex_id": "S1",
                "transit_point_id": "E1",
                "longitude_wgs84": 103.79,
                "latitude_wgs84": 1.29,
            }
        ]
        nodes = [{"station_complex_id": "S1", "commercial_node_id": "N1"}]
        requests, coordinate_branches = build_walk_requests(branches, exits, nodes)
        self.assertEqual(len(requests), 1)
        outcomes = {
            requests[0]["od_plan_id"]: {
                "category": "success",
                "duration_seconds": 540,
                "distance_metres": 700,
            }
        }
        memberships = summarise_memberships(requests, outcomes, coordinate_branches)
        self.assertEqual([row["branch_id"] for row in memberships], ["B1", "B2"])
        self.assertTrue(all(row["inside_10_minute_walk"] for row in memberships))

    def test_fastest_preserved_exit_defines_membership(self) -> None:
        branches = [{"branch_id": "B1", "longitude_wgs84": 103.8, "latitude_wgs84": 1.3}]
        exits = [
            {"station_complex_id": "S1", "transit_point_id": "E1", "longitude_wgs84": 103.79, "latitude_wgs84": 1.29},
            {"station_complex_id": "S1", "transit_point_id": "E2", "longitude_wgs84": 103.78, "latitude_wgs84": 1.28},
        ]
        nodes = [{"station_complex_id": "S1", "commercial_node_id": "N1"}]
        requests, coordinate_branches = build_walk_requests(branches, exits, nodes)
        outcomes = {
            requests[0]["od_plan_id"]: {"category": "success", "duration_seconds": 950, "distance_metres": 1200},
            requests[1]["od_plan_id"]: {"category": "success", "duration_seconds": 700, "distance_metres": 900},
        }
        membership = summarise_memberships(requests, outcomes, coordinate_branches)[0]
        self.assertEqual(membership["minimum_walk_duration_seconds"], 700)
        self.assertFalse(membership["inside_10_minute_walk"])
        self.assertTrue(membership["inside_15_minute_walk"])
        self.assertEqual(membership["best_exit_transit_point_id"], "E2")


if __name__ == "__main__":
    unittest.main()
