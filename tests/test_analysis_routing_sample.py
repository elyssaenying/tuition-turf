from __future__ import annotations

import unittest

from tuition_location_analytics.analysis.routing_sample import expand_walk_comparison, select_balanced_pairs


def source_row(index: int, distance: float) -> dict[str, object]:
    return {
        "od_plan_id": f"SOURCE_{index}",
        "origin_geo_id": f"G{index}",
        "origin_subzone_name": f"ORIGIN {index}",
        "commercial_node_id": f"N{index}",
        "node_name": f"NODE {index}",
        "destination_exit_id": f"E{index}",
        "scenario_id": "weekday",
        "journey_timestamp": "2026-09-16T16:00:00+08:00",
        "pt_mode": "TRANSIT",
        "num_itineraries": 1,
        "max_walk_distance_metres": 500,
        "nearest_exit_straight_line_distance_metres": distance,
    }


class RoutingSampleTests(unittest.TestCase):
    def test_balanced_selection_is_deterministic_and_expansion_ids_are_unique(self) -> None:
        rows = [source_row(index, distance) for index, distance in enumerate([100, 200, 300, 1200, 1400, 1600], start=1)]
        bands = [
            {"band_id": "near", "minimum": 0, "maximum_exclusive": 1000},
            {"band_id": "far", "minimum": 1000, "maximum_exclusive": None},
        ]
        first = select_balanced_pairs(rows, scenario_id="weekday", distance_bands=bands, pairs_per_band=2, seed="x")
        second = select_balanced_pairs(list(reversed(rows)), scenario_id="weekday", distance_bands=bands, pairs_per_band=2, seed="x")
        self.assertEqual([row["sample_pair_id"] for row in first], [row["sample_pair_id"] for row in second])
        self.assertEqual({row["sample_distance_band"] for row in first}, {"near", "far"})
        expanded = expand_walk_comparison(first, [300, 500, 1000])
        self.assertEqual(len(expanded), 12)
        self.assertEqual(len({row["od_plan_id"] for row in expanded}), 12)

    def test_insufficient_band_fails_instead_of_silently_shrinking(self) -> None:
        with self.assertRaises(RuntimeError):
            select_balanced_pairs(
                [source_row(1, 100)],
                scenario_id="weekday",
                distance_bands=[{"band_id": "near", "minimum": 0, "maximum_exclusive": 1000}],
                pairs_per_band=2,
                seed="x",
            )


if __name__ == "__main__":
    unittest.main()
