from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .common import sanitize_url, sha256_file, utc_now, write_json

USER_AGENT = "tuition-location-analytics-foundation/0.1"
DATA_GOV_METADATA = "https://api-production.data.gov.sg/v2/public/api/datasets/{resource_id}/metadata"
DATA_GOV_POLL = "https://api-open.data.gov.sg/v1/public/api/datasets/{resource_id}/poll-download"
DATA_GOV_DATASTORE = "https://data.gov.sg/api/action/datastore_search"
RAW_DIRECTORIES = {
    "S003": "s003_mp2019_subzone_boundary",
    "S004": "s004_schools_2026",
    "S005": "s005_mrt_station_exits",
    "S006": "s006_bus_stops",
}


def source_snapshot_paths(
    repo_root: Path, source: dict[str, Any], snapshot_date: str
) -> tuple[Path, Path]:
    raw_directory = source.get("raw_directory") or RAW_DIRECTORIES[source["source_id"]]
    raw_dir = repo_root / "data/raw" / raw_directory / snapshot_date
    return raw_dir / source["raw_filename"], raw_dir / "snapshot-metadata.json"


@dataclass
class ApiPacer:
    minimum_interval_seconds: float
    last_request_monotonic: float | None = None

    def wait(self) -> None:
        if self.last_request_monotonic is not None:
            elapsed = time.monotonic() - self.last_request_monotonic
            if elapsed < self.minimum_interval_seconds:
                time.sleep(self.minimum_interval_seconds - elapsed)
        self.last_request_monotonic = time.monotonic()


