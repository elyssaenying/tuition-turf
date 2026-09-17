from __future__ import annotations

import unittest

from tuition_location_analytics.nodes.landuse import build_commercial_nodes
from tuition_location_analytics.nodes.stations import build_station_complexes, station_complex_id


def _exit(exit_id: str, station: str, label: str, easting: float, northing: float = 30000.0) -> dict[str, object]:
    return {
        "transit_point_id": f"MRT_EXIT_{exit_id}",
        "source_unique_id": exit_id,
        "station_name": station,
        "exit_code": label,
        "longitude_wgs84": 103.8 + easting / 100000,
        "latitude_wgs84": 1.3 + northing / 100000,
        "easting_3414": easting,
        "northing_3414": northing,
    }


_MERGE_OVERRIDE = {
    "source_label": "CC9",
    "normalized_source_label": "CC9",
    "resolution": "merge_into_existing_named_complex",
    "target_normalized_station_name": "PAYA LEBAR MRT STATION",
    "target_rail_mode": "mrt",
    "rationale": "CC9 is the official Circle Line code for the existing Paya Lebar interchange.",
    "operational_status": "verified_operational",
    "operational_status_basis": "Official LTA Circle Line page.",
    "evidence": [{"publisher": "LTA", "url": "https://example.gov.sg/circle-line", "accessed_at": "2026-09-13"}],
    "override_config_version": "test-v1",
}

_RENAME_OVERRIDE = {
    "source_label": "DT4",
    "normalized_source_label": "DT4",
    "resolution": "rename_separate_station",
    "target_normalized_station_name": "HUME MRT STATION",
    "target_rail_mode": "mrt",
    "rationale": "DT4 is the official Downtown Line code for Hume MRT Station.",
    "operational_status": "verified_operational",
    "operational_status_basis": "Official LTA press release, opened 28 Feb 2025.",
    "evidence": [{"publisher": "LTA", "url": "https://example.gov.sg/hume", "accessed_at": "2026-09-13"}],
    "override_config_version": "test-v1",
}


