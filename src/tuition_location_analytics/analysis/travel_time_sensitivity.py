"""Audit how 15, 20 and 25 minute travel limits affect location selection.

This is a diagnostic. It does not replace the frozen candidate set or release model.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

from tuition_location_analytics.analysis.final_decision import (
    COMPETITION_CASES,
    _average_percentiles,
    _competition_value,
    pareto_frontier,
)
from tuition_location_analytics.competitors.candidate_freeze import build_candidate_freeze


THRESHOLD_CASES = ((15, "pt15_walk10"), (20, "pt20_walk10_primary"), (25, "pt25_walk10"))
WEEKDAY_SCENARIO = "primary_weekday_after_school"
REPORT_REL = Path("reports/analysis/2026-09-28/travel-time-sensitivity")


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _accessibility_rows(
    rows: list[dict[str, str]], scenario: str, threshold_case: str
) -> dict[str, dict[str, str]]:
    selected = {
        row["commercial_node_id"]: row
        for row in rows
        if row["scenario_id"] == scenario and row["threshold_case_id"] == threshold_case
    }
    if len(selected) != 146:
        raise ValueError(f"Expected 146 MRT areas for {scenario}/{threshold_case}, found {len(selected)}")
    return selected


def _rank(
    candidates: list[dict[str, Any]],
    accessibility: dict[str, dict[str, str]],
    competition: dict[str, dict[str, Any]],
    profiles: dict[str, list[float]],
) -> dict[str, Any]:
    ids = sorted(row["commercial_node_id"] for row in candidates)
    by_id = {row["commercial_node_id"]: row for row in candidates}
    missing = sorted(set(ids) - set(competition))
    if missing:
        return {"status": "unavailable_missing_competition", "missing_node_ids": missing}
    if any(node_id not in accessibility for node_id in ids):
        raise ValueError("Accessibility rows are missing for a candidate")
    demand = {node_id: float(by_id[node_id]["population_proximity"]) for node_id in ids}
    access = {
        node_id: float(accessibility[node_id]["accessible_target_population_proxy"])
        for node_id in ids
    }
    demand_scores = _average_percentiles(demand, higher_is_better=True)
    access_scores = _average_percentiles(access, higher_is_better=True)
    selection_counts: Counter[str] = Counter()
    by_case: dict[str, Counter[str]] = {
        case_id: Counter() for case_id, _, _ in COMPETITION_CASES
    }
    full_ranks: dict[str, list[int]] = defaultdict(list)
    pareto_counts: Counter[str] = Counter()
    full_orderings: set[tuple[str, ...]] = set()
    for case_id, minutes, caution in COMPETITION_CASES:
        competition_values = {
            node_id: _competition_value(
                competition[node_id][f"confirmed_within_{minutes}_min_walk"],
                zero_confirmed_caution=caution,
            )
            for node_id in ids
        }
        competition_scores = _average_percentiles(competition_values, higher_is_better=False)
        frontier = pareto_frontier(
            {
                node_id: (demand[node_id], access[node_id], -competition_values[node_id], 0.0)
                for node_id in ids
            }
        )
        pareto_counts.update(frontier)
        for weights in profiles.values():
            scores = {
                node_id: (
                    weights[0] * demand_scores[node_id]
                    + weights[1] * access_scores[node_id]
                    + weights[2] * competition_scores[node_id]
                    + weights[3] * 0.5
                )
                for node_id in ids
            }
            ordered = sorted(ids, key=lambda node_id: (-scores[node_id], node_id))
            full_orderings.add(tuple(ordered))
            for rank, node_id in enumerate(ordered, start=1):
                full_ranks[node_id].append(rank)
            for node_id in [node_id for node_id in ordered if node_id in frontier][:3]:
                selection_counts[node_id] += 1
                by_case[case_id][node_id] += 1
    rows = []
    for node_id in ids:
        rows.append(
            {
                "commercial_node_id": node_id,
                "node_name": by_id[node_id]["node_name"],
                "top_three_count": selection_counts[node_id],
                "observed_count": sum(
                    by_case[case_id][node_id]
                    for case_id in ("confirmed_10_min", "confirmed_15_min")
                ),
                "caution_count": sum(
                    by_case[case_id][node_id]
                    for case_id in ("zero_confirmed_caution_10_min", "zero_confirmed_caution_15_min")
                ),
                "pareto_case_count": pareto_counts[node_id],
                "median_full_rank": statistics.median(full_ranks[node_id]),
                "worst_full_rank": max(full_ranks[node_id]),
            }
        )
    rows.sort(
        key=lambda row: (
            -row["top_three_count"],
            row["median_full_rank"],
            row["worst_full_rank"],
            row["commercial_node_id"],
        )
    )
    return {
        "status": "complete",
        "evaluations": len(COMPETITION_CASES) * len(profiles),
        "unique_full_orderings": len(full_orderings),
        "candidate_results": rows,
    }


def _combine_days(weekday: dict[str, Any], weekend: dict[str, Any]) -> dict[str, Any]:
    if weekday["status"] != "complete" or weekend["status"] != "complete":
        return {"status": "unavailable_missing_competition"}
    weekend_by_id = {
        row["commercial_node_id"]: row for row in weekend["candidate_results"]
    }
    rows = []
    for row in weekday["candidate_results"]:
        other = weekend_by_id[row["commercial_node_id"]]
        rows.append(
            {
                "commercial_node_id": row["commercial_node_id"],
                "node_name": row["node_name"],
                "top_three_count": row["top_three_count"] + other["top_three_count"],
                "observed_count": row["observed_count"] + other["observed_count"],
                "caution_count": row["caution_count"] + other["caution_count"],
            }
        )
    rows.sort(key=lambda row: (-row["top_three_count"], row["commercial_node_id"]))
    return {
        "status": "complete",
        "evaluations": weekday["evaluations"] + weekend["evaluations"],
        "candidate_results": rows,
    }


def build_audit(repo_root: Path) -> dict[str, Any]:
    config_path = repo_root / "config/competitors/candidate_freeze.json"
    config = _json(config_path)
    paths = {
        "qualified_nodes": repo_root / config["inputs"]["qualified_nodes_ref"],
        "population_proximity": repo_root / config["inputs"]["population_proximity_ref"],
        "accessibility": repo_root / config["inputs"]["accessibility_ref"],
        "frozen_candidates": repo_root / "data/processed/competitors/2026-09-18/candidate_freeze_8f16c917adc6a3a3/candidate_node_freeze.csv",
        "competition": repo_root / "reports/competitors/2026-09-18/national_completion/national-competition-summary.json",
        "final_decision": repo_root / "reports/analysis/2026-09-18/final_decision/final-decision.json",
        "operator_profiles": repo_root / "config/modelling/operator_scenarios.json",
        "candidate_config": config_path,
    }
    nodes = _csv(paths["qualified_nodes"])
    proximity = _csv(paths["population_proximity"])
    all_access = _csv(paths["accessibility"])
    frozen = _csv(paths["frozen_candidates"])
    frozen_ids = [row["commercial_node_id"] for row in frozen]
    frozen_by_id = {row["commercial_node_id"]: row for row in frozen}
    competition = {
        row["commercial_node_id"]: row for row in _json(paths["competition"])["nodes"]
    }
    final = _json(paths["final_decision"])
    final_by_id = {row["commercial_node_id"]: row for row in final["candidate_results"]}
    profiles = _json(paths["operator_profiles"])["weights"]
    if len(frozen_ids) != 36 or len(final_by_id) != 36:
        raise ValueError("The frozen 36-area comparison has changed")

    screens: dict[str, Any] = {}
    for minutes, case in THRESHOLD_CASES:
        scenario_config = deepcopy(config)
        scenario_config["eligibility"]["accessibility_threshold_case_id"] = case
        eligible, selected, quality = build_candidate_freeze(
            nodes, proximity, all_access, scenario_config
        )
        selected_ids = [row["commercial_node_id"] for row in selected]
        if minutes == 20 and selected_ids != frozen_ids:
            raise ValueError("The 20-minute candidate selection does not reproduce the frozen order")
        if len(eligible) != 95 or len(selected_ids) != 36:
            raise ValueError(f"The {minutes}-minute candidate set has unexpected coverage")
        eligible_by_id = {row["commercial_node_id"]: row for row in eligible}
        entrants = sorted(set(selected_ids) - set(frozen_ids))
        exits = sorted(set(frozen_ids) - set(selected_ids))
        access = _accessibility_rows(all_access, WEEKDAY_SCENARIO, case)
        all_access_order = sorted(
            access, key=lambda node_id: (-float(access[node_id]["accessible_target_population_proxy"]), node_id)
        )
        all_access_ranks = {node_id: rank for rank, node_id in enumerate(all_access_order, start=1)}
        screen_rank = {node_id: rank for rank, node_id in enumerate(
            sorted(eligible_by_id, key=lambda node_id: (-eligible_by_id[node_id]["screen_score"], node_id)),
            start=1,
        )}
        weekend_access = _accessibility_rows(all_access, "weekend_comparison", case)
        fixed_weekday = _rank(frozen, access, competition, profiles)
        fixed_weekend = _rank(frozen, weekend_access, competition, profiles)
        alternative_weekday = _rank(selected, access, competition, profiles)
        alternative_weekend = _rank(selected, weekend_access, competition, profiles)
        screens[str(minutes)] = {
            "threshold_minutes": minutes,
            "selected_count": len(selected_ids),
            "eligible_count": len(eligible),
            "selected_ids": selected_ids,
            "selected_region_counts": quality["selected_region_counts"],
            "overlap_with_frozen_20_minute_count": len(set(selected_ids) & set(frozen_ids)),
            "entrants": [
                {"commercial_node_id": node_id, "node_name": eligible_by_id[node_id]["node_name"], "competition_evidence_available": node_id in competition}
                for node_id in entrants
            ],
            "exits": [
                {"commercial_node_id": node_id, "node_name": frozen_by_id[node_id]["node_name"]}
                for node_id in exits
            ],
            "missing_competition_evidence_for_selected": [
                {"commercial_node_id": node_id, "node_name": eligible_by_id[node_id]["node_name"]}
                for node_id in selected_ids if node_id not in competition
            ],
            "notable_nodes": {
                name: {
                    "selected": node_id in selected_ids,
                    "selection_stage": next((row["selection_stage"] for row in selected if row["commercial_node_id"] == node_id), None),
                    "screen_rank_among_95": screen_rank[node_id],
                    "reachable_population_proxy": float(access[node_id]["accessible_target_population_proxy"]),
                    "accessibility_rank_among_146": all_access_ranks[node_id],
                }
                for name, node_id in (
                    ("Sengkang", "NODE_060EFCFFF0678F62"),
                    ("Serangoon", "NODE_BE3506E4DDD906F9"),
                    ("Yishun", "NODE_6FF34CE78F7A7CE4"),
                    ("Bukit Panjang", "NODE_E62A238EEFE24A0E"),
                )
            },
            "fixed_36_ranking_weekday": fixed_weekday,
            "fixed_36_ranking_weekend": fixed_weekend,
            "fixed_36_ranking_both_days": _combine_days(fixed_weekday, fixed_weekend),
            "alternative_36_ranking_weekday": alternative_weekday,
            "alternative_36_ranking_weekend": alternative_weekend,
            "alternative_36_ranking_both_days": _combine_days(alternative_weekday, alternative_weekend),
        }

    # Reproduce all published top-three counts before using a filtered result.
    reproduced: Counter[str] = Counter()
    case_pairs = sorted({(row["scenario_id"], row["threshold_case_id"]) for row in all_access})
    if len(case_pairs) != 10:
        raise ValueError(f"Expected 10 published accessibility cases, found {len(case_pairs)}")
    for scenario, case in case_pairs:
        result = _rank(frozen, _accessibility_rows(all_access, scenario, case), competition, profiles)
        if result["status"] != "complete":
            raise ValueError("Published comparison has incomplete competitor coverage")
        reproduced.update({row["commercial_node_id"]: row["top_three_count"] for row in result["candidate_results"]})
    mismatches = {
        node_id: {"published": final_by_id[node_id]["selection_count"], "reproduced": reproduced[node_id]}
        for node_id in frozen_ids if final_by_id[node_id]["selection_count"] != reproduced[node_id]
    }
    if mismatches:
        raise ValueError(f"Published final-selection counts did not reproduce: {mismatches}")
    return {
        "status": "diagnostic_complete",
        "canonical_results_changed": False,
        "scope": "Weekday 16:00 residential-subzone-centre to MRT-exit travel; 10-minute walking fallback and 800-metre straight-line fallback remain fixed; candidate screen and four competition cases match the release rules.",
        "source_checksums": {key: _sha256(path) for key, path in paths.items()},
        "quality": {
            "frozen_20_minute_candidate_order_reproduced": True,
            "all_200_published_top_three_counts_reproduced": True,
            "qualified_nodes": 95,
            "frozen_candidates": 36,
            "publicly_evaluated_competition_nodes": len(competition),
        },
        "thresholds": screens,
    }


def _markdown(audit: dict[str, Any]) -> str:
    screens = audit["thresholds"]
    lines = [
        "# Travel-time sensitivity: 15, 20 and 25 minutes",
        "",
        "The question is whether changing the assumed travel limit changes which MRT areas are investigated and how the already investigated areas compare. This audit preserves the published results and applies the original selection and ranking rules to existing data.",
        "",
        "**Main result:** Sengkang remains a top-three area under all three tested travel limits. Serangoon is selected in 37 of 40 setting comparisons at 25 minutes, and in none at 15 or 20 minutes. Its published 37 of 200 selections therefore come entirely from the 25-minute cases. This is a substantial threshold dependence, not evidence that 25 minutes reflects actual family behaviour.",
        "",
        "Candidate selection uses Wednesday 4 pm journeys. The fixed-candidate ranking checks both Wednesday 4 pm and Saturday 10 am. Journeys start at residential subzone centre points and end at MRT exits. They do not start at schools or end at a specific tuition unit. Reachable population is an access proxy, not observed enrolment or willingness to travel. The 10-minute walking fallback and 800-metre proximity fallback are held constant.",
        "",
        "## First stage: which areas enter detailed investigation?",
        "",
        "The same 95 commercially qualified MRT areas, 24 merit slots and 12 regional coverage slots were used for each travel limit. The 20-minute selection reproduced the published 36-area list in exactly the same order.",
        "",
        "| Travel limit | Areas in common with the frozen 20-minute list | New areas | Frozen areas displaced | Selected areas lacking comparable competitor evidence |",
        "|---:|---:|---:|---:|---:|",
    ]
    for minutes in (15, 20, 25):
        item = screens[str(minutes)]
        lines.append(
            f"| {minutes} min | {item['overlap_with_frozen_20_minute_count']}/36 | {len(item['entrants'])} | {len(item['exits'])} | {len(item['missing_competition_evidence_for_selected'])} |"
        )
    lines += ["", "| MRT area | 15-minute reach | 20-minute reach | 25-minute reach | Selected at 15 / 20 / 25 minutes |", "|---|---:|---:|---:|---|"]
    for name in ("Sengkang", "Serangoon", "Yishun", "Bukit Panjang"):
        cases = [screens[str(minutes)]["notable_nodes"][name] for minutes in (15, 20, 25)]
        lines.append(
            f"| {name} | {cases[0]['reachable_population_proxy']:,.0f} | {cases[1]['reachable_population_proxy']:,.0f} | {cases[2]['reachable_population_proxy']:,.0f} | "
            + " / ".join("yes" if row["selected"] else "no" for row in cases) + " |"
        )
    lines += ["", "### Areas entering and leaving the 36-area screen", ""]
    for minutes in (15, 25):
        item = screens[str(minutes)]
        entered = ", ".join(row["node_name"].removesuffix(" MRT STATION") for row in item["entrants"]) or "None"
        left = ", ".join(row["node_name"].removesuffix(" MRT STATION") for row in item["exits"]) or "None"
        lines += [f"**{minutes} minutes:** Enter: {entered}. Leave: {left}.", ""]
    lines += [
        "## Second stage: ranking the same 36 investigated areas",
        "",
        "For each travel limit, the original model was run at two journey times under four competition treatments and five preference profiles, giving 40 setting comparisons. These counts are not probabilities or independent trials. The finance input is identical for every area and cannot distinguish them.",
        "",
        "| MRT area | Top-three selections at 15 min | At 20 min | At 25 min |",
        "|---|---:|---:|---:|",
    ]
    for name in ("SENGKANG MRT STATION", "SERANGOON MRT STATION", "YISHUN MRT STATION", "BUKIT PANJANG MRT STATION"):
        counts = []
        for minutes in (15, 20, 25):
            rows = screens[str(minutes)]["fixed_36_ranking_both_days"]["candidate_results"]
            counts.append(next(row["top_three_count"] for row in rows if row["node_name"] == name))
        lines.append(f"| {name.removesuffix(' MRT STATION').title()} | " + " | ".join(f"{count}/40" for count in counts) + " |")
    lines += ["", "### Highest selection counts within the fixed 36", ""]
    for minutes in (15, 20, 25):
        result = screens[str(minutes)]["fixed_36_ranking_both_days"]
        leaders = ", ".join(
            f"{row['node_name'].removesuffix(' MRT STATION').title()} ({row['top_three_count']}/40)"
            for row in [row for row in result["candidate_results"] if row["top_three_count"] > 0][:5]
        )
        lines += [f"**{minutes} minutes:** {leaders}.", ""]
    lines += ["## Can the alternative 36-area lists be ranked fully?", ""]
    for minutes in (15, 25):
        item = screens[str(minutes)]
        result = item["alternative_36_ranking_both_days"]
        if result["status"] == "complete":
            leaders = ", ".join(
                f"{row['node_name'].removesuffix(' MRT STATION').title()} ({row['top_three_count']}/40)"
                for row in [row for row in result["candidate_results"] if row["top_three_count"] > 0][:5]
            )
            lines += [f"**{minutes} minutes:** All selected areas have the bounded competitor evidence. Highest selection counts: {leaders}.", ""]
        else:
            names = ", ".join(row["node_name"].removesuffix(" MRT STATION") for row in item["missing_competition_evidence_for_selected"])
            lines += [f"**{minutes} minutes:** A comparable final ranking is unavailable because {len(item['missing_competition_evidence_for_selected'])} selected area lacks competitor coverage: {names}. No competitor count was imputed.", ""]
    lines += [
        "## Interpretation and limits",
        "",
        "- The 20-minute scenario is one decision assumption. The 15- and 25-minute comparisons show how dependent the candidate screen and subsequent ranking are on that assumption.",
        "- The fixed-36 ranking is comparable across travel limits but cannot reveal the final ranking of areas left outside the original 36. The alternative-36 ranking is shown only when the same competitor protocol has covered every selected area.",
        "- The published full model's 200 top-three counts were reproduced exactly before interpreting these subsets. The original 20-minute candidate order also reproduced exactly.",
        "- Thresholds do not estimate actual travel preferences. Subzone-centre origins, station-exit destinations, one weekday and one weekend timestamp, and incomplete market evidence limit business interpretation.",
        "",
        "Sources: `config/competitors/candidate_freeze.json`, the qualified-node, population-proximity and accessibility outputs it references, `reports/competitors/2026-09-18/national_completion/national-competition-summary.json`, and `reports/analysis/2026-09-18/final_decision/final-decision.json`. Full source checksums and per-area diagnostics are in the accompanying JSON.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    audit = build_audit(repo_root)
    output_dir = repo_root / REPORT_REL
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "travel-time-sensitivity.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "travel-time-sensitivity.md").write_text(_markdown(audit), encoding="utf-8")
    print(json.dumps({"status": audit["status"], "report": str((REPORT_REL / "travel-time-sensitivity.md")), "quality": audit["quality"]}, sort_keys=True))


if __name__ == "__main__":
    main()
