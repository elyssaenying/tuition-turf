from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tuition_location_analytics.competitors.geocode import OneMapUnavailable, geocode_branches

_BOUNDS = {
    "minimum_longitude": 103.5,
    "maximum_longitude": 104.2,
    "minimum_latitude": 1.1,
    "maximum_latitude": 1.6,
}


def _auth_and_search(search_payloads):
    """Return a fake _json_request that authenticates once then serves search payloads in order."""
    calls = {"n": 0}

    def fake(url, *, method="GET", body=None, token=None):
        if "getToken" in url:
            return 200, {"access_token": "FAKE_TOKEN_NOT_PERSISTED"}
        payload = search_payloads[calls["n"]]
        calls["n"] += 1
        return 200, payload

    return fake


class BranchGeocodingTests(unittest.TestCase):
    def _env(self, directory: Path) -> None:
        (directory / ".env").write_text("ONEMAP_EMAIL=test@example.invalid\nONEMAP_EMAIL_PASSWORD=x\n")

    def test_unique_exact_postal_match_resolves_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            self._env(repo_root)
            branches = [{"branch_id": "B1", "postal_code": "123456"}]
            payloads = [{"results": [{"POSTAL": "123456", "LONGITUDE": "103.85", "LATITUDE": "1.30"}]}]
            with patch(
                "tuition_location_analytics.competitors.geocode._json_request",
                side_effect=_auth_and_search(payloads),
            ):
                result = geocode_branches(
                    repo_root,
                    branches,
                    pace_seconds=0.0,
                    singapore_bounds=_BOUNDS,
                    cache_dir=repo_root,
                )
            record = result["records"][0]
            self.assertEqual(record["status"], "resolved_exact_postal_unique_coordinate")
            self.assertAlmostEqual(record["longitude_wgs84"], 103.85)

    def test_ambiguous_multiple_coordinates_remain_null(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            self._env(repo_root)
            branches = [{"branch_id": "B1", "postal_code": "123456"}]
            payloads = [
                {
                    "results": [
                        {"POSTAL": "123456", "LONGITUDE": "103.85", "LATITUDE": "1.30"},
                        {"POSTAL": "123456", "LONGITUDE": "103.86", "LATITUDE": "1.31"},
                    ]
                }
            ]
            with patch(
                "tuition_location_analytics.competitors.geocode._json_request",
                side_effect=_auth_and_search(payloads),
            ):
                result = geocode_branches(
                    repo_root,
                    branches,
                    pace_seconds=0.0,
                    singapore_bounds=_BOUNDS,
                    cache_dir=repo_root,
                )
            record = result["records"][0]
            self.assertEqual(record["status"], "ambiguous_exact_postal_coordinates")
            self.assertIsNone(record["longitude_wgs84"])
            self.assertIsNone(record["latitude_wgs84"])

    def test_missing_postal_code_is_not_attempted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            branches = [{"branch_id": "B1", "postal_code": None}]
            with patch(
                "tuition_location_analytics.competitors.geocode._json_request",
                side_effect=AssertionError("must not call OneMap for a branch with no postal code"),
            ):
                result = geocode_branches(
                    repo_root,
                    branches,
                    pace_seconds=0.0,
                    singapore_bounds=_BOUNDS,
                    cache_dir=repo_root,
                )
            self.assertEqual(result["records"][0]["status"], "missing_postal_code")

    def test_no_exact_match_remains_null_not_nearest_guess(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            self._env(repo_root)
            branches = [{"branch_id": "B1", "postal_code": "999999"}]
            payloads = [{"results": [{"POSTAL": "111111", "LONGITUDE": "103.85", "LATITUDE": "1.30"}]}]
            with patch(
                "tuition_location_analytics.competitors.geocode._json_request",
                side_effect=_auth_and_search(payloads),
            ):
                result = geocode_branches(
                    repo_root,
                    branches,
                    pace_seconds=0.0,
                    singapore_bounds=_BOUNDS,
                    cache_dir=repo_root,
                )
            record = result["records"][0]
            self.assertEqual(record["status"], "no_exact_postal_coordinate")
            self.assertIsNone(record["longitude_wgs84"])

    def test_cache_reuse_makes_no_further_network_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            self._env(repo_root)
            branches = [{"branch_id": "B1", "postal_code": "123456"}]
            payloads = [{"results": [{"POSTAL": "123456", "LONGITUDE": "103.85", "LATITUDE": "1.30"}]}]
            with patch(
                "tuition_location_analytics.competitors.geocode._json_request",
                side_effect=_auth_and_search(payloads),
            ):
                geocode_branches(repo_root, branches, pace_seconds=0.0, singapore_bounds=_BOUNDS, cache_dir=repo_root)
            with patch(
                "tuition_location_analytics.competitors.geocode._json_request",
                side_effect=AssertionError("must not call OneMap again on cache reuse"),
            ):
                result = geocode_branches(repo_root, branches, pace_seconds=0.0, singapore_bounds=_BOUNDS, cache_dir=repo_root)
            self.assertEqual(result["records"][0]["status"], "resolved_exact_postal_unique_coordinate")

    def test_summary_never_records_token_or_raw_responses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            self._env(repo_root)
            branches = [{"branch_id": "B1", "postal_code": "123456"}]
            payloads = [{"results": [{"POSTAL": "123456", "LONGITUDE": "103.85", "LATITUDE": "1.30"}]}]
            with patch(
                "tuition_location_analytics.competitors.geocode._json_request",
                side_effect=_auth_and_search(payloads),
            ):
                result = geocode_branches(repo_root, branches, pace_seconds=0.0, singapore_bounds=_BOUNDS, cache_dir=repo_root)
            summary_text = str(result["summary"])
            self.assertNotIn("FAKE_TOKEN_NOT_PERSISTED", summary_text)
            self.assertFalse(result["summary"]["token_persisted"])
            self.assertFalse(result["summary"]["raw_authentication_response_recorded"])
            self.assertEqual(len(result["cache_checksum"]), 64)

    def test_fresh_execution_is_marked_as_executed_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            self._env(repo_root)
            branches = [{"branch_id": "B1", "postal_code": "123456"}]
            payloads = [{"results": [{"POSTAL": "123456", "LONGITUDE": "103.85", "LATITUDE": "1.30"}]}]
            with patch(
                "tuition_location_analytics.competitors.geocode._json_request",
                side_effect=_auth_and_search(payloads),
            ):
                result = geocode_branches(repo_root, branches, pace_seconds=0.0, singapore_bounds=_BOUNDS, cache_dir=repo_root)
            self.assertEqual(result["source"], "executed")

    def test_cache_reuse_is_marked_as_cache_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            self._env(repo_root)
            branches = [{"branch_id": "B1", "postal_code": "123456"}]
            payloads = [{"results": [{"POSTAL": "123456", "LONGITUDE": "103.85", "LATITUDE": "1.30"}]}]
            with patch(
                "tuition_location_analytics.competitors.geocode._json_request",
                side_effect=_auth_and_search(payloads),
            ):
                geocode_branches(repo_root, branches, pace_seconds=0.0, singapore_bounds=_BOUNDS, cache_dir=repo_root)
            with patch(
                "tuition_location_analytics.competitors.geocode._json_request",
                side_effect=AssertionError("must not call OneMap again on cache reuse"),
            ):
                result = geocode_branches(repo_root, branches, pace_seconds=0.0, singapore_bounds=_BOUNDS, cache_dir=repo_root)
            self.assertEqual(result["source"], "cache")


class OneMapFailureClassificationTests(unittest.TestCase):
    """Safe classification of a global (run-wide) OneMap access failure.

    Every case here must raise OneMapUnavailable with a distinct, safe
    category -- never a bare RuntimeError collapsed into one generic
    "no credentials" outcome -- and the exception's string form must never
    contain a credential, token, request-body or response-body value.
    """

    def test_missing_credentials_is_classified_without_any_network_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            # Deliberately no .env written: credentials are genuinely absent.
            branches = [{"branch_id": "B1", "postal_code": "123456"}]
            with patch(
                "tuition_location_analytics.competitors.geocode._json_request",
                side_effect=AssertionError("must not call OneMap when credentials are absent"),
            ):
                with self.assertRaises(OneMapUnavailable) as ctx:
                    geocode_branches(repo_root, branches, pace_seconds=0.0, singapore_bounds=_BOUNDS, cache_dir=repo_root)
            self.assertEqual(ctx.exception.category, "missing_credentials")

    def test_rejected_authentication_is_classified_distinctly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            self._env(repo_root)
            branches = [{"branch_id": "B1", "postal_code": "123456"}]

            def fake(url, *, method="GET", body=None, token=None):
                self.assertIn("SECRET_PASSWORD_VALUE", body.decode("utf-8"))
                return 401, {}

            with patch("tuition_location_analytics.competitors.geocode._json_request", side_effect=fake):
                with self.assertRaises(OneMapUnavailable) as ctx:
                    geocode_branches(repo_root, branches, pace_seconds=0.0, singapore_bounds=_BOUNDS, cache_dir=repo_root)
            self.assertEqual(ctx.exception.category, "authentication")
            self.assertIn("401", str(ctx.exception))
            self.assertNotIn("SECRET_PASSWORD_VALUE", str(ctx.exception))

    def test_network_failure_is_classified_distinctly_from_authentication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            self._env(repo_root)
            branches = [{"branch_id": "B1", "postal_code": "123456"}]

            def fake(url, *, method="GET", body=None, token=None):
                return 0, {}

            with patch("tuition_location_analytics.competitors.geocode._json_request", side_effect=fake):
                with self.assertRaises(OneMapUnavailable) as ctx:
                    geocode_branches(repo_root, branches, pace_seconds=0.0, singapore_bounds=_BOUNDS, cache_dir=repo_root)
            self.assertEqual(ctx.exception.category, "network")

    def test_malformed_successful_response_is_classified_distinctly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            self._env(repo_root)
            branches = [{"branch_id": "B1", "postal_code": "123456"}]

            def fake(url, *, method="GET", body=None, token=None):
                return 200, {"unexpected_field": "SECRET_LOOKING_RESPONSE_BODY_VALUE"}

            with patch("tuition_location_analytics.competitors.geocode._json_request", side_effect=fake):
                with self.assertRaises(OneMapUnavailable) as ctx:
                    geocode_branches(repo_root, branches, pace_seconds=0.0, singapore_bounds=_BOUNDS, cache_dir=repo_root)
            self.assertEqual(ctx.exception.category, "invalid_auth_response")
            self.assertNotIn("SECRET_LOOKING_RESPONSE_BODY_VALUE", str(ctx.exception))

    def test_four_categories_are_all_distinct(self) -> None:
        from tuition_location_analytics.competitors.geocode import ONEMAP_BLOCK_CATEGORIES

        self.assertEqual(
            set(ONEMAP_BLOCK_CATEGORIES),
            {"missing_credentials", "authentication", "network", "invalid_auth_response"},
        )

    def _env(self, directory: Path) -> None:
        (directory / ".env").write_text(
            "ONEMAP_EMAIL=test@example.invalid\nONEMAP_EMAIL_PASSWORD=SECRET_PASSWORD_VALUE\n"
        )


if __name__ == "__main__":
    unittest.main()
