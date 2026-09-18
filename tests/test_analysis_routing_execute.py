from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from tuition_location_analytics.analysis.routing_execute import (
    RedactedRouteCache,
    execute_route_batch,
    execute_route_batch_concurrent,
    parse_safe_route_outcome,
)
from tuition_location_analytics.analysis.routing_execution_cli import readiness
from tuition_location_analytics.competitors.geocode import JsonRequestResult


REPO_ROOT = Path(__file__).resolve().parents[1]


def row() -> dict[str, object]:
    return {
        "od_plan_id": "OD_ONE",
        "origin_latitude_wgs84": 1.30,
        "origin_longitude_wgs84": 103.80,
        "destination_latitude_wgs84": 1.31,
        "destination_longitude_wgs84": 103.81,
        "journey_timestamp": "2026-09-16T16:00:00+08:00",
        "pt_mode": "TRANSIT",
        "max_walk_distance_metres": 1000,
        "num_itineraries": 1,
    }


class SafeRouteParsingTests(unittest.TestCase):
    def test_pt_and_walk_keep_only_selected_numbers(self) -> None:
        pt = parse_safe_route_outcome(
            JsonRequestResult(
                200,
                {"plan": {"itineraries": [{"duration": 600, "legs": [{"distance": 100}, {"distance": 200}]}]}, "secret": "DO_NOT_KEEP"},
                "ok",
            ),
            mode="pt",
        )
        self.assertEqual((pt.category, pt.duration_seconds, pt.distance_metres), ("success", 600.0, 300.0))
        walk = parse_safe_route_outcome(
            JsonRequestResult(200, {"route_summary": {"total_time": 300, "total_distance": 450}}, "ok"),
            mode="walk",
        )
        self.assertEqual((walk.category, walk.duration_seconds, walk.distance_metres), ("success", 300.0, 450.0))

    def test_safe_failure_categories(self) -> None:
        cases = [(404, "missing_route"), (429, "rate_limited"), (401, "authorization_error"), (0, "network_error"), (500, "http_error")]
        for status, expected in cases:
            with self.subTest(status=status):
                result = parse_safe_route_outcome(JsonRequestResult(status, None, "http_error"), mode="pt")
                self.assertEqual(result.category, expected)


class RedactedCacheTests(unittest.TestCase):
    def test_cache_schema_cannot_store_raw_response_or_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "routes.sqlite"
            cache = RedactedRouteCache(path)
            responses = [
                JsonRequestResult(404, None, "http_error"),
                JsonRequestResult(200, {"route_summary": {"total_time": 400, "total_distance": 500}, "secret": "SECRET_BODY"}, "ok"),
            ]

            def request_fn(*args, **kwargs):
                return responses.pop(0)

            summary = execute_route_batch([row()], token="SECRET_TOKEN", cache=cache, request_fn=request_fn, pace_seconds=0)
            cache.close()
            payload = path.read_bytes()
            self.assertNotIn(b"SECRET_BODY", payload)
            self.assertNotIn(b"SECRET_TOKEN", payload)
            self.assertEqual(summary["attempted_requests"], 2)
            self.assertEqual(summary["walking_fallback_requests"], 1)
            with sqlite3.connect(path) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM route_outcomes").fetchone()[0], 2)

    def test_rate_limit_stops_without_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = RedactedRouteCache(Path(tmp) / "routes.sqlite")
            calls = 0

            def request_fn(*args, **kwargs):
                nonlocal calls
                calls += 1
                return JsonRequestResult(429, None, "http_error")

            summary = execute_route_batch([row(), {**row(), "od_plan_id": "OD_TWO"}], token="x", cache=cache, request_fn=request_fn, pace_seconds=0)
            cache.close()
            self.assertEqual(calls, 1)
            self.assertEqual(summary["stop_category"], "rate_limited")

    def test_cached_missing_pt_resumes_uncached_walking_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = RedactedRouteCache(Path(tmp) / "routes.sqlite")
            cache.put("OD_ONE", "pt", parse_safe_route_outcome(JsonRequestResult(404, None, "http_error"), mode="pt"))
            calls = 0

            def request_fn(*args, **kwargs):
                nonlocal calls
                calls += 1
                return JsonRequestResult(200, {"route_summary": {"total_time": 400, "total_distance": 500}}, "ok")

            summary = execute_route_batch([row()], token="x", cache=cache, request_fn=request_fn, pace_seconds=0)
            self.assertEqual(calls, 1)
            self.assertEqual(summary["skipped_cached_primary_rows"], 1)
            self.assertEqual(summary["walking_fallback_requests"], 1)
            self.assertEqual(cache.get("OD_ONE", "walk").category, "success")
            cache.close()

    def test_cached_invalid_pt_resumes_uncached_walking_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = RedactedRouteCache(Path(tmp) / "routes.sqlite")
            cache.put("OD_ONE", "pt", parse_safe_route_outcome(JsonRequestResult(200, {}, "ok"), mode="pt"))

            def request_fn(*args, **kwargs):
                return JsonRequestResult(200, {"route_summary": {"total_time": 400, "total_distance": 500}}, "ok")

            summary = execute_route_batch([row()], token="x", cache=cache, request_fn=request_fn, pace_seconds=0)
            self.assertEqual(summary["walking_fallback_requests"], 1)
            self.assertEqual(cache.get("OD_ONE", "walk").category, "success")
            cache.close()

    def test_concurrent_executor_runs_fallback_and_keeps_safe_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = RedactedRouteCache(Path(tmp) / "routes.sqlite")
            calls = 0

            def request_fn(url, **kwargs):
                nonlocal calls
                calls += 1
                if "routeType=pt" in url:
                    return JsonRequestResult(404, None, "http_error")
                return JsonRequestResult(200, {"route_summary": {"total_time": 400, "total_distance": 500}, "secret": "DO_NOT_KEEP"}, "ok")

            summary = execute_route_batch_concurrent(
                [row()], token="SECRET_TOKEN", cache=cache, request_fn=request_fn,
                request_start_interval_seconds=0, max_workers=2, limit=2,
            )
            self.assertEqual(calls, 2)
            self.assertEqual(summary["walking_fallback_requests"], 1)
            payload = cache.path.read_bytes()
            self.assertNotIn(b"DO_NOT_KEEP", payload)
            self.assertNotIn(b"SECRET_TOKEN", payload)
            cache.close()

    def test_concurrent_rate_limit_stops_new_scheduling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = RedactedRouteCache(Path(tmp) / "routes.sqlite")
            calls = 0

            def request_fn(*args, **kwargs):
                nonlocal calls
                calls += 1
                return JsonRequestResult(429, None, "http_error")

            rows = [row(), {**row(), "od_plan_id": "OD_TWO"}, {**row(), "od_plan_id": "OD_THREE"}]
            summary = execute_route_batch_concurrent(
                rows, token="x", cache=cache, request_fn=request_fn,
                request_start_interval_seconds=0, max_workers=2, limit=3,
            )
            self.assertEqual(summary["stop_category"], "rate_limited")
            self.assertLessEqual(calls, 2)
            cache.close()


class ExecutionGateTests(unittest.TestCase):
    def test_national_execution_readiness_makes_no_network_requests(self) -> None:
        result = readiness(REPO_ROOT)
        self.assertEqual(result["status"], "ready_for_national_execution")
        self.assertEqual(result["network_requests"], 0)


if __name__ == "__main__":
    unittest.main()
