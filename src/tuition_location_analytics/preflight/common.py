from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

SECRET_KEY_NAMES = {"ONEMAP_EMAIL", "ONEMAP_EMAIL_PASSWORD"}
SECRET_PATTERNS = (
    re.compile(r"(?i)authorization\s*[:=]\s*(?:bearer\s+)?[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"(?i)access[_-]?token\s*[:=]\s*[\"']?[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in SECRET_KEY_NAMES:
            values[key] = value.strip().strip("\"").strip("'")
    return values


def contains_secret_like(text: str, known_secrets: Iterable[str] = ()) -> bool:
    for secret in known_secrets:
        if secret and secret in text:
            return True
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def scan_reportable_files(repo_root: Path, known_secrets: Iterable[str] = ()) -> list[str]:
    excluded_parts = {".git", ".venv", "__pycache__", "data"}
    excluded_names = {".env"}
    findings: list[str] = []
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file() or path.name in excluded_names:
            continue
        if any(part in excluded_parts for part in path.relative_to(repo_root).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if contains_secret_like(text, known_secrets):
            findings.append(path.relative_to(repo_root).as_posix())
    return findings

