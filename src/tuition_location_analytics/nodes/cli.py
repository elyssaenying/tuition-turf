from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import pyarrow as pa
import pyarrow.parquet as pq

from tuition_location_analytics.foundation.common import (
    file_record,
    scan_foundation_outputs_for_secrets,
    sha256_file,
    write_csv,
    write_json,
    write_parquet,
)
from tuition_location_analytics.preflight.common import read_env

from .landuse import build_commercial_nodes, process_land_use
from .reporting import (
    commercial_method_markdown,
    completion_markdown,
    quality_markdown,
    station_audit_markdown,
)
from .sources import acquire_node_sources, load_node_config
from .stations import build_station_complexes, process_train_name_rows


def _repo_file(repo_root: Path, reference: str, label: str) -> Path:
    path = (repo_root / reference).resolve()
    if not path.is_relative_to(repo_root.resolve()) or not path.is_file():
        raise RuntimeError(f"configured {label} is missing or outside the repository")
    return path


def _check(
    check_id: str,
    table: str,
    status: str,
    observation: str,
    details: Any = None,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "table": table,
        "status": status,
        "observation": observation,
        "details": details,
    }


def _overall_status(checks: list[dict[str, Any]]) -> str:
    if any(check["status"] == "fail" for check in checks):
        return "failed"
    if any(check["status"] == "warning" for check in checks):
        return "passed_with_warnings"
    return "passed"