def load_source_config(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    source_config = json.loads(
        (repo_root / "config/foundation/sources.json").read_text(encoding="utf-8")
    )
    run_config = json.loads(
        (repo_root / "config/foundation/run.json").read_text(encoding="utf-8")
    )
    snapshot_date = run_config.get("snapshot_date")
    if not isinstance(snapshot_date, str):
        raise RuntimeError("foundation snapshot_date must be configured")
    try:
        date.fromisoformat(snapshot_date)
    except ValueError:
        raise RuntimeError("foundation snapshot_date must be an ISO date") from None
    if not isinstance(run_config.get("preflight_result_ref"), str):
        raise RuntimeError("foundation preflight_result_ref must be configured")
    return source_config, run_config


def _safe_headers(response: Any) -> dict[str, str]:
    allowed = {
        "content-type",
        "content-length",
        "content-disposition",
        "last-modified",
        "etag",
        "date",
    }
    return {
        key.lower(): value
        for key, value in response.headers.items()
        if key.lower() in allowed
    }


def _request_bytes(url: str, *, timeout: int = 120) -> tuple[bytes, int, str, dict[str, str]]:
    request = urllib.request.Request(url, headers={"Accept": "*/*", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(), response.status, response.geturl(), _safe_headers(response)


def _request_json(url: str, pacer: ApiPacer) -> tuple[dict[str, Any], int, str, dict[str, str]]:
    pacer.wait()
    raw, status, final_url, headers = _request_bytes(url)
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("official API returned a non-object JSON payload")
    return payload, status, final_url, headers


def _selected_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
        raise RuntimeError("data.gov.sg metadata response did not report success")
    data = payload["data"]
    selected: dict[str, Any] = {
        key: data.get(key)
        for key in (
            "datasetId",
            "name",
            "format",
            "lastUpdatedAt",
            "managedBy",
            "coverageStart",
            "coverageEnd",
            "datasetSize",
        )
    }
    if isinstance(data.get("geoJsonMetadata"), dict):
        selected["fields"] = [
            item.get("attribute") for item in data["geoJsonMetadata"].get("properties", [])
        ]
    elif isinstance(data.get("columnMetadata"), dict):
        mapping = data["columnMetadata"].get("map", {})
        order = data["columnMetadata"].get("order", [])
        selected["fields"] = [mapping.get(item, item) for item in order]
    return selected


def _existing_snapshot(raw_path: Path, metadata_path: Path) -> dict[str, Any] | None:
    if not raw_path.exists() and not metadata_path.exists():
        return None
    if not raw_path.exists() or not metadata_path.exists():
        raise RuntimeError(f"incomplete immutable snapshot at {raw_path.parent}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    observed = sha256_file(raw_path)
    if observed != metadata.get("checksum"):
        raise RuntimeError(f"immutable snapshot checksum mismatch for {raw_path.name}")
    return metadata


def _write_new_snapshot(raw_path: Path, metadata_path: Path, raw: bytes, metadata: dict[str, Any]) -> None:
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = raw_path.with_suffix(raw_path.suffix + ".part")
    if temporary.exists():
        temporary.unlink()
    try:
        with temporary.open("xb") as handle:
            handle.write(raw)
        os.replace(temporary, raw_path)
        write_json(metadata_path, metadata)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def acquire_data_gov_source(
    repo_root: Path,
    source: dict[str, Any],
    snapshot_date: str,
    pacer: ApiPacer,
) -> dict[str, Any]:
    source_id = source["source_id"]
    raw_path, metadata_path = source_snapshot_paths(repo_root, source, snapshot_date)
    existing = _existing_snapshot(raw_path, metadata_path)
    if existing is not None:
        return {
            "source": source,
            "raw_path": raw_path,
            "metadata_path": metadata_path,
            "metadata": existing,
            "acquisition_status": "reused_immutable_snapshot",
        }

    resource_id = source["resource_id"]
    try:
        metadata_payload, metadata_status, _, metadata_headers = _request_json(
            DATA_GOV_METADATA.format(resource_id=resource_id), pacer
        )
        official_metadata = _selected_metadata(metadata_payload)
        retrieved_at = utc_now()
        if source["method"] == "data_gov_poll_download":
            descriptor, descriptor_status, _, _ = _request_json(
                DATA_GOV_POLL.format(resource_id=resource_id), pacer
            )
            download_url = descriptor.get("data", {}).get("url")
            if descriptor.get("code") != 0 or not isinstance(download_url, str):
                raise RuntimeError("data.gov.sg download descriptor did not contain a URL")
            raw, raw_status, final_url, raw_headers = _request_bytes(download_url)
            requested_url = DATA_GOV_POLL.format(resource_id=resource_id)
            descriptor_http_status = descriptor_status
        elif source["method"] == "data_gov_datastore":
            params = urllib.parse.urlencode({"resource_id": resource_id, "limit": 1000})
            requested_url = f"{DATA_GOV_DATASTORE}?{params}"
            pacer.wait()
            raw, raw_status, final_url, raw_headers = _request_bytes(requested_url)
            descriptor_http_status = None
        else:
            raise RuntimeError(f"unsupported acquisition method for {source_id}")
    except (OSError, urllib.error.URLError, json.JSONDecodeError, RuntimeError) as error:
        raise RuntimeError(f"{source_id} official acquisition failed: {type(error).__name__}") from None

    checksum = hashlib_sha256(raw)
    snapshot_metadata = {
        "source_id": source_id,
        "publisher": source["publisher"],
        "title": source["title"],
        "resource_id": resource_id,
        "landing_url": source["landing_url"],
        "requested_url": requested_url,
        "final_download_location": sanitize_url(final_url),
        "retrieved_at": retrieved_at,
        "metadata_http_status": metadata_status,
        "descriptor_http_status": descriptor_http_status,
        "download_http_status": raw_status,
        "metadata_response_headers": metadata_headers,
        "download_response_headers": raw_headers,
        "official_metadata": official_metadata,
        "byte_size": len(raw),
        "checksum_algorithm": "sha256",
        "checksum": checksum,
        "storage_ref": raw_path.relative_to(repo_root).as_posix(),
        "immutable": True,
        "licence": "Singapore Open Data Licence",
    }
    _write_new_snapshot(raw_path, metadata_path, raw, snapshot_metadata)
    return {
        "source": source,
        "raw_path": raw_path,
        "metadata_path": metadata_path,
        "metadata": snapshot_metadata,
        "acquisition_status": "downloaded",
    }


def hashlib_sha256(raw: bytes) -> str:
    import hashlib

    return hashlib.sha256(raw).hexdigest()


def acquire_sources(repo_root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    source_config, run_config = load_source_config(repo_root)
    snapshot_date = run_config["snapshot_date"]
    by_id = {item["source_id"]: item for item in source_config["sources"]}
    s001 = by_id["S001"]
    s001_path, s001_metadata_path = source_snapshot_paths(
        repo_root, s001, snapshot_date
    )
    if not s001_path.exists() or not s001_metadata_path.exists():
        raise RuntimeError("S001 immutable preflight snapshot or metadata is missing")
    s001_metadata = json.loads(s001_metadata_path.read_text(encoding="utf-8"))
    if sha256_file(s001_path) != s001_metadata.get("checksum"):
        raise RuntimeError("S001 immutable snapshot checksum mismatch")
    acquired: dict[str, dict[str, Any]] = {
        "S001": {
            "source": s001,
            "raw_path": s001_path,
            "metadata_path": s001_metadata_path,
            "metadata": s001_metadata,
            "acquisition_status": "reused_immutable_snapshot",
        }
    }
    pacer = ApiPacer(float(run_config["data_gov_api_pace_seconds"]))
    for source_id in ("S003", "S004", "S005", "S006"):
        acquired[source_id] = acquire_data_gov_source(
            repo_root, by_id[source_id], snapshot_date, pacer
        )
    return acquired, run_config
