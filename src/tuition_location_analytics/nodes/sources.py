from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from tuition_location_analytics.foundation.sources import (
    ApiPacer,
    acquire_data_gov_source,
    acquire_direct_url_source,
)


def load_node_config(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    source_config = json.loads(
        (repo_root / "config/nodes/sources.json").read_text(encoding="utf-8")
    )
    run_config = json.loads(
        (repo_root / "config/nodes/run.json").read_text(encoding="utf-8")
    )
    snapshot_date = run_config.get("snapshot_date")
    if not isinstance(snapshot_date, str):
        raise RuntimeError("node snapshot_date must be configured")
    try:
        parsed_date = date.fromisoformat(snapshot_date)
    except ValueError:
        raise RuntimeError("node snapshot_date must be an ISO date") from None
    if parsed_date.isoformat() != snapshot_date:
        raise RuntimeError("node snapshot_date must use YYYY-MM-DD")
    for key in ("foundation_manifest_ref", "foundation_mrt_exits_ref"):
        if not isinstance(run_config.get(key), str):
            raise RuntimeError(f"node {key} must be configured")
    return source_config, run_config


def acquire_node_sources(
    repo_root: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    source_config, run_config = load_node_config(repo_root)
    pacer = ApiPacer(13.0)
    acquired: dict[str, dict[str, Any]] = {}
    for source in source_config["sources"]:
        if source["method"] == "direct_url_with_expected_checksum":
            acquired[source["source_id"]] = acquire_direct_url_source(
                repo_root,
                source,
                run_config["snapshot_date"],
            )
        else:
            acquired[source["source_id"]] = acquire_data_gov_source(
                repo_root,
                source,
                run_config["snapshot_date"],
                pacer,
            )
    return acquired, run_config
