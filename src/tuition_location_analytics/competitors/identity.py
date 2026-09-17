from __future__ import annotations

import hashlib
import re

from tuition_location_analytics.foundation.common import normalize_name

_UNIT_PATTERN = re.compile(r"#\s*(\d+)\s*-\s*(\w+)")
_WHITESPACE = re.compile(r"\s+")
_PARENTHETICAL = re.compile(r"\s*\([^)]*\)")
_UNIT_SUFFIX = re.compile(r"\s*#\s*[A-Z0-9]+\s*-\s*[A-Z0-9/]+.*$")
_LEADING_BLOCK = re.compile(r"^BLK\s+")
_BUILDING_ABBREVIATIONS = (
    (re.compile(r"\bLOR\b"), "LORONG"),
    (re.compile(r"\bST\b"), "STREET"),
    (re.compile(r"\bAVE\b"), "AVENUE"),
    (re.compile(r"\bRD\b"), "ROAD"),
    (re.compile(r"\bDR\b"), "DRIVE"),
)


def normalize_brand_name(value: str) -> str:
    """Case/whitespace normalization only; never a fuzzy/destructive merge."""
    return normalize_name(value)


def normalize_address(value: str) -> str:
    """Uppercase, collapse whitespace, standardise unit-number spacing.

    This is a Unicode-aware, case/whitespace normalization only. It never merges
    two addresses that differ in block number, street name or unit number, and it
    never guesses a missing unit number.
    """
    text = _WHITESPACE.sub(" ", value.strip().upper())
    text = _UNIT_PATTERN.sub(lambda m: f"#{m.group(1)}-{m.group(2)}", text)
    return text


def normalize_building_address(value: str) -> str:
    """Return a narrowly normalised building-address comparison key.

    This supports an evidence-qualified identity review only. It removes a
    leading ``Blk``, trailing unit and parenthetical place label, and expands a
    closed list of common road abbreviations. It never changes a building or
    street number and is not a general fuzzy-address matcher.
    """
    text = normalize_address(value)
    text = _PARENTHETICAL.sub("", text)
    text = _UNIT_SUFFIX.sub("", text)
    text = _LEADING_BLOCK.sub("", text)
    text = text.replace(",", " ")
    for pattern, replacement in _BUILDING_ABBREVIATIONS:
        text = pattern.sub(replacement, text)
    return _WHITESPACE.sub(" ", text).strip()


def normalize_postal_code(value: str | None) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    if len(digits) == 5:
        digits = digits.zfill(6)
    if len(digits) != 6:
        return None
    return digits


def brand_id(normalized_brand_name: str) -> str:
    digest = hashlib.sha256(normalized_brand_name.encode("utf-8")).hexdigest()[:16]
    return "BRAND_" + digest.upper()


def branch_id(normalized_brand_name: str, normalized_address: str, unit: str | None) -> str:
    key = "\x1f".join((normalized_brand_name, normalized_address, unit or ""))
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return "BRANCH_" + digest.upper()


def offering_id(branch_id_value: str, subject: str, level: str) -> str:
    key = "\x1f".join((branch_id_value, normalize_name(subject), normalize_name(level)))
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return "OFFER_" + digest.upper()


def evidence_id(entity_id: str, source_id: str, observed_at: str, observation_type: str) -> str:
    key = "\x1f".join((entity_id, source_id, observed_at, observation_type))
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return "EVID_" + digest.upper()


def query_id(planning_area_code: str, channel: str, query_text: str) -> str:
    key = "\x1f".join((planning_area_code, channel, query_text))
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return "QRY_" + digest.upper()


def review_id(entity_type: str, entity_id: str, issue_category: str) -> str:
    key = "\x1f".join((entity_type, entity_id, issue_category))
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return "CREV_" + digest.upper()
