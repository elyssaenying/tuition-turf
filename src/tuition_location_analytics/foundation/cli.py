from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import pyarrow as pa

from tuition_location_analytics.preflight.common import read_env

from .common import (
    configure_logging,
    file_record,
    log_event,
    scan_foundation_outputs_for_secrets,
    sha256_file,
    write_csv,
    write_json,
    write_parquet,
)
from .context import process_point_source, process_schools
from .geocode import geocode_schools
from .geography import (
    build_population_crosswalk,
    enrich_population_rows,
    process_boundaries,
    write_boundary_geojson,
    write_geoparquet,
)
from .population import process_population
from .reporting import completion_markdown, data_quality_markdown, geography_join_markdown
from .sources import acquire_sources, load_source_config


def _check(
    check_id: str,
    source_id: str,
    table: str,
    status: str,
    observation: str,
    details: Any = None,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "source_id": source_id,
        "table": table,
        "status": status,
        "observation": observation,
        "details": details,
    }


def _build_quality_checks(
    population: dict[str, Any],
    boundaries: dict[str, Any],
    crosswalk: dict[str, Any],
    schools: dict[str, Any],
    mrt: dict[str, Any],
    bus: dict[str, Any],
    s007_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    pq = population["quality"]
    checks.append(
        _check(
            "Q02",
            "S001",
            "population_age_7_16",
            "pass" if pq["source_composite_key_duplicate_count"] == 0 else "fail",
            f"{pq['source_composite_key_duplicate_count']} duplicate source composite keys",
            pq["source_composite_key_duplicate_examples"],
        )
    )
    invalid_population = (
        pq["negative_count"]
        + pq["missing_count_marker_count"]
        + sum(pq["unknown_count_markers"].values())
        + len(pq["incomplete_target_subzones"])
    )
    checks.append(
        _check(
            "Q03",
            "S001",
            "population_proxy_subzone",
            "pass" if invalid_population == 0 else "fail",
            f"{invalid_population} invalid/missing population conditions; {pq['target_age_total_sex_nil_or_negligible_marker_count']} nil-or-negligible markers among target-age Total-sex components treated as zero ({pq['whole_workbook_nil_or_negligible_marker_count']} in the whole workbook)",
        )
    )
    checks.append(
        _check(
            "Q03",
            "S001",
            "population_sex_reconciliation",
            "pass" if pq["sex_set_or_count_missing_count"] == 0 and pq["sex_rounding_discrepancy_max_abs"] <= 10 else "fail",
            f"{pq['sex_set_or_count_missing_count']} missing sex sets; maximum Total-(Males+Females) difference {pq['sex_rounding_discrepancy_max_abs']}",
            pq["sex_rounding_discrepancy_examples"],
        )
    )
    checks.append(
        _check(
            "Q04",
            "S001",
            "population_proxy_subzone",
            "warning",
            pq["rounding_limitation"],
            {
                "national_published_total": pq["national_target_age_published_total"],
                "national_subzone_sum": pq["national_target_age_subzone_sum"],
                "difference": pq["national_target_age_difference"],
                "planning_area_age_max_abs_difference": pq["planning_area_age_reconciliation_max_abs"],
            },
        )
    )
    bq = boundaries["quality"]
    boundary_failures = (
        bq["processed_invalid_geometry_count"]
        + bq["out_of_singapore_bounds_count"]
        + bq["missing_required_field_count"]
        + len(bq["duplicate_subzone_codes"])
        + len(bq["duplicate_geo_ids"])
        + len(bq["planning_area_codes_with_multiple_names"])
        + len(bq["planning_area_names_with_multiple_codes"])
    )
    checks.append(
        _check(
            "Q05",
            "S003",
            "mp2019_subzones",
            "pass" if boundary_failures == 0 else "fail",
            f"{boundary_failures} blocking geometry, bounds, identifier or hierarchy conditions",
            bq,
        )
    )
    checks.append(
        _check(
            "Q05",
            "S003",
            "mp2019_subzones_source_geometry",
            "warning" if bq["source_invalid_geometry_count"] else "pass",
            f"{bq['source_invalid_geometry_count']} source geometries required recorded make_valid repair; {bq['processed_invalid_geometry_count']} processed geometries remain invalid",
            bq["geometry_repairs"],
        )
    )
    jq = crosswalk["summary"]
    checks.append(
        _check(
            "Q05",
            "S001+S003",
            "geography_crosswalk",
            "pass" if jq["unmatched_count"] == 0 and jq["ambiguous_count"] == 0 else "fail",
            f"{jq['matched_count']} matched, {jq['unmatched_count']} unmatched, {jq['ambiguous_count']} ambiguous; no fuzzy matches",
            {"unmatched": jq["unmatched"], "ambiguous": jq["ambiguous"]},
        )
    )
    sq = schools["quality"]
    school_key_failures = (
        len(sq["duplicate_source_record_ids"])
        + len(sq["duplicate_school_ids"])
        + sq["invalid_postal_count"]
        + sum(sq["missing_required_by_field"].values())
    )
    checks.append(
        _check(
            "Q02",
            "S004",
            "schools",
            "pass" if school_key_failures == 0 else "fail",
            f"{school_key_failures} blocking school key/required-field/postal conditions",
            sq,
        )
    )
    checks.append(
        _check(
            "Q05",
            "S004+S007",
            "schools",
            "pass" if sq["coordinate_missing_count"] == 0 else "warning",
            f"{sq['coordinate_bounds_validated_count']} coordinates validated; {sq['coordinate_missing_count']} unresolved or absent",
            {
                "status_counts": sq["coordinate_status_counts"],
                "unresolved_coordinates": sq["unresolved_coordinates"],
            },
        )
    )
    for source_id, table, quality in (("S005", "mrt_exits", mrt["quality"]), ("S006", "bus_stops", bus["quality"])):
        failures = (
            quality["invalid_geometry_count"]
            + quality["out_of_singapore_bounds_count"]
            + quality["missing_required_field_count"]
            + len(quality["duplicate_transit_point_ids"])
            + len(quality["duplicate_source_unique_ids"])
        )
        checks.append(
            _check(
                "Q05",
                source_id,
                table,
                "pass" if failures == 0 else "fail",
                f"{failures} blocking point geometry/key/bounds conditions; {quality['duplicate_coordinate_count']} duplicate coordinates retained for review",
                quality,
            )
        )
        checks.append(
            _check(
                "Q02",
                source_id,
                table,
                "warning" if quality["duplicate_business_keys"] else "pass",
                f"{len(quality['duplicate_business_keys'])} repeated descriptive business keys across unique source point IDs",
                quality["duplicate_business_keys"],
            )
        )
    checks.append(
        _check(
            "Q06",
            "S007",
            "routing_preflight",
            "warning",
            f"walking {s007_summary['walking_success']}/30; PT {s007_summary['pt_success']}/30; PT missing routes {s007_summary['pt_missing_route']}; rate limited {s007_summary['rate_limited_count']}",
            "Missing PT routes require the documented walking/proximity fallback and remain missing; they are not imputed.",
        )
    )
    return checks


def _configured_reference(repo_root: Path, reference: str, *, label: str) -> Path:
    configured = Path(reference)
    if configured.is_absolute():
        raise RuntimeError(f"{label} must be repository-relative")
    resolved = (repo_root / configured).resolve()
    if not resolved.is_relative_to(repo_root.resolve()):
        raise RuntimeError(f"{label} must stay inside the repository")
    if not resolved.is_file():
        raise RuntimeError(f"configured {label} does not exist: {reference}")
    return resolved


def _foundation_paths(repo_root: Path, snapshot_date: str) -> tuple[Path, Path]:
    return (
        repo_root / "data/processed/foundation" / snapshot_date,
        repo_root / "reports/foundation" / snapshot_date,
    )


def _s007_preflight_summary(repo_root: Path, preflight_result_ref: str) -> dict[str, Any]:
    result_path = _configured_reference(
        repo_root, preflight_result_ref, label="preflight_result_ref"
    )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("s007"), dict):
        raise RuntimeError("configured preflight result has no S007 result")
    result = payload["s007"]
    routes = result.get("routes", [])
    return {
        "preflight_result_ref": result_path.relative_to(repo_root.resolve()).as_posix(),
        "preflight_result_sha256": sha256_file(result_path),
        "walking_success": sum(item["mode"] == "walk" and item["category"] == "success" for item in routes),
        "pt_success": sum(item["mode"] == "pt" and item["category"] == "success" for item in routes),
        "pt_missing_route": sum(item["mode"] == "pt" and item["category"] == "missing_route" for item in routes),
        "rate_limited_count": int(result.get("rate_limited_count", 0)),
    }


