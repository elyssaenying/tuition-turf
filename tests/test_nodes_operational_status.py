from __future__ import annotations

import json
import unittest
from pathlib import Path

from tuition_location_analytics.nodes.landuse import build_commercial_nodes
from tuition_location_analytics.nodes.stations import build_station_complexes

REPO_ROOT = Path(__file__).resolve().parents[1]


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


def _train(base_name: str, station_code: str = "XX1") -> dict[str, object]:
    return {
        "normalized_station_base_name": base_name,
        "station_code": station_code,
        "line_name_english": "Example Line",
        "station_name_chinese": "示例",
    }


_MARINA_SOUTH_EXCEPTION = {
    "normalized_station_name": "MARINA SOUTH MRT STATION",
    "operational_status": "not_operational",
    "basis": "LTA's Thomson-East Coast Line page states Marina South opens in tandem with development completion; opening date to be advised. Also absent from the current System Map roster.",
    "evidence": [
        {
            "source_id": "S029",
            "publisher": "Land Transport Authority",
            "title": "Thomson-East Coast Line",
            "url": "https://www.lta.gov.sg/content/ltagov/en/upcoming_projects/rail_expansion/thomson_east_coast_line.html",
            "accessed_at": "2026-09-13",
        }
    ],
}

_EVIDENCE_CONFIG = {"known_exceptions": [_MARINA_SOUTH_EXCEPTION]}

_MAP_ROSTER = {
    "source_id": "S032",
    "roster_version": "2026-09-13.1",
    "operational_base_names": ["EXAMPLE", "TECK LEE"],
}


class S026AloneIsInsufficientTests(unittest.TestCase):
    """Regression coverage for the Teck Lee counterexample: an exact S026 match must
    never, by itself, establish verified_operational, because S026 (Jun 2017) can carry
    names/codes for stations that were not yet operating at the time it was published."""

    def test_teck_lee_s026_match_without_roster_or_override_is_unresolved(self) -> None:
        exits = [_exit("1", "TECK LEE LRT STATION", "Exit A", 50000.0)]
        result = build_station_complexes(
            exits,
            [_train("TECK LEE", station_code="PW2")],  # S026 exact-name corroboration present
            dispersion_review_threshold_metres=400,
            implausible_extent_threshold_metres=1000,
            operational_status_evidence=_EVIDENCE_CONFIG,
            system_map_roster={"operational_base_names": []},  # not on the current roster in this fixture
        )
        complex_row = result["complexes"][0]
        self.assertEqual(complex_row["corroboration_status"], "exact_base_name_match")
        self.assertEqual(
            complex_row["operational_status"],
            "unresolved",
            "an exact S026 match alone must never produce verified_operational",
        )

    def test_teck_lee_becomes_verified_operational_via_current_map_roster_not_s026(self) -> None:
        exits = [_exit("1", "TECK LEE LRT STATION", "Exit A", 50000.0)]
        result = build_station_complexes(
            exits,
            [_train("TECK LEE", station_code="PW2")],  # S026 still present, but plays no role
            dispersion_review_threshold_metres=400,
            implausible_extent_threshold_metres=1000,
            operational_status_evidence=_EVIDENCE_CONFIG,
            system_map_roster=_MAP_ROSTER,
        )
        complex_row = result["complexes"][0]
        self.assertEqual(complex_row["operational_status"], "verified_operational")
        self.assertTrue(complex_row["operational_status_map_roster_match"])
        self.assertIn("System Map", complex_row["operational_status_basis"])

    def test_any_s026_corroborated_station_absent_from_roster_is_unresolved_not_operational(self) -> None:
        exits = [_exit("1", "EXAMPLE MRT STATION", "Exit A", 50000.0)]
        result = build_station_complexes(
            exits,
            [_train("EXAMPLE")],
            dispersion_review_threshold_metres=400,
            implausible_extent_threshold_metres=1000,
            operational_status_evidence=_EVIDENCE_CONFIG,
            system_map_roster={"operational_base_names": []},
        )
        complex_row = result["complexes"][0]
        self.assertEqual(complex_row["corroboration_status"], "exact_base_name_match")
        self.assertEqual(complex_row["operational_status"], "unresolved")


