from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tuition_location_analytics.preflight.s007 import (
    EXPECTED_DESTINATIONS,
    EXPECTED_ORIGINS,
    EXPECTED_ROUTE_REQUESTS,
    FIXTURE_PATH,
    load_fixture,
    run,
)


class S007Tests(unittest.TestCase):
    def test_frozen_fixture_and_request_boundary(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        fixture = load_fixture(repo_root)
        self.assertEqual(len(fixture["origins"]), EXPECTED_ORIGINS)
        self.assertEqual(len(fixture["destinations"]), EXPECTED_DESTINATIONS)
        self.assertEqual(EXPECTED_ROUTE_REQUESTS, 60)
        self.assertEqual(fixture["journey_date"], "09-16-2026")
        self.assertEqual(fixture["journey_time"], "16:00:00")

    def test_missing_credentials_makes_no_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture_path = root / FIXTURE_PATH
            fixture_path.parent.mkdir(parents=True)
            source = Path(__file__).resolve().parents[1] / FIXTURE_PATH
            fixture_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            result = run(root, pace_seconds=0)
            self.assertEqual(result["status"], "blocked_missing_credentials")
            self.assertEqual(result["executed_search_requests"], 0)
            self.assertEqual(result["executed_route_requests"], 0)
            self.assertNotIn("token", json.dumps(result).lower().replace("token_persisted", ""))


if __name__ == "__main__":
    unittest.main()