def _overall_status(checks: list[dict[str, Any]]) -> str:
    return "failed" if any(item["status"] == "fail" for item in checks) else "passed_with_warnings"


def run(
    repo_root: Path,
    *,
    verbose: bool = False,
    credential_values: Iterable[str] | None = None,
) -> dict[str, Any]:
    logger = configure_logging(verbose)
    log_event(logger, "foundation_run_started")
    _, configured_run = load_source_config(repo_root)
    s007_preflight = _s007_preflight_summary(
        repo_root, configured_run["preflight_result_ref"]
    )
    if credential_values is None:
        credential_values = read_env(repo_root / ".env").values()
    credential_values = tuple(credential_values)
    acquired, config = acquire_sources(repo_root)
    for source_id, item in acquired.items():
        log_event(logger, "source_ready", source_id=source_id, status=item["acquisition_status"])

    population = process_population(
        acquired["S001"]["raw_path"],
        target_age_min=int(config["target_ages_inclusive"][0]),
        target_age_max=int(config["target_ages_inclusive"][1]),
        rounding_unit=int(config["population_rounding_unit"]),
    )
    boundaries = process_boundaries(
        acquired["S003"]["raw_path"], config["singapore_wgs84_bounds"]
    )
    population_pairs = [
        {"planning_area_name": record["planning_area_name"], "subzone_name": record["subzone_name"]}
        for record in population["proxy_rows"]
    ]
    crosswalk = build_population_crosswalk(population_pairs, boundaries["records"])
    population_age = enrich_population_rows(population["target_age_rows"], crosswalk["rows"])
    population_proxy = enrich_population_rows(population["proxy_rows"], crosswalk["rows"])

    schools_without_coordinates = process_schools(acquired["S004"]["raw_path"])
    try:
        geocoding = geocode_schools(
            repo_root,
            schools_without_coordinates["records"],
            snapshot_date=config["snapshot_date"],
            pace_seconds=float(config["onemap_search_pace_seconds"]),
            singapore_bounds=config["singapore_wgs84_bounds"],
        )
    except RuntimeError as error:
        geocoding = {
            "records": [],
            "summary": {
                "source_id": "S007",
                "purpose": "Exact-postal coordinate resolution for S004 schools; no routing requests",
                "planned_search_requests": len(schools_without_coordinates["records"]),
                "executed_search_requests": 0,
                "status_counts": {"blocked": len(schools_without_coordinates["records"])},
                "rate_limited_count": 0,
                "request_headers_recorded": False,
                "raw_authentication_response_recorded": False,
                "raw_search_responses_recorded": False,
                "token_persisted": False,
                "matching_rule": "Exact six-digit postal match and one unique returned WGS84 coordinate; no fuzzy match.",
                "limitation": str(error),
            },
        }
    geocode_lookup = {record["school_id"]: record for record in geocoding["records"]}
    schools = process_schools(acquired["S004"]["raw_path"], geocode_lookup)
    mrt = process_point_source(
        acquired["S005"]["raw_path"], source_id="S005", singapore_bounds=config["singapore_wgs84_bounds"]
    )
    bus = process_point_source(
        acquired["S006"]["raw_path"], source_id="S006", singapore_bounds=config["singapore_wgs84_bounds"]
    )
    source_checksums = "|".join(
        acquired[source_id]["metadata"]["checksum"] for source_id in ("S001", "S003", "S004", "S005", "S006")
    )
    run_id = "foundation_" + hashlib.sha256(
        (
            config["pipeline_version"]
            + "|"
            + config["snapshot_date"]
            + "|"
            + s007_preflight["preflight_result_sha256"]
            + "|"
            + source_checksums
        ).encode("utf-8")
    ).hexdigest()[:16]
    processed_dir, report_dir = _foundation_paths(repo_root, config["snapshot_date"])
    processed_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    outputs: list[tuple[Path, int]] = []

    def standard_outputs(name: str, records: list[dict[str, Any]], overrides: dict[str, pa.DataType] | None = None) -> None:
        parquet_path = processed_dir / f"{name}.parquet"
        csv_path = processed_dir / f"{name}.csv"
        write_parquet(parquet_path, records, type_overrides=overrides)
        write_csv(csv_path, records)
        outputs.extend(((parquet_path, len(records)), (csv_path, len(records))))

    standard_outputs("population_age_7_16", population_age)
    standard_outputs("population_proxy_subzone", population_proxy)
    boundary_parquet = processed_dir / "mp2019_subzones.parquet"
    boundary_geojson = processed_dir / "mp2019_subzones.geojson"
    boundary_csv = processed_dir / "mp2019_subzones.csv"
    write_geoparquet(boundary_parquet, boundaries["records"], boundaries["geometries"])
    write_boundary_geojson(boundary_geojson, boundaries["geojson"])
    write_csv(boundary_csv, boundaries["records"])
    outputs.extend(
        (
            (boundary_parquet, len(boundaries["records"])),
            (boundary_geojson, len(boundaries["records"])),
            (boundary_csv, len(boundaries["records"])),
        )
    )
    standard_outputs("geography_crosswalk", crosswalk["rows"])
    standard_outputs(
        "schools",
        schools["records"],
        {
            "longitude_wgs84": pa.float64(),
            "latitude_wgs84": pa.float64(),
            "easting_3414": pa.float64(),
            "northing_3414": pa.float64(),
        },
    )
    for name, point_data in (("mrt_exits", mrt), ("bus_stops", bus)):
        parquet_path = processed_dir / f"{name}.parquet"
        csv_path = processed_dir / f"{name}.csv"
        write_geoparquet(parquet_path, point_data["records"], point_data["geometries"])
        write_csv(csv_path, point_data["records"])
        outputs.extend(((parquet_path, len(point_data["records"])), (csv_path, len(point_data["records"]))))

    geocode_report_path = report_dir / "school-geocode-report.json"
    write_json(
        geocode_report_path,
        {
            "run_id": run_id,
            **geocoding["summary"],
            "unresolved_coordinates": schools["quality"]["unresolved_coordinates"],
        },
    )

    checks = _build_quality_checks(
        population, boundaries, crosswalk, schools, mrt, bus, s007_preflight
    )
    overall_status = "validation_pending"
    quality_report = {
        "run_id": run_id,
        "pipeline_version": config["pipeline_version"],
        "schema_version": config["schema_version"],
        "overall_status": overall_status,
        "checks": checks,
        "source_summaries": {
            "S001": population["quality"],
            "S003": boundaries["quality"],
            "S004": schools["quality"],
            "S005": mrt["quality"],
            "S006": bus["quality"],
            "S007_school_geocoding": geocoding["summary"],
            "S007_routing_preflight": s007_preflight,
        },
    }
    quality_json = report_dir / "data-quality-report.json"
    quality_md = report_dir / "data-quality-report.md"
    write_json(quality_json, quality_report)
    quality_md.write_text(data_quality_markdown(quality_report), encoding="utf-8")

    geography_report = {"run_id": run_id, "summary": crosswalk["summary"]}
    geography_json = report_dir / "geography-join-report.json"
    geography_md = report_dir / "geography-join-report.md"
    write_json(geography_json, geography_report)
    geography_md.write_text(geography_join_markdown(geography_report), encoding="utf-8")

    schema_by_stem = {
        "population_age_7_16": list(population_age[0]) if population_age else [],
        "population_proxy_subzone": list(population_proxy[0]) if population_proxy else [],
        "mp2019_subzones": list(boundaries["records"][0]) + ["geometry"] if boundaries["records"] else [],
        "geography_crosswalk": list(crosswalk["rows"][0]) if crosswalk["rows"] else [],
        "schools": list(schools["records"][0]) if schools["records"] else [],
        "mrt_exits": list(mrt["records"][0]) + ["geometry"] if mrt["records"] else [],
        "bus_stops": list(bus["records"][0]) + ["geometry"] if bus["records"] else [],
    }
    processed_files = [
        {
            **file_record(path, repo_root, row_count),
            "schema_fields": schema_by_stem[path.stem],
        }
        for path, row_count in outputs
    ]
    source_manifest: list[dict[str, Any]] = []
    transformation_by_source = {
        "S001": ["population_age_7_16", "population_proxy_subzone", "geography_crosswalk"],
        "S003": ["mp2019_subzones", "geography_crosswalk"],
        "S004": ["schools"],
        "S005": ["mrt_exits"],
        "S006": ["bus_stops"],
    }
    source_row_counts = {
        "S001": population["quality"]["source_data_row_count"],
        "S003": boundaries["quality"]["source_feature_count"],
        "S004": schools["quality"]["source_record_count"],
        "S005": mrt["quality"]["source_feature_count"],
        "S006": bus["quality"]["source_feature_count"],
    }
    source_schemas = {
        "S001": ["Planning Area", "Subzone", "Age", "Sex", "2025"],
        **{
            source_id: acquired[source_id]["metadata"].get("official_metadata", {}).get("fields")
            for source_id in ("S003", "S004", "S005", "S006")
        },
    }
    for source_id in ("S001", "S003", "S004", "S005", "S006"):
        item = acquired[source_id]
        metadata = item["metadata"]
        source_manifest.append(
            {
                "source_id": source_id,
                "publisher": item["source"]["publisher"],
                "title": item["source"]["title"],
                "landing_url": item["source"]["landing_url"],
                "resource_id": item["source"].get("resource_id"),
                "acquisition_method": item["source"]["method"],
                "acquisition_status": item["acquisition_status"],
                "retrieved_at": metadata.get("retrieved_at"),
                "requested_url": metadata.get("requested_url", item["source"].get("resource_url")),
                "final_download_location": metadata.get(
                    "final_download_location", metadata.get("final_url")
                ),
                "http_status": metadata.get("download_http_status", metadata.get("http_status")),
                "raw_path": item["raw_path"].relative_to(repo_root).as_posix(),
                "snapshot_metadata_path": item["metadata_path"].relative_to(repo_root).as_posix(),
                "raw_byte_size": item["raw_path"].stat().st_size,
                "raw_sha256": sha256_file(item["raw_path"]),
                "raw_schema": source_schemas[source_id],
                "raw_row_count": source_row_counts[source_id],
                "transformations": transformation_by_source[source_id],
                "immutable": True,
            }
        )
    manifest = {
        "run_id": run_id,
        "pipeline_version": config["pipeline_version"],
        "schema_version": config["schema_version"],
        "snapshot_date": config["snapshot_date"],
        "status": overall_status,
        "sources": source_manifest,
        "service_operations": [geocoding["summary"]],
        "processed_files": processed_files,
        "quality_report": quality_json.relative_to(repo_root).as_posix(),
        "geography_join_report": geography_json.relative_to(repo_root).as_posix(),
        "preflight_result_ref": s007_preflight["preflight_result_ref"],
        "preflight_result_sha256": s007_preflight["preflight_result_sha256"],
        "raw_publication_policy": {
            "S001": "excluded; resource-specific raw redistribution permission unestablished",
            "S003": "Singapore Open Data Licence; publish only after final attribution/release review",
            "S004": "Singapore Open Data Licence; publish only after final attribution/release review",
            "S005": "Singapore Open Data Licence; publish only after final attribution/release review",
            "S006": "Singapore Open Data Licence; publish only after final attribution/release review",
        },
    }
    manifest_path = report_dir / "acquisition-manifest.json"
    write_json(manifest_path, manifest)

    completion = {
        "run_id": run_id,
        "status": overall_status,
        "counts": {
            "population_age_rows": len(population_age),
            "population_subzones": len(population_proxy),
            "boundary_subzones": len(boundaries["records"]),
            "schools": len(schools["records"]),
            "schools_with_coordinates": schools["quality"]["coordinate_bounds_validated_count"],
            "mrt_exits": len(mrt["records"]),
            "bus_stops": len(bus["records"]),
            "geography_matches": crosswalk["summary"]["matched_count"],
            "geography_unmatched": crosswalk["summary"]["unmatched_count"],
            "geography_ambiguous": crosswalk["summary"]["ambiguous_count"],
        },
        "s007_preflight": s007_preflight,
        "school_geocoding": geocoding["summary"],
        "unresolved_school_coordinates": schools["quality"]["unresolved_coordinates"],
    }
    completion_path = report_dir / "completion-report.md"
    completion_path.write_text(completion_markdown(completion), encoding="utf-8")

    secret_scan = scan_foundation_outputs_for_secrets(
        repo_root,
        processed_dir=processed_dir,
        report_dir=report_dir,
        credential_values=credential_values,
    )
    checks.append(
        _check(
            "Q01",
            "FOUNDATION",
            "reportable_outputs",
            secret_scan["status"],
            f"generic scan {secret_scan['generic_pattern_scan_status']}; exact-value comparison {secret_scan['exact_credential_comparison_status']}; assurance {secret_scan['assurance']}; {secret_scan['finding_count']} finding files across {secret_scan['scanned_file_count']} scanned text outputs",
            secret_scan,
        )
    )
    overall_status = _overall_status(checks)
    quality_report["overall_status"] = overall_status
    quality_report["source_summaries"]["foundation_secret_scan"] = secret_scan
    manifest["status"] = overall_status
    manifest["foundation_secret_scan"] = secret_scan
    completion["status"] = overall_status
    completion["foundation_secret_scan"] = secret_scan
    write_json(quality_json, quality_report)
    quality_md.write_text(data_quality_markdown(quality_report), encoding="utf-8")
    write_json(manifest_path, manifest)
    completion_path.write_text(completion_markdown(completion), encoding="utf-8")
    log_event(logger, "foundation_run_completed", run_id=run_id, status=overall_status)
    return {
        "run_id": run_id,
        "status": overall_status,
        "manifest": manifest_path.relative_to(repo_root).as_posix(),
        "quality_report": quality_json.relative_to(repo_root).as_posix(),
        "geography_report": geography_json.relative_to(repo_root).as_posix(),
        "completion_report": completion_path.relative_to(repo_root).as_posix(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Acquire and process the approved foundational nationwide sources S001/S003-S006"
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    result = run(args.repo_root.resolve(), verbose=args.verbose)
    print(json.dumps(result, sort_keys=True))
    if result["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
