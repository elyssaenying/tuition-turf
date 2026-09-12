from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from tuition_location_analytics.preflight.common import read_env

from .common import write_json

AUTH_URL = "https://www.onemap.gov.sg/api/auth/post/getToken"
SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"
USER_AGENT = "tuition-location-analytics-foundation/0.1"


def school_geocode_cache_path(
    repo_root: Path, snapshot_date: str, fixture_checksum: str
) -> Path:
    return (
        repo_root
        / "data/interim/foundation"
        / snapshot_date
        / f"school-geocodes-{fixture_checksum[:16]}.json"
    )


def _json_request(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    token: str | None = None,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = token
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
            rate_headers = {
                key.lower(): value
                for key, value in response.headers.items()
                if key.lower()
                in {"x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset", "retry-after"}
            }
            return response.status, payload if isinstance(payload, dict) else {}, rate_headers
    except urllib.error.HTTPError as error:
        return error.code, {}, {}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return 0, {}, {}


def _token_from_env(repo_root: Path) -> str:
    credentials = read_env(repo_root / ".env")
    email = credentials.get("ONEMAP_EMAIL", "")
    password = credentials.get("ONEMAP_EMAIL_PASSWORD", "")
    if not email or not password:
        raise RuntimeError("OneMap credentials are unavailable")
    body = json.dumps({"email": email, "password": password}).encode("utf-8")
    status, payload, _ = _json_request(AUTH_URL, method="POST", body=body)
    token = payload.get("access_token") if status == 200 else None
    if not isinstance(token, str) or not token:
        raise RuntimeError(f"OneMap authentication failed with HTTP {status}")
    return token


def geocode_schools(
    repo_root: Path,
    schools: list[dict[str, Any]],
    *,
    snapshot_date: str,
    pace_seconds: float,
    singapore_bounds: dict[str, float],
) -> dict[str, Any]:
    fixture = [
        {"school_id": school["school_id"], "postal_code": school["postal_code"]}
        for school in schools
    ]
    fixture_checksum = hashlib.sha256(
        json.dumps(fixture, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    cache_path = school_geocode_cache_path(repo_root, snapshot_date, fixture_checksum)
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("fixture_checksum") != fixture_checksum:
            raise RuntimeError("School geocode cache fixture checksum mismatch")
        return {"records": cached["records"], "summary": cached["summary"]}
    token = _token_from_env(repo_root)
    records: list[dict[str, Any]] = []
    rate_limited_count = 0
    for index, school in enumerate(schools):
        postal = school["postal_code"]
        if not postal:
            records.append(
                {
                    "school_id": school["school_id"],
                    "status": "missing_postal_code",
                    "http_status": None,
                    "exact_postal_candidate_count": 0,
                    "unique_coordinate_count": 0,
                    "longitude_wgs84": None,
                    "latitude_wgs84": None,
                }
            )
            continue
        params = urllib.parse.urlencode(
            {"searchVal": postal, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1}
        )
        status, payload, _ = _json_request(f"{SEARCH_URL}?{params}", token=token)
        if status == 429:
            rate_limited_count += 1
        results = payload.get("results") if status == 200 else []
        if not isinstance(results, list):
            results = []
        exact = [item for item in results if str(item.get("POSTAL", "")).strip() == postal]
        candidates: list[tuple[float, float, dict[str, Any]]] = []
        for item in exact:
            try:
                latitude = float(item["LATITUDE"])
                longitude = float(item["LONGITUDE"])
            except (KeyError, TypeError, ValueError):
                continue
            candidates.append((longitude, latitude, item))
        unique_coordinates = {(round(item[0], 7), round(item[1], 7)) for item in candidates}
        selected_longitude: float | None = None
        selected_latitude: float | None = None
        if len(unique_coordinates) == 1:
            selected_longitude, selected_latitude = next(iter(unique_coordinates))
            in_bounds = (
                singapore_bounds["minimum_longitude"]
                <= selected_longitude
                <= singapore_bounds["maximum_longitude"]
                and singapore_bounds["minimum_latitude"]
                <= selected_latitude
                <= singapore_bounds["maximum_latitude"]
            )
            category = "resolved_exact_postal_unique_coordinate" if in_bounds else "out_of_bounds"
            if not in_bounds:
                selected_longitude = None
                selected_latitude = None
        elif len(unique_coordinates) > 1:
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
                "school_id": school["school_id"],
                "status": category,
                "http_status": status,
                "exact_postal_candidate_count": len(exact),
                "unique_coordinate_count": len(unique_coordinates),
                "longitude_wgs84": selected_longitude,
                "latitude_wgs84": selected_latitude,
            }
        )
        if index + 1 < len(schools):
            time.sleep(pace_seconds)
    status_counts: dict[str, int] = {}
    for record in records:
        status_counts[record["status"]] = status_counts.get(record["status"], 0) + 1
    result = {
        "records": records,
        "summary": {
            "source_id": "S007",
            "purpose": "Exact-postal coordinate resolution for S004 schools; no routing requests",
            "planned_search_requests": sum(bool(school["postal_code"]) for school in schools),
            "executed_search_requests": sum(record["http_status"] is not None for record in records),
            "status_counts": dict(sorted(status_counts.items())),
            "rate_limited_count": rate_limited_count,
            "request_headers_recorded": False,
            "raw_authentication_response_recorded": False,
            "raw_search_responses_recorded": False,
            "token_persisted": False,
            "matching_rule": "Exact six-digit postal match and one unique returned WGS84 coordinate; no fuzzy match.",
            "cache_ref": cache_path.relative_to(repo_root).as_posix(),
            "fixture_checksum": fixture_checksum,
        },
    }
    write_json(
        cache_path,
        {
            "fixture_checksum": fixture_checksum,
            "records": records,
            "summary": result["summary"],
        },
    )
    return result