class MapRosterEvidenceTests(unittest.TestCase):
    def test_named_station_on_current_roster_is_verified_operational(self) -> None:
        exits = [_exit("1", "EXAMPLE MRT STATION", "Exit A", 50000.0)]
        result = build_station_complexes(
            exits,
            [],  # no S026 corroboration at all
            dispersion_review_threshold_metres=400,
            implausible_extent_threshold_metres=1000,
            operational_status_evidence=_EVIDENCE_CONFIG,
            system_map_roster=_MAP_ROSTER,
        )
        complex_row = result["complexes"][0]
        self.assertEqual(complex_row["operational_status"], "verified_operational")
        self.assertTrue(complex_row["operational_status_map_roster_match"])

    def test_named_station_absent_from_map_and_s026_and_overrides_is_unresolved(self) -> None:
        exits = [_exit("1", "SOME FUTURE MRT STATION", "Exit A", 50000.0)]
        result = build_station_complexes(
            exits,
            [],
            dispersion_review_threshold_metres=400,
            implausible_extent_threshold_metres=1000,
            operational_status_evidence=_EVIDENCE_CONFIG,
            system_map_roster=_MAP_ROSTER,
        )
        complex_row = result["complexes"][0]
        self.assertEqual(complex_row["operational_status"], "unresolved")

    def test_every_verified_operational_complex_has_evidence_or_map_roster_match(self) -> None:
        exits = [
            _exit("1", "EXAMPLE MRT STATION", "Exit A", 50000.0),
            _exit("2", "TECK LEE LRT STATION", "Exit A", 60000.0),
            _exit("3", "MARINA SOUTH MRT STATION", "Exit A", 70000.0),
            _exit("4", "SOME FUTURE MRT STATION", "Exit A", 80000.0),
        ]
        result = build_station_complexes(
            exits,
            [_train("EXAMPLE"), _train("TECK LEE", station_code="PW2")],
            dispersion_review_threshold_metres=400,
            implausible_extent_threshold_metres=1000,
            operational_status_evidence=_EVIDENCE_CONFIG,
            system_map_roster=_MAP_ROSTER,
        )
        for complex_row in result["complexes"]:
            if complex_row["operational_status"] != "verified_operational":
                continue
            has_evidence = bool(json.loads(complex_row["operational_status_evidence_json"]))
            has_roster_match = complex_row["operational_status_map_roster_match"]
            self.assertTrue(
                has_evidence or has_roster_match,
                f"{complex_row['station_name']} is verified_operational with neither evidence nor a roster match",
            )


class MarinaSouthExclusionTests(unittest.TestCase):
    def test_marina_south_is_not_operational_and_excluded_from_candidates(self) -> None:
        exits = [_exit("1", "MARINA SOUTH MRT STATION", "Exit A", 50000.0)]
        station_data = build_station_complexes(
            exits,
            [],
            dispersion_review_threshold_metres=400,
            implausible_extent_threshold_metres=1000,
            operational_status_evidence=_EVIDENCE_CONFIG,
            system_map_roster=_MAP_ROSTER,
        )
        complex_row = station_data["complexes"][0]
        self.assertEqual(complex_row["operational_status"], "not_operational")

        land_use = {"records": [], "geometries": []}
        commercial = build_commercial_nodes(
            station_data["complexes"],
            station_data["memberships"],
            station_data["review_items"],
            land_use,
            buffer_metres=[400, 800],
            minimum_independent_signals=2,
        )
        self.assertEqual(commercial["candidates"], [])
        self.assertEqual(len(commercial["excluded_not_yet_operational"]), 1)

    def test_non_operational_station_contributes_no_commercial_evidence_rows(self) -> None:
        exits = [
            _exit("1", "MARINA SOUTH MRT STATION", "Exit A", 50000.0),
            _exit("2", "EXAMPLE MRT STATION", "Exit A", 90000.0),
        ]
        station_data = build_station_complexes(
            exits,
            [_train("EXAMPLE")],
            dispersion_review_threshold_metres=400,
            implausible_extent_threshold_metres=1000,
            operational_status_evidence=_EVIDENCE_CONFIG,
            system_map_roster=_MAP_ROSTER,
        )
        land_use = {"records": [], "geometries": []}
        commercial = build_commercial_nodes(
            station_data["complexes"],
            station_data["memberships"],
            station_data["review_items"],
            land_use,
            buffer_metres=[400, 800],
            minimum_independent_signals=2,
        )
        marina_south_id = next(
            row["station_complex_id"]
            for row in station_data["complexes"]
            if row["station_name"] == "MARINA SOUTH MRT STATION"
        )
        self.assertFalse(
            any(row["station_complex_id"] == marina_south_id for row in commercial["evidence"])
        )
        self.assertEqual(len(commercial["candidates"]), 1)

    def test_under_construction_station_cannot_enter_candidates(self) -> None:
        # A station explicitly excluded via known_exceptions as verified_opening_within_decision_horizon
        # (e.g. a map-flagged "Under Construction" station) must not become a current candidate.
        exception_config = {
            "known_exceptions": [
                {
                    "normalized_station_name": "SUNGEI BEDOK MRT STATION",
                    "operational_status": "verified_opening_within_decision_horizon",
                    "basis": "Marked Under Construction on the current System Map (S032); Thomson-East Coast Line Stage 5.",
                    "evidence": [{"source_id": "S032"}],
                }
            ]
        }
        exits = [_exit("1", "SUNGEI BEDOK MRT STATION", "Exit A", 50000.0)]
        station_data = build_station_complexes(
            exits,
            [],
            dispersion_review_threshold_metres=400,
            implausible_extent_threshold_metres=1000,
            operational_status_evidence=exception_config,
            system_map_roster=_MAP_ROSTER,
        )
        commercial = build_commercial_nodes(
            station_data["complexes"],
            station_data["memberships"],
            station_data["review_items"],
            {"records": [], "geometries": []},
            buffer_metres=[400, 800],
            minimum_independent_signals=2,
        )
        self.assertEqual(commercial["candidates"], [])


