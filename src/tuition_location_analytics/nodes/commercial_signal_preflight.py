from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely.geometry import Point, shape

from tuition_location_analytics.foundation.common import (
    file_record,
    sha256_file,
    utc_now,
    write_csv,
    write_json,
)
from tuition_location_analytics.foundation.sources import ApiPacer, acquire_data_gov_source


SINGAPORE_BOUNDS_WGS84 = (103.55, 1.13, 104.10, 1.50)


def _repo_file(repo_root: Path, reference: str) -> Path:
    path = (repo_root / reference).resolve()
    if not path.is_relative_to(repo_root.resolve()) or not path.is_file():
        raise RuntimeError(f"configured input is missing or outside repository: {reference}")
    return path


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_pharmacy_points(
    payload: dict[str, Any],
    *,
    bounds: tuple[float, float, float, float] = SINGAPORE_BOUNDS_WGS84,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if payload.get("type") != "FeatureCollection" or not isinstance(
        payload.get("features"), list
    ):
        raise RuntimeError("S034 is not a GeoJSON FeatureCollection")

    minimum_longitude, minimum_latitude, maximum_longitude, maximum_latitude = bounds
    valid: list[dict[str, Any]] = []
    invalid_geometry_count = 0
    out_of_bounds_count = 0
    missing_object_id_count = 0
    object_ids: list[str] = []

    for feature in payload["features"]:
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates")
        if (
            geometry.get("type") != "Point"
            or not isinstance(coordinates, list)
            or len(coordinates) < 2
        ):
            invalid_geometry_count += 1
            continue
        try:
            longitude = float(coordinates[0])
            latitude = float(coordinates[1])
        except (TypeError, ValueError):
            invalid_geometry_count += 1
            continue
        if not math.isfinite(longitude) or not math.isfinite(latitude):
            invalid_geometry_count += 1
            continue
        if not (
            minimum_longitude <= longitude <= maximum_longitude
            and minimum_latitude <= latitude <= maximum_latitude
        ):
            out_of_bounds_count += 1
            continue

        properties = feature.get("properties") or {}
        object_id = str(properties.get("OBJECTID_1") or "").strip()
        missing_object_id_count += int(not object_id)
        if object_id:
            object_ids.append(object_id)
        valid.append(
            {
                "object_id": object_id or None,
                "pharmacy_name": str(properties.get("PHARMACY_NAME") or "").strip(),
                "postal_code": str(properties.get("POSTAL_CODE") or "").strip(),
                "longitude_wgs84": longitude,
                "latitude_wgs84": latitude,
            }
        )

    duplicate_object_ids = sorted(
        key for key, count in Counter(object_ids).items() if count > 1
    )
    source_feature_count = len(payload["features"])
    valid_rate = len(valid) / source_feature_count if source_feature_count else 0.0
    quality = {
        "source_feature_count": source_feature_count,
        "valid_in_bounds_point_count": len(valid),
        "valid_in_bounds_point_rate": valid_rate,
        "invalid_geometry_count": invalid_geometry_count,
        "out_of_bounds_count": out_of_bounds_count,
        "missing_object_id_count": missing_object_id_count,
        "duplicate_object_ids": duplicate_object_ids,
    }
    return valid, quality


def _load_region_polygons(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise RuntimeError("subzone input is not a GeoJSON FeatureCollection")
    polygons: list[dict[str, Any]] = []
    for feature in payload.get("features", []):
        properties = feature.get("properties") or {}
        region_name = str(properties.get("region_name") or "").strip()
        geometry = shape(feature.get("geometry"))
        if not region_name or geometry.is_empty:
            raise RuntimeError("subzone input has a missing region or geometry")
        polygons.append({"region_name": region_name, "geometry": geometry})
    return polygons


def _assign_region(point: Point, polygons: list[dict[str, Any]]) -> str | None:
    matches = [row["region_name"] for row in polygons if row["geometry"].covers(point)]
    if not matches:
        return None
    return sorted(matches)[0]


def _source_age_months(last_updated_at: str, snapshot_date: str) -> float:
    last_updated = datetime.fromisoformat(last_updated_at).date()
    snapshot = date.fromisoformat(snapshot_date)
    return max(0.0, (snapshot - last_updated).days / 30.4375)


def build_node_coverage(
    candidates: list[dict[str, str]],
    exits: list[dict[str, str]],
    pharmacies: list[dict[str, Any]],
    region_polygons: list[dict[str, Any]],
    buffers_metres: list[int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3414", always_xy=True)
    exits_by_complex: dict[str, list[Point]] = defaultdict(list)
    for row in exits:
        exits_by_complex[row["station_complex_id"]].append(
            Point(float(row["easting_3414"]), float(row["northing_3414"]))
        )

    pharmacy_points_metric: list[Point] = []
    source_points_by_region: Counter[str] = Counter()
    unassigned_source_point_count = 0
    for pharmacy in pharmacies:
        point_wgs84 = Point(
            float(pharmacy["longitude_wgs84"]), float(pharmacy["latitude_wgs84"])
        )
        region = _assign_region(point_wgs84, region_polygons)
        if region is None:
            unassigned_source_point_count += 1
        else:
            source_points_by_region[region] += 1
        pharmacy_points_metric.append(Point(*transformer.transform(point_wgs84.x, point_wgs84.y)))

    records: list[dict[str, Any]] = []
    unassigned_node_count = 0
    for node in candidates:
        node_exits = exits_by_complex.get(node["station_complex_id"], [])
        if not node_exits:
            raise RuntimeError(f"node has no station exits: {node['commercial_node_id']}")
        anchor = Point(
            float(node["anchor_longitude_wgs84"]),
            float(node["anchor_latitude_wgs84"]),
        )
        region = _assign_region(anchor, region_polygons)
        unassigned_node_count += int(region is None)
        distances = [
            min(exit_point.distance(pharmacy_point) for exit_point in node_exits)
            for pharmacy_point in pharmacy_points_metric
        ]
        nearest_distance = min(distances) if distances else None
        for buffer_metres in buffers_metres:
            count = sum(distance <= buffer_metres for distance in distances)
            records.append(
                {
                    "commercial_node_id": node["commercial_node_id"],
                    "station_complex_id": node["station_complex_id"],
                    "node_name": node["node_name"],
                    "planning_region": region,
                    "source_id": "S034",
                    "evidence_signal_id": "hsa_registered_retail_pharmacy_proximity",
                    "independent_signal_key": "licensed_retail_presence",
                    "buffer_metres": buffer_metres,
                    "proximity_method": "union_of_straight_line_buffers_from_all_valid_station_exits_epsg3414",
                    "measurement_status": "observed",
                    "positive_signal": count > 0,
                    "distinct_pharmacy_count": count,
                    "nearest_pharmacy_distance_metres": (
                        None if nearest_distance is None else round(nearest_distance, 3)
                    ),
                    "missing_reason": None,
                    "interpretation_limit": "Licensed public-facing retail-presence proxy only; absence is not proof of no commercial activity and presence does not prove tuition-premises suitability.",
                }
            )

    diagnostics = {
        "source_points_by_region": dict(sorted(source_points_by_region.items())),
        "unassigned_source_point_count": unassigned_source_point_count,
        "unassigned_source_point_rate": (
            unassigned_source_point_count / len(pharmacies) if pharmacies else 1.0
        ),
        "unassigned_node_count": unassigned_node_count,
    }
    return records, diagnostics


def evaluate_gates(
    config: dict[str, Any],
    source_quality: dict[str, Any],
    diagnostics: dict[str, Any],
    coverage_records: list[dict[str, Any]],
    *,
    source_age_months: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    thresholds = config["predeclared_acceptance_gates"]
    primary = int(config["method"]["primary_buffer_metres"])
    primary_records = [row for row in coverage_records if row["buffer_metres"] == primary]
    by_region: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in primary_records:
        if row["planning_region"]:
            by_region[row["planning_region"]].append(row)

    positive_count = sum(bool(row["positive_signal"]) for row in primary_records)
    national_rate = positive_count / len(primary_records) if primary_records else 0.0
    region_metrics = {
        region: {
            "node_count": len(rows),
            "positive_node_count": sum(bool(row["positive_signal"]) for row in rows),
            "coverage_rate": (
                sum(bool(row["positive_signal"]) for row in rows) / len(rows)
                if rows
                else 0.0
            ),
        }
        for region, rows in sorted(by_region.items())
    }
    source_points_by_region = diagnostics["source_points_by_region"]

    checks = [
        (
            "feature_count",
            source_quality["source_feature_count"] >= thresholds["minimum_official_feature_count"],
            source_quality["source_feature_count"],
            f">={thresholds['minimum_official_feature_count']}",
        ),
        (
            "valid_in_bounds_point_rate",
            source_quality["valid_in_bounds_point_rate"]
            >= thresholds["minimum_valid_in_bounds_point_rate"],
            source_quality["valid_in_bounds_point_rate"],
            f">={thresholds['minimum_valid_in_bounds_point_rate']}",
        ),
        (
            "source_age_months",
            source_age_months <= thresholds["maximum_source_age_months"],
            source_age_months,
            f"<={thresholds['maximum_source_age_months']}",
        ),
        (
            "planning_region_count",
            len(source_points_by_region) >= thresholds["required_planning_regions"],
            len(source_points_by_region),
            f">={thresholds['required_planning_regions']}",
        ),
        (
            "minimum_source_points_per_region",
            bool(source_points_by_region)
            and min(source_points_by_region.values())
            >= thresholds["minimum_source_points_per_region"],
            min(source_points_by_region.values()) if source_points_by_region else 0,
            f">={thresholds['minimum_source_points_per_region']}",
        ),
        (
            "unassigned_source_point_rate",
            diagnostics["unassigned_source_point_rate"]
            <= thresholds["maximum_unassigned_source_point_rate"],
            diagnostics["unassigned_source_point_rate"],
            f"<={thresholds['maximum_unassigned_source_point_rate']}",
        ),
        (
            "unassigned_node_count",
            diagnostics["unassigned_node_count"]
            <= thresholds["maximum_unassigned_node_count"],
            diagnostics["unassigned_node_count"],
            f"<={thresholds['maximum_unassigned_node_count']}",
        ),
        (
            "national_node_coverage_rate",
            national_rate >= thresholds["minimum_national_node_coverage_rate_at_primary_buffer"],
            national_rate,
            f">={thresholds['minimum_national_node_coverage_rate_at_primary_buffer']}",
        ),
        (
            "minimum_region_node_coverage_rate",
            len(region_metrics) >= thresholds["required_planning_regions"]
            and min(row["coverage_rate"] for row in region_metrics.values())
            >= thresholds["minimum_node_coverage_rate_per_region_at_primary_buffer"],
            min((row["coverage_rate"] for row in region_metrics.values()), default=0.0),
            f">={thresholds['minimum_node_coverage_rate_per_region_at_primary_buffer']}",
        ),
        (
            "positive_nodes_nationally",
            positive_count >= thresholds["minimum_positive_nodes_nationally"],
            positive_count,
            f">={thresholds['minimum_positive_nodes_nationally']}",
        ),
        (
            "minimum_positive_nodes_per_region",
            len(region_metrics) >= thresholds["required_planning_regions"]
            and min(row["positive_node_count"] for row in region_metrics.values())
            >= thresholds["minimum_positive_nodes_per_region"],
            min((row["positive_node_count"] for row in region_metrics.values()), default=0),
            f">={thresholds['minimum_positive_nodes_per_region']}",
        ),
    ]
    gates = [
        {"gate": name, "status": "pass" if passed else "fail", "observed": observed, "required": required}
        for name, passed, observed, required in checks
    ]
    metrics = {
        "primary_buffer_metres": primary,
        "node_count": len(primary_records),
        "positive_node_count": positive_count,
        "national_node_coverage_rate": national_rate,
        "regions": region_metrics,
    }
    return gates, metrics


def _markdown(result: dict[str, Any]) -> str:
    accepted = result["decision"] == "accepted"
    lines = [
        "# Second commercial-signal preflight",
        "",
        f"Decision: **{'ACCEPTED' if accepted else 'REJECTED'}**  ",
        f"Source: `{result['source_id']}` — {result['source_title']}  ",
        f"Snapshot: `{result['snapshot_date']}`  ",
        "",
        "## Plain-English meaning",
        "",
        (
            "The source passed every rule frozen before its node-level results were inspected. It may be used as an independent positive commercial-presence signal."
            if accepted
            else "The source failed at least one rule frozen before its node-level results were inspected. It must not be used to qualify nodes."
        ),
        "A nearby licensed pharmacy shows current public-facing retail activity. It does not prove that a tuition unit is available, affordable or permitted. No nearby pharmacy does not prove that commercial activity is absent.",
        "",
        "## Gate results",
        "",
        "| Gate | Status | Observed | Required |",
        "|---|---|---:|---:|",
    ]
    for gate in result["gates"]:
        observed = gate["observed"]
        if isinstance(observed, float):
            observed = f"{observed:.3f}"
        lines.append(f"| {gate['gate']} | {gate['status']} | {observed} | {gate['required']} |")
    lines.extend(
        [
            "",
            "## Regional coverage at 800 m",
            "",
            "| Planning region | Pharmacy points | MRT areas | Positive MRT areas | Coverage |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    point_counts = result["diagnostics"]["source_points_by_region"]
    for region, metrics in result["coverage_metrics"]["regions"].items():
        lines.append(
            f"| {region} | {point_counts.get(region, 0)} | {metrics['node_count']} | "
            f"{metrics['positive_node_count']} | {metrics['coverage_rate']:.1%} |"
        )
    lines.extend(
        [
            "",
            "## Method",
            "",
            "- Each MRT area uses the union of straight-line buffers around every preserved station exit.",
            "- A node is positive when at least one distinct HSA-registered retail pharmacy falls within the buffer.",
            "- The 800 m band is the qualification band; 400 m is retained as a stricter sensitivity view.",
            "- This preflight does not inspect tuition competitors and does not select candidate winners.",
        ]
    )
    return "\n".join(lines) + "\n"


def run(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    config_path = repo_root / "config/nodes/second_signal_preflight.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    source_config = json.loads((repo_root / "config/nodes/sources.json").read_text(encoding="utf-8"))
    sources = {row["source_id"]: row for row in source_config["sources"]}
    source = sources[config["source_id"]]
    acquisition = acquire_data_gov_source(
        repo_root,
        source,
        config["snapshot_date"],
        ApiPacer(0.25),
    )

    payload = json.loads(acquisition["raw_path"].read_text(encoding="utf-8"))
    pharmacies, source_quality = parse_pharmacy_points(payload)
    paths = {key: _repo_file(repo_root, ref) for key, ref in config["inputs"].items()}
    candidates = _read_csv(paths["candidate_nodes_ref"])
    exits = _read_csv(paths["station_exits_ref"])
    region_polygons = _load_region_polygons(paths["subzones_ref"])
    coverage, diagnostics = build_node_coverage(
        candidates,
        exits,
        pharmacies,
        region_polygons,
        [int(value) for value in config["method"]["buffers_metres"]],
    )

    official_metadata = acquisition["metadata"].get("official_metadata") or {}
    last_updated_at = str(official_metadata.get("lastUpdatedAt") or "")
    if not last_updated_at:
        raise RuntimeError("S034 official metadata is missing lastUpdatedAt")
    age_months = _source_age_months(last_updated_at, config["snapshot_date"])
    gates, coverage_metrics = evaluate_gates(
        config,
        source_quality,
        diagnostics,
        coverage,
        source_age_months=age_months,
    )
    decision = "accepted" if all(gate["status"] == "pass" for gate in gates) else "rejected"

    processed_dir = repo_root / "data/processed/nodes" / config["snapshot_date"]
    report_dir = repo_root / "reports/nodes" / config["snapshot_date"]
    coverage_path = processed_dir / "second_commercial_signal_node_coverage.csv"
    report_path = report_dir / "second-commercial-signal-preflight.json"
    markdown_path = report_dir / "second-commercial-signal-preflight.md"
    write_csv(coverage_path, coverage)
    result = {
        "run_at": utc_now(),
        "decision": decision,
        "source_id": source["source_id"],
        "source_title": source["title"],
        "snapshot_date": config["snapshot_date"],
        "config_ref": config_path.relative_to(repo_root).as_posix(),
        "config_sha256": sha256_file(config_path),
        "source_snapshot_ref": acquisition["raw_path"].relative_to(repo_root).as_posix(),
        "source_snapshot_sha256": acquisition["metadata"]["checksum"],
        "source_last_updated_at": last_updated_at,
        "source_age_months": age_months,
        "source_quality": source_quality,
        "diagnostics": diagnostics,
        "coverage_metrics": coverage_metrics,
        "gates": gates,
        "limitations": config["prohibited_uses"],
        "outputs": [file_record(coverage_path, repo_root, len(coverage))],
    }
    write_json(report_path, result)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_markdown(result), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight a second commercial-presence signal")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = run(args.repo_root)
    print(json.dumps({"decision": result["decision"], "gates": result["gates"]}, indent=2))


if __name__ == "__main__":
    main()
