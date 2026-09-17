from __future__ import annotations

import json
import unittest
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class AccessibilityScenarioConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(
            (REPO_ROOT / "config/accessibility/scenarios.json").read_text(encoding="utf-8")
        )

    def test_frozen_before_any_routing_result(self) -> None:
        self.assertEqual(self.config["status"], "frozen_pre_results")

    def test_primary_timestamps_are_valid_singapore_local_iso(self) -> None:
        primary = self.config["primary_scenario"]["journey_timestamp"]
        parsed = datetime.fromisoformat(primary)
        self.assertEqual(parsed.utcoffset().total_seconds(), 8 * 3600)
        self.assertEqual(parsed.strftime("%A"), "Wednesday")

        weekend = self.config["sensitivity_scenarios"]["weekend_comparison_scenario"]["journey_timestamp"]
        parsed_weekend = datetime.fromisoformat(weekend)
        self.assertEqual(parsed_weekend.strftime("%A"), "Saturday")

    def test_primary_thresholds_present_and_positive(self) -> None:
        primary = self.config["primary_scenario"]
        self.assertEqual(primary["public_transport_threshold_minutes"], 20)
        self.assertEqual(primary["walking_threshold_minutes"], 10)
        self.assertEqual(primary["straight_line_proximity_fallback_metres"], 800)

    def test_sensitivity_thresholds_bracket_the_primary_value(self) -> None:
        sensitivity = self.config["sensitivity_scenarios"]
        pt_values = sensitivity["public_transport_threshold_minutes"]
        walk_values = sensitivity["walking_threshold_minutes"]
        primary = self.config["primary_scenario"]
        self.assertTrue(min(pt_values) < primary["public_transport_threshold_minutes"] < max(pt_values))
        self.assertTrue(min(walk_values) < primary["walking_threshold_minutes"] < max(walk_values))

    def test_h2_materiality_threshold_is_ten_percent_and_frozen(self) -> None:
        rule = self.config["h2_materiality_rule"]["primary_rule"]
        self.assertEqual(rule["materiality_threshold"], 0.10)
        self.assertEqual(rule["aggregation"], "median across all nodes with a valid computation")
        self.assertIn("zero_or_null_denominator_handling", rule)

    def test_secondary_diagnostics_are_marked_non_replacing(self) -> None:
        diagnostics = self.config["h2_materiality_rule"]["secondary_descriptive_diagnostics"]
        self.assertEqual(len(diagnostics), 2)
        names = {d["diagnostic"] for d in diagnostics}
        self.assertEqual(names, {"spearman_rank_correlation", "share_of_nodes_moving_at_least_10_ranks"})
        for diagnostic in diagnostics:
            self.assertIn("does not replace", diagnostic["role"])

    def test_proximity_fallback_never_labelled_as_travel_time(self) -> None:
        primary = self.config["primary_scenario"]
        self.assertIn("never a travel-time claim", primary["proximity_fallback_rule"])
        self.assertIn("never imputed", primary["missing_route_rule"].lower())


if __name__ == "__main__":
    unittest.main()
