from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import urllib.parse
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import pyarrow as pa
import pyarrow.parquet as pq


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    if temporary.exists():
        temporary.unlink()
    with temporary.open("xb") as handle:
        handle.write(payload)
    os.replace(temporary, path)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(records[0]) if records else []
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(records)
    os.replace(temporary, path)


def write_parquet(
    path: Path,
    records: list[dict[str, Any]],
    *,
    type_overrides: dict[str, pa.DataType] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if records and type_overrides:
        columns: dict[str, pa.Array] = {}
        for name in records[0]:
            values = [record.get(name) for record in records]
            columns[name] = pa.array(values, type=type_overrides.get(name))
        table = pa.table(columns)
    else:
        table = pa.Table.from_pylist(records)
    temporary = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table, temporary, compression="zstd")
    os.replace(temporary, path)


def normalize_name(value: str) -> str:
    return " ".join(value.strip().upper().split())


def sanitize_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def file_record(path: Path, repo_root: Path, row_count: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": path.relative_to(repo_root).as_posix(),
        "byte_size": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    if row_count is not None:
        result["row_count"] = row_count
    return result


def duplicate_values(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


_REPORTABLE_TEXT_SUFFIXES = {".csv", ".geojson", ".json", ".md", ".txt"}
_SECRET_PATTERNS = (
    re.compile(r"(?i)authorization\s*[:=]\s*(?:bearer\s+)?[^\s,}\]]+"),
    re.compile(r'(?i)["\']?(?:access_token|password|api_key|secret)["\']?\s*[:=]\s*["\']?[^\s,"\'}\]]+'),
)


def scan_foundation_outputs_for_secrets(
    repo_root: Path,
    *,
    processed_dir: Path,
    report_dir: Path,
    credential_values: Iterable[str],
) -> dict[str, Any]:
    """Scan reportable foundation text outputs without retaining matched text.

    The caller supplies credential values already loaded in memory. Binary outputs
    are deliberately skipped, while the two narrowly scoped output roots keep raw
    data, caches, virtual environments and local credential files out of scope.
    """
    roots = (processed_dir.resolve(), report_dir.resolve())
    repository = repo_root.resolve()
    secrets = tuple(
        value.encode("utf-8")
        for value in credential_values
        if isinstance(value, str) and value
    )
    generic_pattern_finding_paths: set[str] = set()
    exact_credential_finding_paths: set[str] = set()
    scanned_file_count = 0
    skipped_binary_file_count = 0

    for root in roots:
        if not root.is_relative_to(repository):
            raise ValueError(f"secret-scan root is outside repository: {root}")
        if not root.exists():
            continue
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            if path.suffix.lower() not in _REPORTABLE_TEXT_SUFFIXES:
                skipped_binary_file_count += 1
                continue
            payload = path.read_bytes()
            scanned_file_count += 1
            credential_match = any(secret in payload for secret in secrets)
            try:
                text_payload = payload.decode("utf-8")
            except UnicodeDecodeError:
                skipped_binary_file_count += 1
                continue
            pattern_match = any(pattern.search(text_payload) for pattern in _SECRET_PATTERNS)
            relative_path = path.relative_to(repository).as_posix()
            if pattern_match:
                generic_pattern_finding_paths.add(relative_path)
            if credential_match:
                exact_credential_finding_paths.add(relative_path)

    credential_values_available = bool(secrets)
    finding_paths = generic_pattern_finding_paths | exact_credential_finding_paths
    if finding_paths:
        status = "fail"
    elif credential_values_available:
        status = "pass"
    else:
        status = "warning"
    return {
        "status": status,
        "assurance": "full" if credential_values_available else "limited",
        "credential_values_available": credential_values_available,
        "generic_pattern_scan_status": (
            "fail" if generic_pattern_finding_paths else "pass"
        ),
        "exact_credential_comparison_status": (
            "performed" if credential_values_available else "not_performed_credentials_unavailable"
        ),
        "generic_pattern_finding_count": len(generic_pattern_finding_paths),
        "generic_pattern_finding_paths": sorted(generic_pattern_finding_paths),
        "exact_credential_finding_count": len(exact_credential_finding_paths),
        "exact_credential_finding_paths": sorted(exact_credential_finding_paths),
        "finding_count": len(finding_paths),
        "finding_paths": sorted(finding_paths),
        "scanned_file_count": scanned_file_count,
        "skipped_binary_file_count": skipped_binary_file_count,
        "scope": [root.relative_to(repository).as_posix() for root in roots],
    }


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        fields = getattr(record, "structured_fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        return json.dumps(payload, sort_keys=True)


def configure_logging(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("tuition_location_analytics.foundation")
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    return logger


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    logger.info(event, extra={"structured_fields": fields})
