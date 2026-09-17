from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tuition_location_analytics.preflight.common import read_env

from tuition_location_analytics.foundation.common import sha256_file, write_json

AUTH_URL = "https://www.onemap.gov.sg/api/auth/post/getToken"
SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"
USER_AGENT = "tuition-location-analytics-competitors/0.1"

#: Safe, non-secret categories for a global (run-wide) OneMap access failure.
#: Never carries a credential value, token, request body or response body.
ONEMAP_BLOCK_CATEGORIES = ("missing_credentials", "authentication", "network", "invalid_auth_response")


class OneMapUnavailable(RuntimeError):
    """Global OneMap authentication could not be established.

    Raised only for a run-wide access failure (no requests could be made at
    all), never for a single branch's search outcome. ``category`` is one of
    ``ONEMAP_BLOCK_CATEGORIES`` and the message carries only a safe, non-secret
    classification plus an HTTP status code where applicable -- never a
    credential value, token, request body or response body.
    """

    def __init__(self, category: str, message: str, *, http_status: int | None = None) -> None:
        if category not in ONEMAP_BLOCK_CATEGORIES:
            raise ValueError(f"unknown OneMap block category: {category}")
        super().__init__(message)
        self.category = category
        self.http_status = http_status


@dataclass(frozen=True)
class JsonRequestResult:
    """A parsed OneMap response with a safe transport/parse classification.

    ``payload`` is retained only in memory for the immediate caller. It is
    never written to a report, cache or exception. ``outcome`` deliberately
    distinguishes a connection failure from a successful HTTP response whose
    body could not be parsed as the expected JSON object.
    """

    status: int
    payload: dict[str, Any] | None
    outcome: str


