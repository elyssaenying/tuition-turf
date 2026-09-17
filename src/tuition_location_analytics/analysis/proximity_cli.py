from __future__ import annotations

import argparse
import hashlib
import html
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import Transformer
from shapely import wkb
from shapely.geometry import Point
from shapely.ops import transform

from tuition_location_analytics.foundation.common import (
    file_record,
    sha256_file,
    utc_now,
    write_csv,
    write_json,
    write_parquet,
)

from .proximity import (
    METHOD,
    add_demand_ranks,
    area_weighted_population,
    exit_union_catchment,
    point_count,
)


def _repo_file(repo_root: Path, reference: str) -> Path:
    path = (repo_root / reference).resolve()
    if not path.is_relative_to(repo_root.resolve()) or not path.is_file():
        raise RuntimeError(f"configured input is missing or outside repository: {reference}")
    return path


def _load_config(repo_root: Path) -> tuple[Path, dict[str, Any]]:
    path = repo_root / "config/analysis/proximity_baseline.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    radii = config.get("proximity_radii_metres")
    if radii != [800, 1200]:
        raise RuntimeError("proximity baseline must retain the frozen 800 m band and 1,200 m sensitivity")
    if config.get("method") != METHOD:
        raise RuntimeError("proximity method label is invalid")
    return path, config


