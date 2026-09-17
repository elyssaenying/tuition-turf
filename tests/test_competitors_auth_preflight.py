from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tuition_location_analytics.competitors import auth_preflight
from tuition_location_analytics.competitors.geocode import AUTH_URL, JsonRequestResult, _json_request


_SECRET_EMAIL = "preflight-secret@example.invalid"
_SECRET_PASSWORD = "PRELIGHT_SECRET_PASSWORD_VALUE"
_SECRET_TOKEN = "PRELIGHT_SECRET_TOKEN_VALUE"
_SECRET_RESPONSE = "PRELIGHT_SECRET_RESPONSE_BODY_VALUE"


class _Response:
    def __init__(self, body: bytes) -> None:
        self.status = 200
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class CompetitorAuthPreflightTests(unittest.TestCase):
    def _repo_with_credentials(self, directory: str) -> Path:
        root = Path(directory)
        (root / ".env").write_text(
            f"ONEMAP_EMAIL={_SECRET_EMAIL}\nONEMAP_EMAIL_PASSWORD={_SECRET_PASSWORD}\n",
            encoding="utf-8",
        )
        return root

    def _assert_no_secret(self, value: object) -> None:
        rendered = str(value)
        for secret in (_SECRET_EMAIL, _SECRET_PASSWORD, _SECRET_TOKEN, _SECRET_RESPONSE):
            self.assertNotIn(secret, rendered)

    def test_success_uses_one_auth_request_and_no_search_or_routing_and_discards_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo_with_credentials(directory)
            calls: list[str] = []

            def fake(url, *, method="GET", body=None, token=None):
                calls.append(url)
                self.assertEqual(url, AUTH_URL)
                self.assertEqual(method, "POST")
                return JsonRequestResult(200, {"access_token": _SECRET_TOKEN}, "ok")

            with patch("tuition_location_analytics.competitors.geocode._json_request", side_effect=fake):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    exit_code = auth_preflight.main(["--repo-root", str(root)])
            self.assertEqual(exit_code, 0)
            self.assertEqual(calls, [AUTH_URL])
            result = json.loads(output.getvalue())
            self.assertEqual(
                result,
                {"status": "pass", "authentication_requests": 1, "search_requests": 0, "routing_requests": 0},
            )
            self._assert_no_secret(output.getvalue())

    def test_missing_credentials_makes_no_request_and_returns_only_safe_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch(
                "tuition_location_analytics.competitors.geocode._json_request",
                side_effect=AssertionError("authentication must not be called"),
            ):
                result = auth_preflight.run_auth_preflight(root)
            self.assertEqual(
                result,
                {
                    "status": "blocked_missing_credentials",
                    "authentication_requests": 0,
                    "search_requests": 0,
                    "routing_requests": 0,
                },
            )

    def test_authentication_rejection_is_safe_and_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo_with_credentials(directory)
            with patch(
                "tuition_location_analytics.competitors.geocode._json_request",
                return_value=JsonRequestResult(401, None, "http_error"),
            ):
                result = auth_preflight.run_auth_preflight(root)
            self.assertEqual(result["status"], "blocked_authentication")
            self.assertEqual(result["authentication_requests"], 1)
            self.assertEqual(result["http_status"], 401)
            self._assert_no_secret(result)

    def test_network_failure_is_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo_with_credentials(directory)
            with patch(
                "tuition_location_analytics.competitors.geocode._json_request",
                return_value=JsonRequestResult(0, None, "network"),
            ):
                result = auth_preflight.run_auth_preflight(root)
            self.assertEqual(result["status"], "blocked_network")
            self.assertEqual(result["authentication_requests"], 1)
            self._assert_no_secret(result)

    def test_http_200_malformed_json_is_invalid_auth_response_without_body_exposure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo_with_credentials(directory)
            with patch(
                "tuition_location_analytics.competitors.geocode._json_request",
                return_value=JsonRequestResult(200, None, "invalid_json"),
            ):
                result = auth_preflight.run_auth_preflight(root)
            self.assertEqual(result["status"], "blocked_invalid_auth_response")
            self._assert_no_secret(result)

    def test_http_200_non_object_json_is_invalid_auth_response_without_body_exposure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo_with_credentials(directory)
            with patch(
                "tuition_location_analytics.competitors.geocode._json_request",
                return_value=JsonRequestResult(200, None, "non_object_json"),
            ):
                result = auth_preflight.run_auth_preflight(root)
            self.assertEqual(result["status"], "blocked_invalid_auth_response")
            self._assert_no_secret(result)

    def test_http_200_missing_or_invalid_access_token_is_invalid_auth_response(self) -> None:
        for payload in ({}, {"access_token": ""}, {"access_token": 7}):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as directory:
                root = self._repo_with_credentials(directory)
                with patch(
                    "tuition_location_analytics.competitors.geocode._json_request",
                    return_value=JsonRequestResult(200, payload, "ok"),
                ):
                    result = auth_preflight.run_auth_preflight(root)
                self.assertEqual(result["status"], "blocked_invalid_auth_response")
                self._assert_no_secret(result)

    def test_generic_request_preserves_invalid_json_and_non_object_classification(self) -> None:
        with patch("urllib.request.urlopen", return_value=_Response(b"{")):
            malformed = _json_request("https://example.invalid/auth", body=b"request-body-not-persisted")
        with patch("urllib.request.urlopen", return_value=_Response(b"[]")):
            non_object = _json_request("https://example.invalid/auth")
        self.assertEqual((malformed.status, malformed.outcome), (200, "invalid_json"))
        self.assertEqual((non_object.status, non_object.outcome), (200, "non_object_json"))
        self._assert_no_secret(malformed)
        self._assert_no_secret(non_object)


if __name__ == "__main__":
    unittest.main()
