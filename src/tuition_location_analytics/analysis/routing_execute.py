from __future__ import annotations

import json
import sqlite3
import time
import urllib.parse
from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from tuition_location_analytics.competitors.geocode import JsonRequestResult, _json_request
from tuition_location_analytics.foundation.common import utc_now


ROUTE_URL = "https://www.onemap.gov.sg/api/public/routingsvc/route"
STOP_CATEGORIES = frozenset({"rate_limited", "authorization_error", "network_error"})
WALK_FALLBACK_PT_CATEGORIES = frozenset({"missing_route", "invalid_response"})


@dataclass(frozen=True)
class SafeRouteOutcome:
    category: str
    http_status: int
    duration_seconds: float | None
    distance_metres: float | None


def parse_safe_route_outcome(response: JsonRequestResult, *, mode: str) -> SafeRouteOutcome:
    status = response.status
    payload = response.payload if response.outcome == "ok" and isinstance(response.payload, dict) else {}
    if status == 404:
        return SafeRouteOutcome("missing_route", status, None, None)
    if status == 429:
        return SafeRouteOutcome("rate_limited", status, None, None)
    if status in {401, 403}:
        return SafeRouteOutcome("authorization_error", status, None, None)
    if status == 0:
        return SafeRouteOutcome("network_error", status, None, None)
    if status != 200:
        return SafeRouteOutcome("http_error", status, None, None)
    if response.outcome != "ok":
        return SafeRouteOutcome("invalid_response", status, None, None)

    duration: float | None = None
    distance: float | None = None
    if mode == "pt":
        itineraries = payload.get("plan", {}).get("itineraries") if isinstance(payload.get("plan"), dict) else None
        if isinstance(itineraries, list) and itineraries and isinstance(itineraries[0], dict):
            raw_duration = itineraries[0].get("duration")
            legs = itineraries[0].get("legs")
            if isinstance(raw_duration, (int, float)):
                duration = float(raw_duration)
            if isinstance(legs, list):
                values = [leg.get("distance") for leg in legs if isinstance(leg, dict)]
                numeric = [float(value) for value in values if isinstance(value, (int, float))]
                if numeric:
                    distance = sum(numeric)
    elif mode == "walk":
        summary = payload.get("route_summary")
        if isinstance(summary, dict):
            raw_duration = summary.get("total_time")
            raw_distance = summary.get("total_distance")
            if isinstance(raw_duration, (int, float)):
                duration = float(raw_duration)
            if isinstance(raw_distance, (int, float)):
                distance = float(raw_distance)
    else:
        raise ValueError(f"unsupported route mode: {mode}")
    if duration is None:
        return SafeRouteOutcome("invalid_response", status, None, None)
    return SafeRouteOutcome("success", status, duration, distance)


class RedactedRouteCache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS route_outcomes (
                od_plan_id TEXT NOT NULL,
                method TEXT NOT NULL,
                category TEXT NOT NULL,
                http_status INTEGER NOT NULL,
                duration_seconds REAL,
                distance_metres REAL,
                attempted_at TEXT NOT NULL,
                PRIMARY KEY (od_plan_id, method)
            )
            """
        )
        self.connection.commit()

    def has(self, od_plan_id: str, method: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM route_outcomes WHERE od_plan_id=? AND method=?",
            (od_plan_id, method),
        ).fetchone()
        return row is not None

    def get(self, od_plan_id: str, method: str) -> SafeRouteOutcome | None:
        row = self.connection.execute(
            """
            SELECT category, http_status, duration_seconds, distance_metres
            FROM route_outcomes
            WHERE od_plan_id=? AND method=?
            """,
            (od_plan_id, method),
        ).fetchone()
        if row is None:
            return None
        return SafeRouteOutcome(
            category=str(row[0]),
            http_status=int(row[1]),
            duration_seconds=float(row[2]) if row[2] is not None else None,
            distance_metres=float(row[3]) if row[3] is not None else None,
        )

    def put(self, od_plan_id: str, method: str, outcome: SafeRouteOutcome) -> None:
        self.connection.execute(
            """
            INSERT INTO route_outcomes
            (od_plan_id, method, category, http_status, duration_seconds, distance_metres, attempted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(od_plan_id, method) DO NOTHING
            """,
            (
                od_plan_id,
                method,
                outcome.category,
                outcome.http_status,
                outcome.duration_seconds,
                outcome.distance_metres,
                utc_now(),
            ),
        )
        self.connection.commit()

    def count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM route_outcomes").fetchone()[0])

    def records(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT od_plan_id, method, category, http_status,
                   duration_seconds, distance_metres, attempted_at
            FROM route_outcomes
            ORDER BY od_plan_id, method
            """
        ).fetchall()
        return [
            {
                "od_plan_id": row[0],
                "method": row[1],
                "category": row[2],
                "http_status": row[3],
                "duration_seconds": row[4],
                "distance_metres": row[5],
                "attempted_at": row[6],
            }
            for row in rows
        ]

    def close(self) -> None:
        self.connection.close()


