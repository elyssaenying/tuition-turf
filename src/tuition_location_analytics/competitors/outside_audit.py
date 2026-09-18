from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from tuition_location_analytics.foundation.common import (
    file_record,
    sha256_file,
    utc_now,
    write_csv,
    write_json,
    write_parquet,
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _band_rows(rows: list[dict[str, Any]], labels: list[str]) -> list[dict[str, Any]]:
    ordered = sorted(
        rows,
        key=lambda row: (-float(row["screen_score"]), row["commercial_node_id"]),
    )
    count = len(ordered)
    if not labels:
        raise ValueError("screen-band labels must not be empty")
    for position, row in enumerate(ordered):
        band_index = min(len(labels) - 1, position * len(labels) // max(1, count))
        row["pre_competition_screen_band"] = labels[band_index]
    return ordered


def draw_outside_audit(
    eligible_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    candidate_ids = {row["commercial_node_id"] for row in candidate_rows}
    if len(candidate_ids) != len(candidate_rows):
        raise RuntimeError("candidate freeze contains duplicate node IDs")
    rows = _band_rows(
        [dict(row) for row in eligible_rows],
        list(config["screen_bands"]["labels_high_to_low"]),
    )
    non_candidates = [row for row in rows if row["commercial_node_id"] not in candidate_ids]
    sample_size = int(config["sample_size"])
    if sample_size > len(non_candidates):
        raise RuntimeError("outside-audit sample exceeds eligible non-candidate universe")

    strata: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in non_candidates:
        key = (row["planning_region"], row["pre_competition_screen_band"])
        strata[key].append(row)
    minimum = int(config["allocation"]["minimum_per_nonempty_stratum"])
    if len(strata) * minimum > sample_size:
        raise RuntimeError("minimum stratum allocation exceeds sample size")

    allocation = {key: minimum for key in strata}
    universe_count = len(non_candidates)
    while sum(allocation.values()) < sample_size:
        candidates = [key for key, values in strata.items() if allocation[key] < len(values)]
        if not candidates:
            raise RuntimeError("unable to allocate requested outside-audit sample")
        key = sorted(
            candidates,
            key=lambda item: (
                -(
                    len(strata[item]) / universe_count
                    - allocation[item] / sample_size
                ),
                item,
            ),
        )[0]
        allocation[key] += 1

    rng = random.Random(int(config["random_seed"]))
    sample: list[dict[str, Any]] = []
    stratum_records: list[dict[str, Any]] = []
    for key in sorted(strata):
        region, band = key
        population = sorted(strata[key], key=lambda row: row["commercial_node_id"])
        sample_count = allocation[key]
        chosen_ids = {
            row["commercial_node_id"] for row in rng.sample(population, sample_count)
        }
        probability = sample_count / len(population)
        for row in population:
            if row["commercial_node_id"] not in chosen_ids:
                continue
            copy = dict(row)
            copy["audit_stratum_id"] = f"{region}|{band}"
            copy["stratum_population_count"] = len(population)
            copy["stratum_sample_count"] = sample_count
            copy["inclusion_probability"] = probability
            copy["design_weight"] = 1.0 / probability
            sample.append(copy)
        stratum_records.append(
            {
                "audit_stratum_id": f"{region}|{band}",
                "planning_region": region,
                "pre_competition_screen_band": band,
                "population_count": len(population),
                "sample_count": sample_count,
                "inclusion_probability": probability,
                "design_weight": 1.0 / probability,
            }
        )

    sample.sort(key=lambda row: (row["planning_region"], row["pre_competition_screen_band"], row["commercial_node_id"]))
    sample_ids = {row["commercial_node_id"] for row in sample}
    eligible_regions = {row["planning_region"] for row in rows}
    non_candidate_region_counts = Counter(
        row["planning_region"] for row in non_candidates
    )
    quality = {
        "eligible_universe_count": len(rows),
        "candidate_count": len(candidate_ids),
        "eligible_non_candidate_count": len(non_candidates),
        "requested_sample_size": sample_size,
        "actual_sample_size": len(sample),
        "nonempty_stratum_count": len(strata),
        "unique_sample_ids": len(sample_ids) == len(sample),
        "candidate_overlap_count": len(sample_ids & candidate_ids),
        "eligible_non_candidate_region_counts": dict(
            sorted(non_candidate_region_counts.items())
        ),
        "regions_without_eligible_non_candidates": sorted(
            eligible_regions - set(non_candidate_region_counts)
        ),
        "combined_candidate_and_audit_region_count": len(
            {row["planning_region"] for row in rows if row["commercial_node_id"] in candidate_ids}
            | {row["planning_region"] for row in sample}
        ),
        "region_sample_counts": dict(sorted(Counter(row["planning_region"] for row in sample).items())),
        "band_sample_counts": dict(
            sorted(Counter(row["pre_competition_screen_band"] for row in sample).items())
        ),
        "competitor_inputs_used": False,
    }
    return sample, stratum_records, quality


def run(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    config_path = repo_root / "config/competitors/outside_audit.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    inputs = {
        key: (repo_root / reference).resolve() for key, reference in config["inputs"].items()
    }
    for path in inputs.values():
        if not path.is_relative_to(repo_root) or not path.is_file():
            raise RuntimeError(f"outside-audit input is missing or outside repository: {path}")
    sample, strata, quality = draw_outside_audit(
        _read_csv(inputs["eligible_screen_ref"]),
        _read_csv(inputs["candidate_freeze_ref"]),
        config,
    )
    config_hash = sha256_file(config_path)
    audit_id = f"outside_audit_{config_hash[:16]}"
    output_dir = repo_root / "data/processed/competitors/2026-09-18" / audit_id
    report_dir = repo_root / "reports/competitors/2026-09-18" / audit_id
    sample_csv = output_dir / "outside_audit_sample.csv"
    sample_parquet = output_dir / "outside_audit_sample.parquet"
    strata_csv = output_dir / "outside_audit_strata.csv"
    strata_parquet = output_dir / "outside_audit_strata.parquet"
    write_csv(sample_csv, sample)
    write_parquet(sample_parquet, sample)
    write_csv(strata_csv, strata)
    write_parquet(strata_parquet, strata)
    result = {
        "audit_id": audit_id,
        "created_at": utc_now(),
        "status": "frozen_before_competitor_inspection",
        "random_seed": int(config["random_seed"]),
        "config_ref": config_path.relative_to(repo_root).as_posix(),
        "config_sha256": config_hash,
        "input_sha256": {key: sha256_file(path) for key, path in sorted(inputs.items())},
        "quality": quality,
        "strata": strata,
        "sample_node_ids": [row["commercial_node_id"] for row in sample],
        "outputs": [
            file_record(sample_csv, repo_root, len(sample)),
            file_record(sample_parquet, repo_root, len(sample)),
            file_record(strata_csv, repo_root, len(strata)),
            file_record(strata_parquet, repo_root, len(strata)),
        ],
    }
    write_json(report_dir / "outside-audit-freeze.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze the outside-candidate audit sample")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = run(args.repo_root)
    print(json.dumps({"audit_id": result["audit_id"], "quality": result["quality"]}, indent=2))


if __name__ == "__main__":
    main()