def _horizontal_bar_svg(records: list[dict[str, Any]], *, top_n: int = 20) -> str:
    selected = records[:top_n]
    width, left, right, bar_height, gap = 1040, 280, 90, 22, 9
    height = 90 + len(selected) * (bar_height + gap)
    plot_width = width - left - right
    maximum = max(float(row["proximity_target_population_proxy_800m"]) for row in selected) or 1
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#1f2937}.title{font-size:22px;font-weight:700}.label{font-size:12px}.value{font-size:12px;font-weight:700}.note{font-size:11px;fill:#6b7280}</style>',
        '<text class="title" x="20" y="32">Top MRT areas by 800 m population proximity proxy</text>',
        '<text class="note" x="20" y="53">Area-weighted ages 7–16 resident proxy; straight-line exit-union catchment, not travel time or enrolment</text>',
    ]
    for index, row in enumerate(selected):
        y = 72 + index * (bar_height + gap)
        value = float(row["proximity_target_population_proxy_800m"])
        bar_width = value / maximum * plot_width
        name = html.escape(str(row["node_name"]).replace(" MRT STATION", ""))
        parts.append(f'<text class="label" x="{left - 10}" y="{y + 16}" text-anchor="end">{index + 1}. {name}</text>')
        parts.append(f'<rect x="{left}" y="{y}" width="{bar_width:.1f}" height="{bar_height}" rx="3" fill="#2563eb"/>')
        parts.append(f'<text class="value" x="{left + bar_width + 7:.1f}" y="{y + 16}">{value:,.0f}</text>')
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def _summary_markdown(run_id: str, records: list[dict[str, Any]], quality: dict[str, Any]) -> str:
    top = records[:10]
    lines = [
        "# National MRT-area proximity-demand baseline",
        "",
        f"Run ID: `{run_id}`  ",
        f"Status: `{quality['status']}`  ",
        f"Nodes analysed: **{len(records)}**",
        "",
        "## What this result means",
        "",
        "This is the first nationwide comparison of the 146 approved MRT-area candidates. It estimates the ages 7–16 resident population spatially overlapping the union of straight-line buffers around every preserved station exit. Population is allocated by intersected subzone area.",
        "",
        "It is a **proximity proxy**, not public-transport travel time, observed enrolment, customers or a final location recommendation. Overlapping node catchments are evaluated independently and must not be summed.",
        "",
        "## Highest 800 m proxy values",
        "",
        "| Rank | MRT area | Population proxy | 1,200 m sensitivity | Bus stops within 800 m | Schools within 800 m |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for row in top:
        lines.append(
            f"| {row['population_proxy_800m_rank']} | {row['node_name']} | "
            f"{row['proximity_target_population_proxy_800m']:.0f} | "
            f"{row['proximity_target_population_proxy_1200m']:.0f} | "
            f"{row['bus_stop_count_800m']} | {row['school_context_count_800m']} |"
        )
    lines.extend(
        [
            "",
            "## Quality and limitations",
            "",
            f"- All {quality['node_count']} current node candidates were processed and have station exits.",
            f"- Input target-age population proxy: {quality['national_target_population_proxy']:,}.",
            f"- Monotonic sensitivity check (1,200 m ≥ 800 m): {'passed' if quality['sensitivity_monotonic'] else 'failed'}.",
            "- Uniform population within each subzone is an approximation; residential land is not evenly distributed.",
            "- Seven schools with unresolved coordinates are omitted from spatial school counts.",
            "- Bus-stop and school counts are context only and are not a measured accessibility score.",
            "- National OneMap routing, H2, competition, finance and final recommendations remain outstanding.",
            "",
            "## Next analytical step",
            "",
            "Implement the frozen transit/walking accessibility calculation and compare it with this straight-line baseline. Do not narrow to final candidates from this proxy alone.",
        ]
    )
    return "\n".join(lines) + "\n"


def run(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    config_path, config = _load_config(repo_root)
    paths = {key: _repo_file(repo_root, reference) for key, reference in config["inputs"].items()}

    candidates = pq.read_table(paths["commercial_node_candidates"]).to_pylist()
    exits_raw = pq.read_table(paths["station_complex_exits"]).to_pylist()
    subzones_raw = pq.read_table(paths["mp2019_subzones"]).to_pylist()
    population_raw = pq.read_table(paths["population_proxy_subzone"]).to_pylist()
    bus_raw = pq.read_table(paths["bus_stops"]).to_pylist()
    schools_raw = pq.read_table(paths["schools"]).to_pylist()

    population = {row["geo_id"]: row for row in population_raw}
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3414", always_xy=True)
    subzones: list[dict[str, Any]] = []
    for row in subzones_raw:
        geometry_3414 = transform(transformer.transform, wkb.loads(row["geometry"]))
        pop_row = population[row["geo_id"]]
        subzones.append(
            {
                "geo_id": row["geo_id"],
                "planning_area_name": row["planning_area_name"],
                "region_name": row["region_name"],
                "geometry_3414": geometry_3414,
                "target_population_proxy": pop_row["accessible_target_population_proxy"],
            }
        )

    exits: dict[str, list[Point]] = defaultdict(list)
    for row in exits_raw:
        exits[row["station_complex_id"]].append(
            Point(float(row["easting_3414"]), float(row["northing_3414"]))
        )
    bus_points = [Point(float(row["easting_3414"]), float(row["northing_3414"])) for row in bus_raw]
    school_points = [
        Point(float(row["easting_3414"]), float(row["northing_3414"]))
        for row in schools_raw
        if row.get("easting_3414") is not None and row.get("northing_3414") is not None
    ]

    records: list[dict[str, Any]] = []
    for node in candidates:
        node_exits = exits.get(node["station_complex_id"], [])
        catchments = {
            radius: exit_union_catchment(node_exits, radius)
            for radius in config["proximity_radii_metres"]
        }
        pop_800, subzones_800 = area_weighted_population(catchments[800], subzones)
        pop_1200, subzones_1200 = area_weighted_population(catchments[1200], subzones)
        anchor = Point(
            float(node["anchor_longitude_wgs84"]),
            float(node["anchor_latitude_wgs84"]),
        )
        anchor_3414 = Point(*transformer.transform(anchor.x, anchor.y))
        containing = [row for row in subzones if row["geometry_3414"].covers(anchor_3414)]
        context = containing[0] if len(containing) == 1 else None
        records.append(
            {
                "commercial_node_id": node["commercial_node_id"],
                "station_complex_id": node["station_complex_id"],
                "node_name": node["node_name"],
                "operational_status": node["operational_status"],
                "qualification_status": node["qualification_status"],
                "planning_area_name_at_anchor": context["planning_area_name"] if context else None,
                "region_name_at_anchor": context["region_name"] if context else None,
                "catchment_method": METHOD,
                "population_allocation_method": "subzone_area_weighted_uniform_distribution_assumption",
                "proximity_target_population_proxy_800m": pop_800,
                "proximity_target_population_proxy_1200m": pop_1200,
                "intersected_subzone_count_800m": subzones_800,
                "intersected_subzone_count_1200m": subzones_1200,
                "bus_stop_count_800m": point_count(catchments[800], bus_points),
                "bus_stop_count_1200m": point_count(catchments[1200], bus_points),
                "school_context_count_800m": point_count(catchments[800], school_points),
                "school_context_count_1200m": point_count(catchments[1200], school_points),
                "quality_flags_json": json.dumps(
                    (["anchor_geography_unresolved"] if context is None else [])
                    + (["zero_800m_population_proxy"] if pop_800 == 0 else [])
                    + (["node_not_formally_qualified"] if node["qualification_status"] != "qualified" else []),
                    separators=(",", ":"),
                ),
            }
        )

    records = add_demand_ranks(records)
    national_population = int(sum(float(row["accessible_target_population_proxy"] or 0) for row in population_raw))
    quality = {
        "status": "passed_with_warnings",
        "node_count": len(records),
        "expected_node_count": 146,
        "all_nodes_have_exits": all(exits.get(row["station_complex_id"]) for row in candidates),
        "duplicate_node_id_count": len(records) - len({row["commercial_node_id"] for row in records}),
        "anchor_geography_unresolved_count": sum(row["planning_area_name_at_anchor"] is None for row in records),
        "negative_population_proxy_count": sum(row["proximity_target_population_proxy_800m"] < 0 for row in records),
        "proxy_exceeds_national_population_count": sum(row["proximity_target_population_proxy_1200m"] > national_population for row in records),
        "sensitivity_monotonic": all(
            row["proximity_target_population_proxy_1200m"] + 1e-9 >= row["proximity_target_population_proxy_800m"]
            for row in records
        ),
        "national_target_population_proxy": national_population,
        "school_coordinate_resolved_count": len(school_points),
        "school_coordinate_unresolved_count": len(schools_raw) - len(school_points),
        "warning": "straight-line proximity baseline only; national transit/walking routing has not been executed",
    }
    hard_fail = (
        quality["node_count"] != quality["expected_node_count"]
        or not quality["all_nodes_have_exits"]
        or quality["duplicate_node_id_count"]
        or quality["anchor_geography_unresolved_count"]
        or quality["negative_population_proxy_count"]
        or quality["proxy_exceeds_national_population_count"]
        or not quality["sensitivity_monotonic"]
    )
    if hard_fail:
        quality["status"] = "failed"
        raise RuntimeError("proximity baseline quality gates failed")

    digest = "|".join([sha256_file(config_path), *[sha256_file(path) for path in paths.values()]])
    run_id = "proximity_baseline_" + hashlib.sha256(digest.encode("utf-8")).hexdigest()[:16]
    processed_dir = repo_root / "data/processed/analysis" / config["analysis_date"] / run_id
    report_dir = repo_root / "reports/analysis" / config["analysis_date"] / run_id
    if processed_dir.exists() or report_dir.exists():
        raise RuntimeError(f"analysis run directory already exists: {run_id}")
    processed_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)

    parquet_path = processed_dir / "node_proximity_metrics.parquet"
    csv_path = processed_dir / "node_proximity_metrics.csv"
    float_fields = {
        "proximity_target_population_proxy_800m": pa.float64(),
        "proximity_target_population_proxy_1200m": pa.float64(),
        "population_proxy_800m_percentile": pa.float64(),
    }
    write_parquet(parquet_path, records, type_overrides=float_fields)
    write_csv(csv_path, records)
    quality_path = report_dir / "data-quality-report.json"
    write_json(quality_path, quality)
    report_path = report_dir / "analysis-summary.md"
    report_path.write_text(_summary_markdown(run_id, records, quality), encoding="utf-8")
    chart_path = report_dir / "top-20-population-proxy.svg"
    chart_path.write_text(_horizontal_bar_svg(records), encoding="utf-8")

    output_records = [
        file_record(parquet_path, repo_root, len(records)),
        file_record(csv_path, repo_root, len(records)),
        file_record(quality_path, repo_root),
        file_record(report_path, repo_root),
        file_record(chart_path, repo_root),
    ]
    manifest_path = report_dir / "manifest.json"
    manifest = {
        "run_id": run_id,
        "generated_at": utc_now(),
        "analysis_date": config["analysis_date"],
        "method": METHOD,
        "status": quality["status"],
        "input_files": [file_record(path, repo_root) for path in paths.values()] + [file_record(config_path, repo_root)],
        "output_files": output_records,
        "limitations": [
            "straight-line proximity proxy only; not public-transport or walking travel time",
            "uniform within-subzone population allocation assumption",
            "node catchments overlap and cannot be summed",
            "not a shortlist, ranking recommendation or demand forecast",
        ],
    }
    write_json(manifest_path, manifest)
    return {"run_id": run_id, "processed_dir": str(processed_dir), "report_dir": str(report_dir), "quality": quality, "top_nodes": records[:10]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the national straight-line proximity-demand baseline")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    result = run(Path(args.repo_root))
    print(json.dumps({"run_id": result["run_id"], "status": result["quality"]["status"], "node_count": result["quality"]["node_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