class StationOverrideTests(unittest.TestCase):
    def test_merge_override_joins_existing_complex_without_ambiguous_or_collision_flags(self) -> None:
        exits = [
            _exit("1", "PAYA LEBAR MRT STATION", "Exit A", 20000.0),
            _exit("2", "PAYA LEBAR MRT STATION", "Exit B", 20010.0),
            _exit("3", "CC9", "Exit E", 20020.0),
        ]
        result = build_station_complexes(
            exits,
            [],
            dispersion_review_threshold_metres=400,
            implausible_extent_threshold_metres=1000,
            station_overrides=[_MERGE_OVERRIDE],
        )
        self.assertEqual(len(result["complexes"]), 1)
        complex_row = result["complexes"][0]
        self.assertEqual(complex_row["station_name"], "PAYA LEBAR MRT STATION")
        self.assertEqual(complex_row["exit_count"], 3)
        self.assertEqual(complex_row["operational_status"], "verified_operational")
        self.assertNotIn("ambiguous_station_name", complex_row["review_flags_json"])
        self.assertNotIn("normalized_name_collision", complex_row["review_flags_json"])
        self.assertEqual(
            complex_row["station_complex_id"], station_complex_id("PAYA LEBAR MRT STATION")
        )
        # All three source exits remain present and individually addressable.
        member_ids = {row["transit_point_id"] for row in result["memberships"]}
        self.assertEqual(member_ids, {"MRT_EXIT_1", "MRT_EXIT_2", "MRT_EXIT_3"})
        self.assertEqual(len(result["station_complex_id_crosswalk"]), 1)
        crosswalk_row = result["station_complex_id_crosswalk"][0]
        self.assertEqual(crosswalk_row["previous_normalized_station_name"], "CC9")
        self.assertEqual(crosswalk_row["new_station_complex_id"], complex_row["station_complex_id"])
        self.assertTrue(crosswalk_row["merged_into_pre_existing_complex"])
        self.assertFalse(
            any(item["issue_category"] == "ambiguous_station_name" for item in result["review_items"])
        )

    def test_rename_override_creates_new_named_station_without_pre_existing_group(self) -> None:
        exits = [
            _exit("10", "DT4", "1", 40000.0),
            _exit("11", "DT4", "2", 40005.0),
        ]
        result = build_station_complexes(
            exits,
            [],
            dispersion_review_threshold_metres=400,
            implausible_extent_threshold_metres=1000,
            station_overrides=[_RENAME_OVERRIDE],
        )
        self.assertEqual(len(result["complexes"]), 1)
        complex_row = result["complexes"][0]
        self.assertEqual(complex_row["station_name"], "HUME MRT STATION")
        self.assertEqual(complex_row["rail_mode"], "mrt")
        self.assertEqual(complex_row["operational_status"], "verified_operational")
        self.assertNotIn("ambiguous_station_name", complex_row["review_flags_json"])
        crosswalk_row = result["station_complex_id_crosswalk"][0]
        self.assertFalse(crosswalk_row["merged_into_pre_existing_complex"])
        self.assertEqual(crosswalk_row["previous_normalized_station_name"], "DT4")

    def test_unregistered_code_only_station_stays_ambiguous_and_unresolved(self) -> None:
        exits = [_exit("20", "ZZ9", "1", 60000.0), _exit("21", "ZZ9", "2", 60005.0)]
        result = build_station_complexes(
            exits,
            [],
            dispersion_review_threshold_metres=400,
            implausible_extent_threshold_metres=1000,
            station_overrides=[],
        )
        complex_row = result["complexes"][0]
        self.assertEqual(complex_row["operational_status"], "unresolved")
        self.assertIn("ambiguous_station_name", complex_row["review_flags_json"])
        self.assertEqual(result["station_complex_id_crosswalk"], [])

    def test_crosswalk_has_one_row_per_resolved_station_not_per_exit(self) -> None:
        exits = [
            _exit("10", "DT4", "1", 40000.0),
            _exit("11", "DT4", "2", 40005.0),
            _exit("12", "DT4", "3", 40010.0),
        ]
        result = build_station_complexes(
            exits,
            [],
            dispersion_review_threshold_metres=400,
            implausible_extent_threshold_metres=1000,
            station_overrides=[_RENAME_OVERRIDE],
        )
        self.assertEqual(len(result["station_complex_id_crosswalk"]), 1)

    def test_all_source_exits_preserved_exactly_once_across_mixed_overrides(self) -> None:
        exits = [
            _exit("1", "PAYA LEBAR MRT STATION", "Exit A", 20000.0),
            _exit("3", "CC9", "Exit E", 20020.0),
            _exit("10", "DT4", "1", 40000.0),
            _exit("30", "SOME OTHER MRT STATION", "Exit A", 80000.0),
        ]
        result = build_station_complexes(
            exits,
            [],
            dispersion_review_threshold_metres=400,
            implausible_extent_threshold_metres=1000,
            station_overrides=[_MERGE_OVERRIDE, _RENAME_OVERRIDE],
        )
        input_ids = {row["transit_point_id"] for row in exits}
        member_ids = [row["transit_point_id"] for row in result["memberships"]]
        self.assertEqual(len(member_ids), len(exits))
        self.assertEqual(set(member_ids), input_ids)
        self.assertEqual(len(member_ids), len(set(member_ids)))


