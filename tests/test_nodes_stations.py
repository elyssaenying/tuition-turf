from __future__ import annotations

import unittest

from tuition_location_analytics.nodes.stations import (
    build_station_complexes,
    station_complex_id,
)


def _exit(exit_id: str, station: str, label: str, easting: float) -> dict[str, object]:
    return {
        "transit_point_id": f"MRT_EXIT_{exit_id}",
        "source_unique_id": exit_id,
        "station_name": station,
        "exit_code": label,
        "longitude_wgs84": 103.8 + easting / 100000,
        "latitude_wgs84": 1.3,
        "easting_3414": easting,
        "northing_3414": 30000.0,
    }


class StationComplexTests(unittest.TestCase):
    def test_exact_grouping_preserves_exits_duplicate_labels_and_distances(self) -> None:
        exits = [
            _exit("1", "Example MRT Station", "Exit A", 20000.0),
            _exit("2", " EXAMPLE  MRT STATION ", "Exit A", 20003.0),
            _exit("3", "Example MRT Station", "Exit B", 20008.0),
            _exit("4", "Example East MRT Station", "Exit A", 21000.0),
        ]
        train = [
            {
                "normalized_station_base_name": "EXAMPLE",
                "station_code": "EX1",
                "line_name_english": "Example Line",
                "station_name_chinese": "示例",
            }
        ]
        result = build_station_complexes(
            exits,
            train,
            dispersion_review_threshold_metres=400,
            implausible_extent_threshold_metres=1000,
        )
        self.assertEqual(len(result["complexes"]), 2)
        self.assertEqual(len(result["memberships"]), 4)
        example = next(
            row for row in result["complexes"] if row["normalized_station_name"] == "EXAMPLE MRT STATION"
        )
        self.assertEqual(example["station_complex_id"], station_complex_id("EXAMPLE MRT STATION"))
        self.assertEqual(example["exit_count"], 3)
        self.assertEqual(example["representative_exit_id"], "MRT_EXIT_2")
        self.assertAlmostEqual(example["maximum_pairwise_exit_distance_metres"], 8.0)
        self.assertTrue(example["has_duplicate_exit_labels"])
        self.assertEqual(example["corroboration_status"], "exact_base_name_match")
        self.assertEqual(result["quality"]["duplicate_membership_exit_ids"], [])
        self.assertEqual(result["quality"]["missing_membership_exit_ids"], [])
        self.assertEqual(result["quality"]["s026_unmatched_complex_count"], 1)

    def test_stable_id_depends_only_on_exact_normalized_station_name(self) -> None:
        self.assertEqual(
            station_complex_id("EXAMPLE MRT STATION"),
            station_complex_id("EXAMPLE MRT STATION"),
        )
        self.assertNotEqual(
            station_complex_id("EXAMPLE MRT STATION"),
            station_complex_id("EXAMPLE EAST MRT STATION"),
        )


if __name__ == "__main__":
    unittest.main()
