from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .common import read_env, utc_now

AUTH_URL = "https://www.onemap.gov.sg/api/auth/post/getToken"
SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"
ROUTE_URL = "https://www.onemap.gov.sg/api/public/routingsvc/route"
FIXTURE_PATH = Path("config/preflight/onemap_od_fixture.json")
EXPECTED_ORIGINS = 10
EXPECTED_DESTINATIONS = 3
EXPECTED_MODES = ("pt", "walk")
EXPECTED_ROUTE_REQUESTS = EXPECTED_ORIGINS * EXPECTED_DESTINATIONS * len(EXPECTED_MODES)


@dataclass(frozen=True)
class Coordinates:
    latitude: float
    longitude: float

    def query_value(self) -> str:
        return f"{self.latitude:.7f},{self.longitude:.7f}"


def load_fixture(repo_root: Path) -> dict[str, Any]:
    fixture = json.loads((repo_root / FIXTURE_PATH).read_text(encoding="utf-8"))
    if len(fixture["origins"]) != EXPECTED_ORIGINS:
        raise ValueError("fixture must contain exactly 10 origins")
    if len(fixture["destinations"]) != EXPECTED_DESTINATIONS:
        raise ValueError("fixture must contain exactly 3 destinations")
    return fixture


def _request_json(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    token: str | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    headers = {"Accept": "application/json", "User-Agent": "tuition-location-analytics-preflight/0.1"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = token
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            rate_headers = {
                key.lower(): value
                for key, value in response.headers.items()
                if key.lower() in {"x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset", "retry-after"}
            }
            return response.status, payload, rate_headers
    except urllib.error.HTTPError as error:
        return error.code, {}, {}


def _get_token(email: str, password: str) -> tuple[str, str | None]:
    body = json.dumps({"email": email, "password": password}).encode("utf-8")
    status, payload, _ = _request_json(AUTH_URL, method="POST", body=body)
    token = payload.get("access_token") if status == 200 else None
    if not isinstance(token, str) or not token:
        raise RuntimeError(f"authentication_failed_http_{status}")
    expiry = payload.get("expiry_timestamp")
    return token, str(expiry) if expiry is not None else None


def _resolve_location(query: str, token: str) -> tuple[Coordinates | None, dict[str, Any]]:
    params = urllib.parse.urlencode(
        {"searchVal": query, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1}
    )
    status, payload, rate_headers = _request_json(f"{SEARCH_URL}?{params}", token=token)
    results = payload.get("results") if status == 200 else None
    if not isinstance(results, list) or not results:
        return None, {"http_status": status, "category": "missing_search_result", "rate_headers": rate_headers}
    first = results[0]
    try:
        coordinates = Coordinates(float(first["LATITUDE"]), float(first["LONGITUDE"]))
    except (KeyError, TypeError, ValueError):
        return None, {"http_status": status, "category": "missing_coordinates", "rate_headers": rate_headers}
    return coordinates, {
        "http_status": status,
        "category": "resolved",
        "selected_search_value": first.get("SEARCHVAL"),
        "selected_postal": first.get("POSTAL"),
        "rate_headers": rate_headers,
    }


def _route(
    origin: Coordinates,
    destination: Coordinates,
    mode: str,
    fixture: dict[str, Any],
    token: str,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "start": origin.query_value(),
        "end": destination.query_value(),
        "routeType": mode,
    }
    if mode == "pt":
        params.update(
            {
                "date": fixture["journey_date"],
                "time": fixture["journey_time"],
                "mode": "TRANSIT",
                "maxWalkDistance": fixture["max_walk_distance_metres"],
                "numItineraries": 1,
            }
        )
    status, payload, rate_headers = _request_json(
        f"{ROUTE_URL}?{urllib.parse.urlencode(params)}", token=token
    )
    summary = payload.get("route_summary") if isinstance(payload, dict) else None
    itineraries = payload.get("plan", {}).get("itineraries") if isinstance(payload, dict) else None
    duration_available = isinstance(summary, dict) and summary.get("total_time") is not None
    distance_available = isinstance(summary, dict) and summary.get("total_distance") is not None
    if mode == "pt" and isinstance(itineraries, list) and itineraries:
        duration_available = itineraries[0].get("duration") is not None
        distance_available = any(
            leg.get("distance") is not None for leg in itineraries[0].get("legs", [])
        )
    if status == 200 and (duration_available or distance_available):
        category = "success"
    elif status == 404:
        category = "missing_route"
    elif status == 429:
        category = "rate_limited"
    elif status in {401, 403}:
        category = "authorization_error"
    else:
        category = "api_error"
    return {
        "http_status": status,
        "category": category,
        "duration_field_available": duration_available,
        "distance_field_available": distance_available,
        "rate_headers": rate_headers,
    }


def run(repo_root: Path, pace_seconds: float = 0.5) -> dict[str, Any]:
    fixture = load_fixture(repo_root)
    credentials = read_env(repo_root / ".env")
    email = credentials.get("ONEMAP_EMAIL", "")
    password = credentials.get("ONEMAP_EMAIL_PASSWORD", "")
    base = {
        "source_id": "S007",
        "started_at": utc_now(),
        "fixture_ref": FIXTURE_PATH.as_posix(),
        "fixture_role": "coverage-test fixtures, not recommended candidates",
        "journey_date": fixture["journey_date"],
        "journey_time": fixture["journey_time"],
        "planned_search_requests": EXPECTED_ORIGINS + EXPECTED_DESTINATIONS,
        "planned_route_requests": EXPECTED_ROUTE_REQUESTS,
        "executed_search_requests": 0,
        "executed_route_requests": 0,
        "request_headers_recorded": False,
        "raw_authentication_response_recorded": False,
        "token_persisted": False,
    }
    if not email or not password:
        return {
            **base,
            "status": "blocked_missing_credentials",
            "limitation": "Create the ignored .env with both documented OneMap variables, then rerun. No API request was made.",
        }

    try:
        token, expiry = _get_token(email, password)
    except RuntimeError as error:
        return {**base, "status": str(error), "authentication_request_count": 1}

    resolved: dict[str, Coordinates] = {}
    resolution_records: list[dict[str, Any]] = []
    locations = [("origin", item) for item in fixture["origins"]] + [
        ("destination", item) for item in fixture["destinations"]
    ]
    for role, item in locations:
        coordinates, record = _resolve_location(item["search_query"], token)
        base["executed_search_requests"] += 1
        resolution_records.append({"id": item["id"], "role": role, **record})
        if coordinates is not None:
            resolved[item["id"]] = coordinates
        time.sleep(pace_seconds)

    if len(resolved) != len(locations):
        return {
            **base,
            "status": "blocked_fixture_resolution",
            "token_expiry_received": expiry is not None,
            "fixture_resolution": resolution_records,
            "limitation": "All 13 fixed locations must resolve before any routing request is made.",
        }

    route_records: list[dict[str, Any]] = []
    for origin in fixture["origins"]:
        for destination in fixture["destinations"]:
            for mode in EXPECTED_MODES:
                record = _route(
                    resolved[origin["id"]],
                    resolved[destination["id"]],
                    mode,
                    fixture,
                    token,
                )
                base["executed_route_requests"] += 1
                route_records.append(
                    {
                        "origin_id": origin["id"],
                        "destination_id": destination["id"],
                        "mode": mode,
                        **record,
                    }
                )
                time.sleep(pace_seconds)

    missing = sum(record["category"] == "missing_route" for record in route_records)
    rate_limited = sum(record["category"] == "rate_limited" for record in route_records)
    return {
        **base,
        "status": "completed",
        "token_expiry_received": expiry is not None,
        "fixture_resolution": resolution_records,
        "routes": route_records,
        "missing_route_count": missing,
        "missing_route_rate": missing / EXPECTED_ROUTE_REQUESTS,
        "rate_limited_count": rate_limited,
        "persistence_limitation": "Only redacted aggregate/request metadata is persisted; authentication material and raw route responses are not stored.",
    }

