from __future__ import annotations

import json
import unittest
from pathlib import Path

from shapely.geometry import Point, box

from tuition_location_analytics.analysis.proximity import (
    METHOD,
    add_demand_ranks,
    area_weighted_population,
    exit_union_catchment,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class ProximityGeometryTests(unittest.TestCase):
    def test_exit_union_does_not_double_count_overlap(self) -> None:
        one = exit_union_catchment([Point(0, 0)], 100)
        duplicate = exit_union_catchment([Point(0, 0), Point(0, 0)], 100)
        self.assertAlmostEqual(one.area, duplicate.area)

    def test_requires_exit_and_positive_radius(self) -> None:
        with self.assertRaises(ValueError):
            exit_union_catchment([], 100)
        with self.assertRaises(ValueError):
            exit_union_catchment([Point(0, 0)], 0)

    def test_area_weighted_population_uses_overlap_share(self) -> None:
        subzones = [
            {"geometry_3414": box(0, 0, 10, 10), "target_population_proxy": 100},
            {"geometry_3414": box(10, 0, 20, 10), "target_population_proxy": 200},
        ]
        value, count = area_weighted_population(box(0, 0, 15, 10), subzones)
        self.assertAlmostEqual(value, 200.0)
        self.assertEqual(count, 2)


class ProximityRankingTests(unittest.TestCase):
    def test_ranking_is_deterministic_for_ties(self) -> None:
        records = [
            {"commercial_node_id": "B", "proximity_target_population_proxy_800m": 10.0},
            {"commercial_node_id": "A", "proximity_target_population_proxy_800m": 10.0},
            {"commercial_node_id": "C", "proximity_target_population_proxy_800m": 5.0},
        ]
        ranked = add_demand_ranks(records)
        self.assertEqual([row["commercial_node_id"] for row in ranked], ["A", "B", "C"])
        self.assertEqual([row["population_proxy_800m_rank"] for row in ranked], [1, 2, 3])


class ProximityConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(
            (REPO_ROOT / "config/analysis/proximity_baseline.json").read_text(encoding="utf-8")
        )

    def test_method_and_claim_boundary_are_explicit(self) -> None:
        self.assertEqual(self.config["method"], METHOD)
        self.assertEqual(self.config["proximity_radii_metres"], [800, 1200])
        boundary = self.config["claim_boundary"].lower()
        self.assertIn("not transit", boundary)
        self.assertIn("not", boundary)
        self.assertIn("ranking recommendation", boundary)

    def test_all_inputs_exist(self) -> None:
        for reference in self.config["inputs"].values():
            self.assertTrue((REPO_ROOT / reference).is_file(), reference)


if __name__ == "__main__":
    unittest.main()