def _route_url(row: dict[str, Any], mode: str) -> str:
    params: dict[str, Any] = {
        "start": f"{float(row['origin_latitude_wgs84']):.7f},{float(row['origin_longitude_wgs84']):.7f}",
        "end": f"{float(row['destination_latitude_wgs84']):.7f},{float(row['destination_longitude_wgs84']):.7f}",
        "routeType": mode,
    }
    if mode == "pt":
        timestamp = str(row["journey_timestamp"])
        date_part, time_part = timestamp.split("T", 1)
        year, month, day = date_part.split("-")
        params.update(
            {
                "date": f"{month}-{day}-{year}",
                "time": time_part[:8],
                "mode": row["pt_mode"],
                "maxWalkDistance": row["max_walk_distance_metres"],
                "numItineraries": row["num_itineraries"],
            }
        )
    return f"{ROUTE_URL}?{urllib.parse.urlencode(params)}"


def execute_route_batch(
    rows: Iterable[dict[str, Any]],
    *,
    token: str,
    cache: RedactedRouteCache,
    request_fn: Callable[..., JsonRequestResult] = _json_request,
    pace_seconds: float,
    limit: int | None = None,
) -> dict[str, Any]:
    attempted = 0
    skipped_cached = 0
    walking_fallbacks = 0
    stop_category: str | None = None
    for row in rows:
        if limit is not None and attempted >= limit:
            break
        od_id = str(row["od_plan_id"])
        pt = cache.get(od_id, "pt")
        if pt is not None:
            skipped_cached += 1
        else:
            pt = parse_safe_route_outcome(request_fn(_route_url(row, "pt"), token=token), mode="pt")
            cache.put(od_id, "pt", pt)
            attempted += 1
            if pace_seconds > 0:
                time.sleep(pace_seconds)
        if pt.category in STOP_CATEGORIES:
            stop_category = pt.category
            break
        if pt.category in WALK_FALLBACK_PT_CATEGORIES:
            if limit is not None and attempted >= limit:
                break
            if not cache.has(od_id, "walk"):
                walk = parse_safe_route_outcome(request_fn(_route_url(row, "walk"), token=token), mode="walk")
                cache.put(od_id, "walk", walk)
                attempted += 1
                walking_fallbacks += 1
                if pace_seconds > 0:
                    time.sleep(pace_seconds)
                if walk.category in STOP_CATEGORIES:
                    stop_category = walk.category
                    break
    return {
        "attempted_requests": attempted,
        "skipped_cached_primary_rows": skipped_cached,
        "walking_fallback_requests": walking_fallbacks,
        "stop_category": stop_category,
        "cache_record_count": cache.count(),
        "raw_response_persisted": False,
        "token_persisted": False,
    }


def execute_route_batch_concurrent(
    rows: Iterable[dict[str, Any]],
    *,
    token: str,
    cache: RedactedRouteCache,
    request_fn: Callable[..., JsonRequestResult] = _json_request,
    request_start_interval_seconds: float,
    max_workers: int,
    limit: int,
) -> dict[str, Any]:
    if max_workers <= 0 or limit <= 0 or request_start_interval_seconds < 0:
        raise ValueError("concurrent route execution limits are invalid")
    tasks: deque[tuple[dict[str, Any], str]] = deque()
    skipped_cached = 0
    for row in rows:
        od_id = str(row["od_plan_id"])
        pt = cache.get(od_id, "pt")
        if pt is None:
            tasks.append((row, "pt"))
        else:
            skipped_cached += 1
            if pt.category in WALK_FALLBACK_PT_CATEGORIES and cache.get(od_id, "walk") is None:
                tasks.append((row, "walk"))

    attempted = 0
    walking_fallbacks = 0
    stop_category: str | None = None
    last_started: float | None = None
    futures: dict[Future[JsonRequestResult], tuple[dict[str, Any], str]] = {}

    def persist(future: Future[JsonRequestResult], row: dict[str, Any], mode: str) -> None:
        nonlocal stop_category, walking_fallbacks
        try:
            response = future.result()
        except Exception:
            response = JsonRequestResult(status=0, payload=None, outcome="network")
        outcome = parse_safe_route_outcome(response, mode=mode)
        od_id = str(row["od_plan_id"])
        cache.put(od_id, mode, outcome)
        if mode == "walk":
            walking_fallbacks += 1
        if outcome.category in STOP_CATEGORIES and stop_category is None:
            stop_category = outcome.category
        if mode == "pt" and outcome.category in WALK_FALLBACK_PT_CATEGORIES and stop_category is None:
            if cache.get(od_id, "walk") is None:
                tasks.appendleft((row, "walk"))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        while tasks or futures:
            while tasks and len(futures) < max_workers and attempted < limit and stop_category is None:
                if last_started is not None and request_start_interval_seconds > 0:
                    remaining = request_start_interval_seconds - (time.monotonic() - last_started)
                    if remaining > 0:
                        time.sleep(remaining)
                row, mode = tasks.popleft()
                future = executor.submit(request_fn, _route_url(row, mode), token=token)
                futures[future] = (row, mode)
                attempted += 1
                last_started = time.monotonic()
            if not futures:
                break
            completed, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in completed:
                row, mode = futures.pop(future)
                persist(future, row, mode)
            if attempted >= limit and not futures:
                break

    return {
        "attempted_requests": attempted,
        "skipped_cached_primary_rows": skipped_cached,
        "walking_fallback_requests": walking_fallbacks,
        "stop_category": stop_category,
        "cache_record_count": cache.count(),
        "raw_response_persisted": False,
        "token_persisted": False,
        "concurrent_workers": max_workers,
        "request_start_interval_seconds": request_start_interval_seconds,
    }