def _json_request(
    url: str, *, method: str = "GET", body: bytes | None = None, token: str | None = None
) -> JsonRequestResult:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = token
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = response.status
            try:
                payload = json.loads(response.read().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return JsonRequestResult(status=status, payload=None, outcome="invalid_json")
            if not isinstance(payload, dict):
                return JsonRequestResult(status=status, payload=None, outcome="non_object_json")
            return JsonRequestResult(status=status, payload=payload, outcome="ok")
    except urllib.error.HTTPError as error:
        return JsonRequestResult(status=error.code, payload=None, outcome="http_error")
    except (urllib.error.URLError, TimeoutError):
        return JsonRequestResult(status=0, payload=None, outcome="network")


def _normalise_json_request_result(result: JsonRequestResult | tuple[int, Any]) -> JsonRequestResult:
    """Support existing two-item mocked results while retaining parse state.

    Production calls always receive ``JsonRequestResult``. The tuple support
    is deliberately test-only compatibility and does not make a raw response
    body observable or persistable.
    """
    if isinstance(result, JsonRequestResult):
        return result
    status, payload = result
    if status == 0:
        return JsonRequestResult(status=0, payload=None, outcome="network")
    if status != 200:
        return JsonRequestResult(status=status, payload=None, outcome="http_error")
    if not isinstance(payload, dict):
        return JsonRequestResult(status=status, payload=None, outcome="non_object_json")
    return JsonRequestResult(status=status, payload=payload, outcome="ok")


def _authenticate(repo_root: Path) -> str:
    """Obtain a short-lived OneMap token, or raise a safely categorised OneMapUnavailable.

    The exception message and the ``category`` attribute never contain the
    credential values, the request body or the raw authentication response --
    only a safe classification and, where applicable, the HTTP status code.
    """
    credentials = read_env(repo_root / ".env")
    email = credentials.get("ONEMAP_EMAIL", "")
    password = credentials.get("ONEMAP_EMAIL_PASSWORD", "")
    if not email or not password:
        raise OneMapUnavailable("missing_credentials", "OneMap credentials are unavailable")
    body = json.dumps({"email": email, "password": password}).encode("utf-8")
    response = _normalise_json_request_result(_json_request(AUTH_URL, method="POST", body=body))
    if response.status == 0:
        raise OneMapUnavailable(
            "network", "OneMap authentication request failed: connection, timeout or DNS error"
        )
    if response.status != 200:
        raise OneMapUnavailable(
            "authentication",
            f"OneMap authentication rejected with HTTP {response.status}",
            http_status=response.status,
        )
    if response.outcome != "ok" or response.payload is None:
        raise OneMapUnavailable(
            "invalid_auth_response",
            "OneMap authentication returned HTTP 200 with an invalid response shape",
            http_status=response.status,
        )
    token = response.payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise OneMapUnavailable(
            "invalid_auth_response",
            "OneMap authentication returned HTTP 200 without a usable access token",
            http_status=response.status,
        )
    return token


def geocode_branches(
    repo_root: Path,
    branches: list[dict[str, Any]],
    *,
    pace_seconds: float,
    singapore_bounds: dict[str, float],
    cache_dir: Path,
) -> dict[str, Any]:
    """Exact-postal OneMap geocoding for competitor branches.

    Mirrors the foundation school-geocoding safety guarantees: only an exact
    6-digit postal match with exactly one unique in-bounds WGS84 coordinate is
    accepted; ambiguous, missing or out-of-bounds results remain null. No
    credential, token, request header or raw authentication/search response is
    ever persisted; only the derived category/coordinate per branch is cached.
    """
    fixture = [
        {"branch_id": branch["branch_id"], "postal_code": branch.get("postal_code")}
        for branch in branches
    ]
    fixture_checksum = hashlib.sha256(
        json.dumps(fixture, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    cache_path = cache_dir / f"branch-geocodes-{fixture_checksum[:16]}.json"
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("fixture_checksum") != fixture_checksum:
            raise RuntimeError("branch geocode cache fixture checksum mismatch")
        return {
            "records": cached["records"],
            "summary": cached["summary"],
            "cache_checksum": sha256_file(cache_path),
            "source": "cache",
        }

    token: str | None = None
    records: list[dict[str, Any]] = []
    rate_limited_count = 0
    for index, branch in enumerate(branches):
        postal = branch.get("postal_code")
        if not postal:
            records.append(
                {
                    "branch_id": branch["branch_id"],
                    "status": "missing_postal_code",
                    "exact_postal_candidate_count": None,
                    "unique_coordinate_count": None,
                    "longitude_wgs84": None,
                    "latitude_wgs84": None,
                }
            )
            continue
        if token is None:
            token = _authenticate(repo_root)
        params = urllib.parse.urlencode(
            {"searchVal": postal, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1}
        )
        search_response = _normalise_json_request_result(_json_request(f"{SEARCH_URL}?{params}", token=token))
        status = search_response.status
        payload = search_response.payload or {}
        if status == 429:
            rate_limited_count += 1
        results = payload.get("results") if status == 200 else []
        if not isinstance(results, list):
            results = []
        exact = [item for item in results if str(item.get("POSTAL", "")).strip() == postal]
        candidates: set[tuple[float, float]] = set()
        for item in exact:
            try:
                candidates.add((round(float(item["LONGITUDE"]), 7), round(float(item["LATITUDE"]), 7)))
            except (KeyError, TypeError, ValueError):
                continue
        longitude = latitude = None
        if len(candidates) == 1:
            longitude, latitude = next(iter(candidates))
            in_bounds = (
                singapore_bounds["minimum_longitude"] <= longitude <= singapore_bounds["maximum_longitude"]
                and singapore_bounds["minimum_latitude"] <= latitude <= singapore_bounds["maximum_latitude"]
            )
            category = "resolved_exact_postal_unique_coordinate" if in_bounds else "out_of_bounds"
            if not in_bounds:
                longitude = latitude = None
        elif len(candidates) > 1:
            category = "ambiguous_exact_postal_coordinates"
        elif status == 429:
            category = "rate_limited"
        elif status == 200:
            category = "no_exact_postal_coordinate"
        elif status:
            category = "http_error"
        else:
            category = "network_error"
        records.append(
            {
                "branch_id": branch["branch_id"],
                "status": category,
                "exact_postal_candidate_count": len(exact),
                "unique_coordinate_count": len(candidates),
                "longitude_wgs84": longitude,
                "latitude_wgs84": latitude,
            }
        )
        if index + 1 < len(branches):
            time.sleep(pace_seconds)

    status_counts: dict[str, int] = {}
    for record in records:
        status_counts[record["status"]] = status_counts.get(record["status"], 0) + 1
    summary = {
        "purpose": "Exact-postal coordinate resolution for competitor branches; no routing requests",
        "planned_search_requests": sum(bool(branch.get("postal_code")) for branch in branches),
        "executed_search_requests": sum(
            record["status"] not in {"missing_postal_code"} for record in records
        ),
        "status_counts": dict(sorted(status_counts.items())),
        "rate_limited_count": rate_limited_count,
        "matching_rule": "Exact six-digit postal match and one unique returned WGS84 coordinate; no fuzzy match.",
        "token_persisted": False,
        "raw_authentication_response_recorded": False,
        "raw_search_responses_recorded": False,
        "cache_ref": cache_path.name,
        "fixture_checksum": fixture_checksum,
    }
    write_json(cache_path, {"fixture_checksum": fixture_checksum, "records": records, "summary": summary})
    return {"records": records, "summary": summary, "cache_checksum": sha256_file(cache_path), "source": "executed"}
