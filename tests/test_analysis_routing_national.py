from __future__ import annotations

import unittest

from tuition_location_analytics.analysis.routing_national_cli import build_progress


class NationalRoutingProgressTests(unittest.TestCase):
    def test_progress_requires_primary_and_missing_route_fallback_completion(self) -> None:
        rows = [{"od_plan_id": "A"}, {"od_plan_id": "B"}]
        partial = build_progress(
            rows,
            [
                {"od_plan_id": "A", "method": "pt", "category": "success"},
                {"od_plan_id": "B", "method": "pt", "category": "missing_route"},
            ],
        )
        self.assertEqual(partial["status"], "in_progress")
        self.assertEqual(partial["completed_pt_percent"], 100.0)
        self.assertEqual(partial["walking_fallbacks_required"], 1)
        complete = build_progress(
            rows,
            [
                {"od_plan_id": "A", "method": "pt", "category": "success"},
                {"od_plan_id": "B", "method": "pt", "category": "missing_route"},
                {"od_plan_id": "B", "method": "walk", "category": "success"},
            ],
        )
        self.assertEqual(complete["status"], "complete")


if __name__ == "__main__":
    unittest.main()