def run(
    repo_root: Path,
    *,
    credential_values: Iterable[str] | None = None,
) -> dict[str, Any]:
    _, configured = load_node_config(repo_root)
    foundation_manifest_path = _repo_file(
        repo_root, configured["foundation_manifest_ref"], "foundation_manifest_ref"
    )
    mrt_path = _repo_file(
        repo_root, configured["foundation_mrt_exits_ref"], "foundation_mrt_exits_ref"
    )
    foundation_manifest = json.loads(foundation_manifest_path.read_text(encoding="utf-8"))
    mrt_manifest_records = [
        item
        for item in foundation_manifest.get("processed_files", [])
        if item.get("path") == configured["foundation_mrt_exits_ref"]
    ]
    if len(mrt_manifest_records) != 1:
        raise RuntimeError("foundation manifest does not identify the configured MRT exit input")
    if sha256_file(mrt_path) != mrt_manifest_records[0]["sha256"]:
        raise RuntimeError("foundation MRT exit checksum does not match its manifest")
    if credential_values is None:
        credential_values = read_env(repo_root / ".env").values()
    credential_values = tuple(credential_values)

    acquired, run_config = acquire_node_sources(repo_root)
    exits = pq.read_table(mrt_path).drop(["geometry"]).to_pylist()
    train_payload = json.loads(acquired["S026"]["raw_path"].read_text(encoding="utf-8"))
    train_names = process_train_name_rows(train_payload)
    overrides_path = _repo_file(repo_root, run_config["station_overrides_ref"], "station_overrides_ref")
    dispositions_path = _repo_file(
        repo_root, run_config["review_dispositions_ref"], "review_dispositions_ref"
    )
    operational_status_path = _repo_file(
        repo_root,
        run_config["operational_status_evidence_ref"],
        "operational_status_evidence_ref",
    )
    system_map_roster_path = _repo_file(
        repo_root,
        run_config["system_map_roster_ref"],
        "system_map_roster_ref",
    )
    overrides_config = json.loads(overrides_path.read_text(encoding="utf-8"))
    dispositions_config = json.loads(dispositions_path.read_text(encoding="utf-8"))
    operational_status_config = json.loads(operational_status_path.read_text(encoding="utf-8"))
    system_map_roster_config = json.loads(system_map_roster_path.read_text(encoding="utf-8"))
    for entry in overrides_config["overrides"]:
        entry.setdefault("override_config_version", overrides_config["override_config_version"])
    station_data = build_station_complexes(
        exits,
        train_names["records"],
        dispersion_review_threshold_metres=float(
            run_config["station_dispersion_review_threshold_metres"]
        ),
        implausible_extent_threshold_metres=float(
            run_config["station_implausible_extent_threshold_metres"]
        ),
        station_overrides=overrides_config["overrides"],
        review_dispositions=dispositions_config["dispositions"],
        operational_status_evidence=operational_status_config,
        system_map_roster=system_map_roster_config,
    )
    land_use = process_land_use(
        acquired["S027"]["raw_path"], run_config["accepted_land_use_categories"]
    )
    commercial = build_commercial_nodes(
        station_data["complexes"],
        station_data["memberships"],
        station_data["review_items"],
        land_use,
        buffer_metres=[int(value) for value in run_config["commercial_buffer_metres"]],
        minimum_independent_signals=int(
            run_config["minimum_independent_signals_for_qualified"]
        ),
    )

    input_digest = "|".join(
        [
            sha256_file(mrt_path),
            acquired["S026"]["metadata"]["checksum"],
            acquired["S027"]["metadata"]["checksum"],
            sha256_file(overrides_path),
            sha256_file(dispositions_path),
            sha256_file(operational_status_path),
            sha256_file(system_map_roster_path),
            hashlib.sha256(
                json.dumps(run_config, sort_keys=True).encode("utf-8")
            ).hexdigest(),
        ]
    )
    run_id = "nodes_" + hashlib.sha256(input_digest.encode("utf-8")).hexdigest()[:16]
    processed_dir = repo_root / "data/processed/nodes" / run_config["snapshot_date"]
    report_dir = repo_root / "reports/nodes" / run_config["snapshot_date"]
    processed_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    output_specs = [
        ("station_complexes", station_data["complexes"]),
        ("station_complex_exits", station_data["memberships"]),
        ("station_complex_id_crosswalk", station_data["station_complex_id_crosswalk"]),
        ("commercial_node_candidates", commercial["candidates"]),
        ("commercial_node_evidence", commercial["evidence"]),
        ("node_review_queue", commercial["review_items"]),
    ]
    output_paths: list[tuple[Path, int]] = []
    float_fields = {
        name: pa.float64()
        for name in (
            "representative_longitude_wgs84",
            "representative_latitude_wgs84",
            "representative_easting_3414",
            "representative_northing_3414",
            "centroid_longitude_wgs84",
            "centroid_latitude_wgs84",
            "centroid_easting_3414",
            "centroid_northing_3414",
            "minimum_easting_3414",
            "minimum_northing_3414",
            "maximum_easting_3414",
            "maximum_northing_3414",
            "maximum_pairwise_exit_distance_metres",
            "longitude_wgs84",
            "latitude_wgs84",
            "easting_3414",
            "northing_3414",
            "anchor_longitude_wgs84",
            "anchor_latitude_wgs84",
            "relevant_area_sqm",
            "buffer_area_sqm",
            "relevant_area_share",
            "nearest_relevant_feature_distance_metres",
        )
    }
    for name, records in output_specs:
        parquet_path = processed_dir / f"{name}.parquet"
        csv_path = processed_dir / f"{name}.csv"
        overrides = {
            field: value for field, value in float_fields.items() if records and field in records[0]
        }
        write_parquet(parquet_path, records, type_overrides=overrides)
        write_csv(csv_path, records)
        output_paths.extend(((parquet_path, len(records)), (csv_path, len(records))))

    inspection_path = processed_dir / "node_inspection.geojson"
    write_json(
        inspection_path,
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": row["commercial_node_id"],
                    "geometry": {
                        "type": "Point",
                        "coordinates": [
                            row["anchor_longitude_wgs84"],
                            row["anchor_latitude_wgs84"],
                        ],
                    },
                    "properties": {
                        key: value
                        for key, value in row.items()
                        if key not in {"anchor_longitude_wgs84", "anchor_latitude_wgs84"}
                    },
                }
                for row in commercial["candidates"]
            ],
        },
    )
    output_paths.append((inspection_path, len(commercial["candidates"])))

    station_audit = {
        "run_id": run_id,
        "quality": station_data["quality"],
        "station_complex_id_crosswalk": station_data["station_complex_id_crosswalk"],
        "override_config_version": overrides_config["override_config_version"],
        "disposition_config_version": dispositions_config["disposition_config_version"],
    }
    commercial_method = {
        "run_id": run_id,
        "accepted_land_use_categories": run_config["accepted_land_use_categories"],
        "minimum_independent_signals_for_qualified": run_config[
            "minimum_independent_signals_for_qualified"
        ],
        "buffer_metres": run_config["commercial_buffer_metres"],
        "land_use_quality": land_use["quality"],
        "commercial_quality": commercial["quality"],
        "candidate_source_assessments": [
            {
                "candidate": "HDB Property Information plus HDB Existing Building",
                "decision": "rejected_for_this_phase",
                "reason": "No deterministic shared identifier or address join; large-scale geocoding was not authorised without a separate preflight.",
            },
            {
                "candidate": "OneMap thematic layers",
                "decision": "deferred",
                "reason": "Authenticated service inspected, but no necessary nationwide commercial theme was verified for this run.",
            },
        ],
        "second_independent_signal_validation_protocol": {
            "status": "documented_not_implemented",
            "reason_not_implemented_now": "A nationwide HDB commercial-building join or comparable geocoding exercise was explicitly out of scope for this bounded correction; MP2025 zoning remains the only implemented signal family, so no node in this run may be marked qualified.",
            "protocol": [
                "1. Freeze a predeclared expanded shortlist of candidate nodes (provisional plus needs_manual_review nodes worth testing) before looking at any second-signal result, so the source of the shortlist cannot be chosen to fit a preferred outcome.",
                "2. Use one current, legally reusable and independently verifiable commercial-presence source that is not itself a source of tuition-competitor evidence and not MP2025 zoning (for example a licensed/open business-registration-with-address feed, a permitted commercial-directory export, or an authorised OneMap thematic commercial layer, subject to its own source-feasibility and licence check before use).",
                "3. Validate every node on the predeclared shortlist against that source using the same buffer methodology and thresholds as the zoning signal; do not selectively validate only the nodes that already look preferred.",
                "4. Record measurement_status/positive_signal/missing_reason for every shortlist node exactly as the zoning evidence rows do, so missing evidence stays null rather than being treated as a negative or a zero.",
                "5. If any shortlisted candidate fails the second-signal check, remove it and recompute the shortlist from the remaining predeclared pool; repeat validation on the recomputed shortlist rather than patching the result.",
                "6. Repeat steps 3-5 until the eligible shortlist is stable (no further removals).",
                "7. A node may only move from provisional to qualified once it has at least two independent positive signal families evaluated this way; zoning bands (400 m/800 m) still count as one family, never two.",
                "8. None of this establishes occupancy, current availability, quoted rent or premises permission; it only raises confidence that a commercial-use signal is genuinely independent of zoning classification.",
            ],
        },
    }
    grouping_json = report_dir / "station-grouping-audit.json"
    grouping_md = report_dir / "station-grouping-audit.md"
    method_json = report_dir / "commercial-evidence-methodology.json"
    method_md = report_dir / "commercial-evidence-methodology.md"
    write_json(grouping_json, station_audit)
    grouping_md.write_text(station_audit_markdown(station_audit), encoding="utf-8")
    write_json(method_json, commercial_method)
    method_md.write_text(commercial_method_markdown(commercial_method), encoding="utf-8")

    station_quality = station_data["quality"]
    land_quality = land_use["quality"]
    commercial_quality = commercial["quality"]
    checks = [
        _check(
            "NQ01",
            "station_complex_exits",
            "pass"
            if not station_quality["duplicate_membership_exit_ids"]
            and not station_quality["missing_membership_exit_ids"]
            and not station_quality["unexpected_membership_exit_ids"]
            else "fail",
            f"{station_quality['membership_row_count']}/{station_quality['input_exit_count']} source exits preserved exactly once",
            station_quality,
        ),
        _check(
            "NQ02",
            "station_complexes",
            "warning" if station_quality["manual_review_complex_count"] else "pass",
            f"{station_quality['station_complex_count']} exact-name complexes; {station_quality['manual_review_complex_count']} carry review flags",
            station_quality,
        ),
        _check(
            "NQ03",
            "station_complexes",
            "warning" if station_quality["s026_unmatched_complex_count"] else "pass",
            f"S026 corroborated {station_quality['s026_exact_match_complex_count']} complexes; {station_quality['s026_unmatched_complex_count']} unmatched complexes retained",
            train_names["quality"],
        ),
        _check(
            "NQ04",
            "mp2025_relevant_land_use",
            (
                "fail"
                if land_quality["missing_relevant_object_id_count"]
                or land_quality["duplicate_relevant_object_ids"]
                else "warning"
                if land_quality["source_invalid_geometry_count"]
                else "pass"
            ),
            f"{land_quality['relevant_feature_count']} accepted-category features from {land_quality['source_feature_count']} MP2025 features; {land_quality['source_invalid_geometry_count']} invalid source geometries, none silently used without validation/repair",
            land_quality,
        ),
        _check(
            "NQ05",
            "commercial_node_candidates",
            "pass"
            if commercial_quality["qualified_nodes_without_minimum_signals"] == 0
            and not commercial_quality["missing_evidence_treated_as_zero"]
            else "fail",
            f"{commercial_quality['commercial_node_candidate_count']} MRT candidates; statuses {commercial_quality['qualification_status_counts']}; missing evidence remains null",
            commercial_quality,
        ),
        _check(
            "NQ07",
            "station_overrides",
            "fail" if station_quality["unused_station_override_labels"] else "pass",
            f"{station_quality['station_override_source_label_count']} station-override labels applied; {len(station_quality['unused_station_override_labels'])} configured override labels were not found in this exit snapshot",
            station_quality["unused_station_override_labels"],
        ),
        _check(
            "NQ10",
            "operational_status_evidence",
            "fail" if station_quality["unused_known_operational_exceptions"] else "pass",
            f"{len(station_quality['known_operational_exceptions_applied'])} known operational exceptions applied "
            f"(S026 plays no role in operational_status; identity/name/code/line corroboration only); "
            f"{len(station_quality['unused_known_operational_exceptions'])} configured known exceptions were not found in this exit snapshot; "
            f"{station_quality['system_map_roster_names_matched_count']} system-map roster "
            f"({station_quality['system_map_roster_source_id']} v{station_quality['system_map_roster_version']}) names matched a complex in this snapshot",
            {
                "unused_known_operational_exceptions": station_quality["unused_known_operational_exceptions"],
            },
        ),
        _check(
            "NQ08",
            "station_complexes",
            "pass"
            if all(
                row["operational_status"]
                in {
                    "verified_operational",
                    "verified_opening_within_decision_horizon",
                    "not_operational",
                    "unresolved",
                }
                for row in station_data["complexes"]
            )
            else "fail",
            f"operational_status counts {station_quality['operational_status_counts']}",
            station_quality["operational_status_counts"],
        ),
        _check(
            "NQ11",
            "station_complexes",
            "fail"
            if any(
                row["operational_status"] == "verified_operational"
                and not json.loads(row["operational_status_evidence_json"])
                and not row["operational_status_map_roster_match"]
                for row in station_data["complexes"]
            )
            else "pass",
            "Every verified_operational complex carries either a non-empty operational-status "
            "evidence reference (identity override or known-exception evidence) or a match "
            "against the current dated System Map roster; S026 corroboration and mere presence "
            "in the S005 exit layer are never, by themselves, sufficient.",
            None,
        ),
        _check(
            "NQ09",
            "node_review_queue",
            "pass"
            if len(
                {(row["station_complex_id"], row["issue_category"]) for row in commercial["review_items"]}
            )
            == len(commercial["review_items"])
            else "fail",
            f"{commercial_quality['review_queue_row_count']} review rows; "
            f"{commercial_quality['review_queue_open_count']} open, {commercial_quality['review_queue_closed_count']} closed; "
            f"issue categories {commercial_quality['review_issue_category_counts']}",
            commercial_quality["review_issue_category_open_counts"],
        ),
    ]
    quality_report = {
        "run_id": run_id,
        "schema_version": run_config["schema_version"],
        "method_version": run_config["method_version"],
        "overall_status": "validation_pending",
        "checks": checks,
        "source_summaries": {
            "S005_station_grouping": station_quality,
            "S026_train_names": train_names["quality"],
            "S027_land_use": land_quality,
            "commercial_nodes": commercial_quality,
        },
    }
    quality_json = report_dir / "data-quality-report.json"
    quality_md = report_dir / "data-quality-report.md"
    write_json(quality_json, quality_report)
    quality_md.write_text(quality_markdown(quality_report), encoding="utf-8")

    processed_files = [
        {
            **file_record(path, repo_root, row_count),
            "schema_fields": (
                list(next(records for name, records in output_specs if name == path.stem)[0])
                if path.stem in {name for name, _ in output_specs}
                else ["GeoJSON FeatureCollection"]
            ),
        }
        for path, row_count in output_paths
    ]
    source_manifest = []
    for source_id in ("S026", "S027"):
        item = acquired[source_id]
        metadata = item["metadata"]
        source_manifest.append(
            {
                "source_id": source_id,
                "publisher": item["source"]["publisher"],
                "title": item["source"]["title"],
                "landing_url": item["source"]["landing_url"],
                "resource_id": item["source"]["resource_id"],
                "acquisition_method": item["source"]["method"],
                "acquisition_status": item["acquisition_status"],
                "retrieved_at": metadata.get("retrieved_at"),
                "reference_period": metadata.get("official_metadata", {}).get(
                    "coverageEnd"
                ),
                "raw_path": item["raw_path"].relative_to(repo_root).as_posix(),
                "snapshot_metadata_path": item["metadata_path"].relative_to(repo_root).as_posix(),
                "raw_byte_size": item["raw_path"].stat().st_size,
                "raw_sha256": sha256_file(item["raw_path"]),
                "raw_schema": metadata.get("official_metadata", {}).get("fields"),
                "raw_row_count": (
                    train_names["quality"]["source_row_count"]
                    if source_id == "S026"
                    else land_quality["source_feature_count"]
                ),
                "transformations": (
                    ["exact station-name corroboration"]
                    if source_id == "S026"
                    else [
                        "frozen category filter",
                        "EPSG:3414 exit-union buffer intersection",
                    ]
                ),
                "use_limitation": item["source"]["use_limitation"],
                "immutable": True,
            }
        )
    manifest = {
        "run_id": run_id,
        "schema_version": run_config["schema_version"],
        "method_version": run_config["method_version"],
        "snapshot_date": run_config["snapshot_date"],
        "status": "validation_pending",
        "foundation_input": {
            "manifest_ref": configured["foundation_manifest_ref"],
            "manifest_sha256": sha256_file(foundation_manifest_path),
            "mrt_exits_ref": configured["foundation_mrt_exits_ref"],
            "mrt_exits_sha256": sha256_file(mrt_path),
            "mrt_exit_count": len(exits),
        },
        "configuration_inputs": [
            {
                "reference": run_config["station_overrides_ref"],
                "sha256": sha256_file(overrides_path),
                "config_version": overrides_config["override_config_version"],
                "purpose": "Authoritative resolution of code-only S005 station labels; never applied by proximity alone.",
            },
            {
                "reference": run_config["review_dispositions_ref"],
                "sha256": sha256_file(dispositions_path),
                "config_version": dispositions_config["disposition_config_version"],
                "purpose": "Closed/open dispositions for repeated-exit-label and unusually-dispersed station review issues.",
            },
            {
                "reference": run_config["operational_status_evidence_ref"],
                "sha256": sha256_file(operational_status_path),
                "config_version": operational_status_config["evidence_policy_version"],
                "purpose": "Operational-status evidence policy: S026 is identity corroboration only and never establishes operational status by itself; known exceptions (e.g. Marina South) and the S032 system-map roster are the operative evidence.",
            },
            {
                "reference": run_config["system_map_roster_ref"],
                "sha256": sha256_file(system_map_roster_path),
                "config_version": system_map_roster_config["roster_version"],
                "purpose": "Versioned, manually curated derived registry of station names read from the dated LTA System Map (S032), used as the current authoritative operational-network roster.",
            },
        ],
        "raw_evidence_snapshots": [
            {
                "source_id": "S032",
                "acquisition_status": acquired["S032"]["acquisition_status"],
                "storage_ref": acquired["S032"]["raw_path"].relative_to(repo_root).as_posix(),
                "sha256": acquired["S032"]["metadata"]["checksum"],
                "purpose": "Immutable raw snapshot of the LTA System Map PDF underlying the system_map_roster_ref derived registry.",
            }
        ],
        "sources": source_manifest,
        "processed_files": processed_files,
        "quality_report": quality_json.relative_to(repo_root).as_posix(),
        "station_grouping_audit": grouping_json.relative_to(repo_root).as_posix(),
        "commercial_evidence_methodology": method_json.relative_to(repo_root).as_posix(),
    }
    manifest_path = report_dir / "acquisition-provenance-manifest.json"
    write_json(manifest_path, manifest)

    completion = {
        "run_id": run_id,
        "status": "validation_pending",
        "counts": {
            "station_complexes": len(station_data["complexes"]),
            "station_exits": len(station_data["memberships"]),
            "commercial_node_candidates": len(commercial["candidates"]),
            "qualification_status_counts": commercial_quality[
                "qualification_status_counts"
            ],
            "operational_status_counts": station_data["quality"]["operational_status_counts"],
            "commercial_evidence_rows": len(commercial["evidence"]),
            "review_queue_rows": len(commercial["review_items"]),
            "review_queue_open_rows": commercial_quality["review_queue_open_count"],
            "review_queue_closed_rows": commercial_quality["review_queue_closed_count"],
            "review_issue_category_counts": commercial_quality["review_issue_category_counts"],
            "station_overrides_applied": station_data["quality"]["station_overrides_applied_count"],
            "station_complex_id_crosswalk_rows": station_data["quality"][
                "station_complex_id_crosswalk_count"
            ],
            "excluded_not_yet_operational": commercial_quality["excluded_not_yet_operational_count"],
        },
        "secret_scan": {
            "status": "validation_pending",
            "assurance": "unknown",
            "finding_count": 0,
        },
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
            "NQ06",
            "reportable_node_outputs",
            secret_scan["status"],
            f"generic scan {secret_scan['generic_pattern_scan_status']}; exact comparison {secret_scan['exact_credential_comparison_status']}; {secret_scan['finding_count']} finding files",
            secret_scan,
        )
    )
    status = _overall_status(checks)
    quality_report["overall_status"] = status
    quality_report["source_summaries"]["secret_scan"] = secret_scan
    manifest["status"] = status
    manifest["secret_scan"] = secret_scan
    completion["status"] = status
    completion["secret_scan"] = secret_scan
    write_json(quality_json, quality_report)
    quality_md.write_text(quality_markdown(quality_report), encoding="utf-8")
    write_json(manifest_path, manifest)
    completion_path.write_text(completion_markdown(completion), encoding="utf-8")
    return {
        "run_id": run_id,
        "status": status,
        "manifest": manifest_path.relative_to(repo_root).as_posix(),
        "quality_report": quality_json.relative_to(repo_root).as_posix(),
        "station_grouping_audit": grouping_json.relative_to(repo_root).as_posix(),
        "commercial_evidence_methodology": method_json.relative_to(repo_root).as_posix(),
        "completion_report": completion_path.relative_to(repo_root).as_posix(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build versioned MRT complexes and evidence-qualified commercial nodes"
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = run(args.repo_root.resolve())
    print(json.dumps(result, sort_keys=True))
    if result["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