class ReviewQueueCompletenessRegressionTests(unittest.TestCase):
    """Regression coverage for the suppressed no_commercial_zoning_signal issue (DT4 case)."""

    def _land_use_with_no_relevant_feature(self) -> dict[str, object]:
        return {"records": [], "geometries": []}

    def test_existing_station_issue_no_longer_suppresses_zoning_issue(self) -> None:
        complex_record = {
            "station_complex_id": "STC_AMBIGUOUS",
            "station_name": "ZZ9",
            "rail_mode": "mrt_code_only_unverified",
            "representative_longitude_wgs84": 103.8,
            "representative_latitude_wgs84": 1.3,
            "exit_count": 1,
            "operational_status": "unresolved",
            "operational_status_basis": "test fixture",
            "operational_status_evidence_json": "[]",
        }
        membership = {"station_complex_id": "STC_AMBIGUOUS", "easting_3414": 30000.0, "northing_3414": 30000.0}
        pre_existing_station_issue = {
            "review_item_id": "REV_PRIOR",
            "station_complex_id": "STC_AMBIGUOUS",
            "commercial_node_id": None,
            "issue_category": "ambiguous_station_name",
            "relevant_values": "ZZ9",
            "evidence_refs_json": "[]",
            "suggested_resolution": "resolve",
            "human_decision_required": "confirm",
            "status": "open",
            "resolution_summary": None,
        }
        result = build_commercial_nodes(
            [complex_record],
            [membership],
            [pre_existing_station_issue],
            self._land_use_with_no_relevant_feature(),
            buffer_metres=[400, 800],
            minimum_independent_signals=2,
        )
        categories = {item["issue_category"] for item in result["review_items"]}
        self.assertIn("ambiguous_station_name", categories)
        self.assertIn("no_commercial_zoning_signal", categories)
        self.assertIn("unresolved_operational_status", categories)
        self.assertEqual(len(categories), 3)
        self.assertEqual(result["candidates"][0]["qualification_status"], "needs_manual_review")

    def test_identical_complex_and_category_pairs_are_deduplicated(self) -> None:
        complex_record = {
            "station_complex_id": "STC_DUP",
            "station_name": "Example MRT Station",
            "rail_mode": "mrt",
            "representative_longitude_wgs84": 103.8,
            "representative_latitude_wgs84": 1.3,
            "exit_count": 1,
            "operational_status": "verified_operational",
            "operational_status_basis": "test fixture",
            "operational_status_evidence_json": "[]",
        }
        membership = {"station_complex_id": "STC_DUP", "easting_3414": 30000.0, "northing_3414": 30000.0}
        duplicate_items = [
            {
                "review_item_id": "REV_A",
                "station_complex_id": "STC_DUP",
                "commercial_node_id": None,
                "issue_category": "unusually_dispersed",
                "relevant_values": "first",
                "evidence_refs_json": "[]",
                "suggested_resolution": "x",
                "human_decision_required": "y",
                "status": "open",
                "resolution_summary": None,
            },
            {
                "review_item_id": "REV_B",
                "station_complex_id": "STC_DUP",
                "commercial_node_id": None,
                "issue_category": "unusually_dispersed",
                "relevant_values": "duplicate",
                "evidence_refs_json": "[]",
                "suggested_resolution": "x",
                "human_decision_required": "y",
                "status": "open",
                "resolution_summary": None,
            },
        ]
        result = build_commercial_nodes(
            [complex_record],
            [membership],
            duplicate_items,
            self._land_use_with_no_relevant_feature(),
            buffer_metres=[400, 800],
            minimum_independent_signals=2,
        )
        dispersed_items = [
            item for item in result["review_items"] if item["issue_category"] == "unusually_dispersed"
        ]
        self.assertEqual(len(dispersed_items), 1)

    def test_verified_opening_within_decision_horizon_is_excluded_from_candidates(self) -> None:
        complex_record = {
            "station_complex_id": "STC_FUTURE",
            "station_name": "Future MRT Station",
            "rail_mode": "mrt",
            "representative_longitude_wgs84": 103.8,
            "representative_latitude_wgs84": 1.3,
            "exit_count": 1,
            "operational_status": "verified_opening_within_decision_horizon",
            "operational_status_basis": "test fixture",
            "operational_status_evidence_json": "[]",
        }
        membership = {"station_complex_id": "STC_FUTURE", "easting_3414": 30000.0, "northing_3414": 30000.0}
        result = build_commercial_nodes(
            [complex_record],
            [membership],
            [],
            self._land_use_with_no_relevant_feature(),
            buffer_metres=[400, 800],
            minimum_independent_signals=2,
        )
        self.assertEqual(result["candidates"], [])
        self.assertEqual(len(result["excluded_not_yet_operational"]), 1)
        self.assertTrue(
            any(item["issue_category"] == "excluded_not_yet_operational" for item in result["review_items"])
        )


if __name__ == "__main__":
    unittest.main()
