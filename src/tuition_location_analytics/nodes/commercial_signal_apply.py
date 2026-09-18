from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from tuition_location_analytics.foundation.common import write_csv, write_parquet


METHOD_VERSION = "station-complex-commercial-evidence-v5-hsa-pharmacy"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _optional_float(value: Any) -> float | None:
    return None if value in {None, ""} else float(value)


def _optional_int(value: Any) -> int | None:
    return None if value in {None, ""} else int(value)


def _optional_bool(value: Any) -> bool | None:
    if value in {None, ""}:
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def apply_second_signal(
    candidates: list[dict[str, Any]],
    original_evidence: list[dict[str, Any]],
    pharmacy_coverage: list[dict[str, Any]],
    *,
    primary_buffer_metres: int = 800,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    zoning = [
        row for row in original_evidence if row["independent_signal_key"] == "official_land_use_zoning"
    ]
    zoning_by_key = {
        (row["commercial_node_id"], int(row["buffer_metres"])): row for row in zoning
    }
    pharmacy_by_key = {
        (row["commercial_node_id"], int(row["buffer_metres"])): row
        for row in pharmacy_coverage
    }

    expected_keys = set(zoning_by_key)
    if set(pharmacy_by_key) != expected_keys:
        raise RuntimeError("pharmacy coverage does not exactly match node/buffer zoning keys")

    evidence: list[dict[str, Any]] = []
    for key in sorted(expected_keys):
        zoning_row = dict(zoning_by_key[key])
        zoning_row["buffer_metres"] = int(zoning_row["buffer_metres"])
        zoning_row["positive_signal"] = _optional_bool(zoning_row["positive_signal"])
        zoning_row["relevant_feature_count"] = _optional_int(zoning_row["relevant_feature_count"])
        for field in (
            "relevant_area_sqm",
            "buffer_area_sqm",
            "relevant_area_share",
            "nearest_relevant_feature_distance_metres",
        ):
            zoning_row[field] = _optional_float(zoning_row[field])
        evidence.append(zoning_row)

        pharmacy = pharmacy_by_key[key]
        evidence.append(
            {
                "commercial_node_id": pharmacy["commercial_node_id"],
                "station_complex_id": pharmacy["station_complex_id"],
                "evidence_signal_id": pharmacy["evidence_signal_id"],
                "independent_signal_key": pharmacy["independent_signal_key"],
                "buffer_metres": int(pharmacy["buffer_metres"]),
                "proximity_method": pharmacy["proximity_method"],
                "measurement_status": pharmacy["measurement_status"],
                "positive_signal": _optional_bool(pharmacy["positive_signal"]),
                "source_ids_json": json.dumps([pharmacy["source_id"]]),
                "relevant_feature_count": int(pharmacy["distinct_pharmacy_count"]),
                "relevant_area_sqm": None,
                "buffer_area_sqm": zoning_row["buffer_area_sqm"],
                "relevant_area_share": None,
                "nearest_relevant_feature_distance_metres": _optional_float(
                    pharmacy["nearest_pharmacy_distance_metres"]
                ),
                "category_area_sqm_json": None,
                "missing_reason": None,
                "interpretation_limit": pharmacy["interpretation_limit"],
            }
        )

    primary_by_node: dict[str, list[dict[str, Any]]] = {}
    for row in evidence:
        if row["buffer_metres"] == primary_buffer_metres:
            primary_by_node.setdefault(row["commercial_node_id"], []).append(row)

    updated: list[dict[str, Any]] = []
    for raw in candidates:
        node = dict(raw)
        node_id = node["commercial_node_id"]
        rows = primary_by_node.get(node_id, [])
        if len(rows) != 2 or any(row["measurement_status"] != "observed" for row in rows):
            raise RuntimeError(f"node does not have two observed primary-band signals: {node_id}")
        positive_keys = sorted(
            row["independent_signal_key"] for row in rows if row["positive_signal"] is True
        )
        node["node_definition_version"] = METHOD_VERSION
        node["anchor_longitude_wgs84"] = float(node["anchor_longitude_wgs84"])
        node["anchor_latitude_wgs84"] = float(node["anchor_latitude_wgs84"])
        node["exit_count"] = int(node["exit_count"])
        node["commercial_signal_count"] = len(positive_keys)
        node["positive_signal_keys_json"] = json.dumps(positive_keys)
        node["missing_signal_keys_json"] = json.dumps([])
        node["qualification_status"] = (
            "qualified" if len(positive_keys) >= 2 else "provisional"
        )
        node["commercial_evidence_status"] = "complete"
        node["qualification_rule"] = (
            "At least 2 independent positive signal families at the 800 m evidence band."
        )
        node["commercial_context_limitation"] = (
            "Zoning plus licensed retail presence establish two independent commercial-context signals only; they do not prove occupancy, availability, rent or tuition-use eligibility."
        )
        updated.append(node)

    qualified_count = sum(row["qualification_status"] == "qualified" for row in updated)
    quality = {
        "node_count": len(updated),
        "evidence_row_count": len(evidence),
        "signals_per_node_at_primary_buffer": 2,
        "qualified_node_count": qualified_count,
        "provisional_node_count": len(updated) - qualified_count,
        "missing_measurement_count": sum(
            row["measurement_status"] != "observed" for row in evidence
        ),
    }
    return updated, evidence, quality


def run(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    report = json.loads(
        (repo_root / "reports/nodes/2026-09-18/second-commercial-signal-preflight.json").read_text(
            encoding="utf-8"
        )
    )
    if report.get("decision") != "accepted" or any(
        gate.get("status") != "pass" for gate in report.get("gates", [])
    ):
        raise RuntimeError("second commercial signal has not passed every frozen preflight gate")

    candidates = _read_csv(
        repo_root / "data/processed/nodes/2026-09-13/commercial_node_candidates.csv"
    )
    evidence = _read_csv(
        repo_root / "data/processed/nodes/2026-09-13/commercial_node_evidence.csv"
    )
    coverage = _read_csv(
        repo_root / "data/processed/nodes/2026-09-18/second_commercial_signal_node_coverage.csv"
    )
    updated, updated_evidence, quality = apply_second_signal(candidates, evidence, coverage)

    output_dir = repo_root / "data/processed/nodes/2026-09-18"
    write_csv(output_dir / "commercial_node_candidates.csv", updated)
    write_parquet(output_dir / "commercial_node_candidates.parquet", updated)
    write_csv(output_dir / "commercial_node_evidence.csv", updated_evidence)
    write_parquet(output_dir / "commercial_node_evidence.parquet", updated_evidence)
    return quality


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply an accepted second commercial signal")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(run(args.repo_root), indent=2))


if __name__ == "__main__":
    main()
