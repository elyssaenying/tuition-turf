from __future__ import annotations

import unittest

from tuition_location_analytics.competitors.pilot_selection import (
    compute_national_quartile,
    select_pilot_planning_areas,
)


def _geo(code: str, region: str, name: str | None = None) -> dict[str, object]:
    return {"planning_area_code": code, "planning_area_name": name or code.title(), "region_name": region}


def _pop(code: str, value: float) -> dict[str, object]:
    return {"planning_area_code": code, "accessible_target_population_proxy": value}


class PilotSelectionTests(unittest.TestCase):
    def _fixture(self):
        geography = [
            _geo("A1", "REGION ONE", "Area A1"),
            _geo("A2", "REGION ONE", "Area A2"),
            _geo("A3", "REGION ONE", "Area A3"),
            _geo("B1", "REGION TWO", "Area B1"),
            _geo("B2", "REGION TWO", "Area B2"),
        ]
        population = [
            _pop("A1", 1000),
            _pop("A2", 500),
            _pop("A3", 100),
            _pop("B1", 2000),
            _pop("B2", 50),
        ]
        return geography, population

    def test_selects_exactly_two_per_region(self) -> None:
        geography, population = self._fixture()
        result = select_pilot_planning_areas(
            geography, population, per_region_picks=2, mandated_code="A3"
        )
        self.assertEqual(len(result["selected"]), 4)
        by_region: dict[str, int] = {}
        for row in result["selected"]:
            by_region[row["region_name"]] = by_region.get(row["region_name"], 0) + 1
        self.assertEqual(by_region, {"REGION ONE": 2, "REGION TWO": 2})

    def test_mandated_code_always_included(self) -> None:
        geography, population = self._fixture()
        result = select_pilot_planning_areas(geography, population, mandated_code="A3")
        codes = {row["planning_area_code"] for row in result["selected"]}
        self.assertIn("A3", codes)
        mandated_row = next(row for row in result["selected"] if row["planning_area_code"] == "A3")
        self.assertEqual(mandated_row["selection_reason"], "mandated_no_commercial_zoning_signal_stress_test")

    def test_top_population_pick_per_non_mandated_region(self) -> None:
        geography, population = self._fixture()
        result = select_pilot_planning_areas(geography, population, mandated_code="A3")
        region_two_codes = {row["planning_area_code"] for row in result["selected"] if row["region_name"] == "REGION TWO"}
        self.assertIn("B1", region_two_codes)  # highest population in REGION TWO

    def test_output_field_is_planning_area_named_not_accessible(self) -> None:
        # No catchment/accessibility calculation has been performed at pilot-selection
        # time, so the output field must not reuse the foundation's accessibility-named
        # field; it must be explicitly planning-area scoped.
        geography, population = self._fixture()
        result = select_pilot_planning_areas(geography, population, mandated_code="A3")
        for row in result["selected"]:
            self.assertIn("planning_area_target_population_proxy", row)
            self.assertNotIn("accessible_target_population_proxy", row)

    def test_deterministic_across_repeated_calls(self) -> None:
        geography, population = self._fixture()
        first = select_pilot_planning_areas(geography, population, mandated_code="A3")
        second = select_pilot_planning_areas(geography, population, mandated_code="A3")
        self.assertEqual(first["selected"], second["selected"])

    def test_planning_area_count_is_derived_not_hardcoded(self) -> None:
        geography, population = self._fixture()
        result = select_pilot_planning_areas(geography, population, mandated_code="A3")
        self.assertEqual(result["total_planning_areas_in_geography_data"], len(geography))

    def test_missing_mandated_code_raises(self) -> None:
        geography, population = self._fixture()
        with self.assertRaises(RuntimeError):
            select_pilot_planning_areas(geography, population, mandated_code="ZZ")

    def test_quartile_boundaries_are_rank_based(self) -> None:
        codes = ["A", "B", "C", "D"]
        pop = {"A": 10, "B": 20, "C": 30, "D": 40}
        self.assertEqual(compute_national_quartile("A", pop, codes), 1)
        self.assertEqual(compute_national_quartile("D", pop, codes), 4)

    def test_not_based_on_observed_competitor_counts_flag_present(self) -> None:
        geography, population = self._fixture()
        result = select_pilot_planning_areas(geography, population, mandated_code="A3")
        self.assertTrue(result["not_based_on_observed_competitor_counts"])


if __name__ == "__main__":
    unittest.main()