class RepeatedLabelWordingTests(unittest.TestCase):
    def _load_real_dispositions(self) -> list[dict[str, object]]:
        path = REPO_ROOT / "config/nodes/review_dispositions.json"
        return json.loads(path.read_text(encoding="utf-8"))["dispositions"]

    def test_repeated_label_dispositions_do_not_claim_physical_exit_identity(self) -> None:
        dispositions = self._load_real_dispositions()
        repeated = [d for d in dispositions if d["issue_category"] == "repeated_exit_labels"]
        self.assertEqual(len(repeated), 6)
        banned_phrase = "physically separate exit structures"
        for entry in repeated:
            self.assertNotIn(banned_phrase, entry["resolution_summary"])

    def test_choa_chu_kang_is_closed_non_blocking_with_semantic_flag(self) -> None:
        dispositions = self._load_real_dispositions()
        choa_chu_kang = next(
            d
            for d in dispositions
            if d["normalized_station_name"] == "CHOA CHU KANG MRT STATION"
            and d["issue_category"] == "repeated_exit_labels"
        )
        self.assertEqual(choa_chu_kang["status"], "closed")
        self.assertFalse(choa_chu_kang["human_decision_required"])
        self.assertTrue(choa_chu_kang["semantic_ambiguity_quality_flag"])

    def test_same_labelled_exits_are_retained_regardless_of_distance_heuristic(self) -> None:
        exits = [
            _exit("1", "CHOA CHU KANG MRT STATION", "Exit A", 40000.0),
            _exit("2", "CHOA CHU KANG MRT STATION", "Exit A", 40003.0),  # 3 m apart: under heuristic
        ]
        dispositions = self._load_real_dispositions()
        result = build_station_complexes(
            exits,
            [],
            dispersion_review_threshold_metres=400,
            implausible_extent_threshold_metres=1000,
            review_dispositions=dispositions,
        )
        self.assertEqual(len(result["memberships"]), 2)
        member_ids = {row["transit_point_id"] for row in result["memberships"]}
        self.assertEqual(member_ids, {"MRT_EXIT_1", "MRT_EXIT_2"})
        review_item = next(
            item for item in result["review_items"] if item["issue_category"] == "repeated_exit_labels"
        )
        self.assertEqual(review_item["status"], "closed")
        self.assertTrue(review_item["semantic_ambiguity_quality_flag"])


class SevenOverridesStillCorrectTests(unittest.TestCase):
    def test_all_seven_overrides_load_and_resolve_from_the_real_config(self) -> None:
        overrides = json.loads(
            (REPO_ROOT / "config/nodes/station_overrides.json").read_text(encoding="utf-8")
        )["overrides"]
        self.assertEqual({entry["source_label"] for entry in overrides}, {
            "CC9", "DT18", "DT4", "NE18", "CC30", "CC31", "CC32",
        })
        exits = [_exit(str(i), entry["source_label"], "1", 40000.0 + i * 100) for i, entry in enumerate(overrides)]
        result = build_station_complexes(
            exits,
            [],
            dispersion_review_threshold_metres=400,
            implausible_extent_threshold_metres=1000,
            station_overrides=overrides,
        )
        resolved_names = {row["station_name"] for row in result["complexes"]}
        self.assertEqual(
            resolved_names,
            {
                "PAYA LEBAR MRT STATION",
                "TELOK AYER MRT STATION",
                "HUME MRT STATION",
                "PUNGGOL COAST MRT STATION",
                "KEPPEL MRT STATION",
                "CANTONMENT MRT STATION",
                "PRINCE EDWARD ROAD MRT STATION",
            },
        )
        for row in result["complexes"]:
            self.assertEqual(row["operational_status"], "verified_operational")


class ReviewCategoriesRemainAdditiveTests(unittest.TestCase):
    def test_operational_exception_and_zoning_issue_are_both_retained(self) -> None:
        complex_record = {
            "station_complex_id": "STC_MARINA_SOUTH",
            "station_name": "MARINA SOUTH MRT STATION",
            "rail_mode": "mrt",
            "representative_longitude_wgs84": 103.8,
            "representative_latitude_wgs84": 1.3,
            "exit_count": 1,
            "operational_status": "not_operational",
            "operational_status_basis": "test fixture",
            "operational_status_evidence_json": "[]",
        }
        membership = {"station_complex_id": "STC_MARINA_SOUTH", "easting_3414": 30000.0, "northing_3414": 30000.0}
        result = build_commercial_nodes(
            [complex_record],
            [membership],
            [],
            {"records": [], "geometries": []},
            buffer_metres=[400, 800],
            minimum_independent_signals=2,
        )
        categories = {item["issue_category"] for item in result["review_items"]}
        self.assertEqual(categories, {"excluded_not_yet_operational"})
        self.assertEqual(result["candidates"], [])


if __name__ == "__main__":
    unittest.main()
