from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

#: Alphabetically first among the planning-area codes hosting a station with an
#: open no_commercial_zoning_signal review item (Bukit Batok/Hume, Changi/Changi
#: Airport, Pioneer/Joo Koon, Sungei Kadut/Kranji, Tuas/Tuas Link). This is a
#: documented tie-break, not a demographic criterion, and is applied before any
#: competitor discovery is run.
MANDATED_NO_ZONING_SIGNAL_PLANNING_AREA_CODE = "BK"


def compute_population_by_planning_area(
    population_proxy_rows: list[dict[str, Any]],
) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for row in population_proxy_rows:
        totals[row["planning_area_code"]] += float(row["accessible_target_population_proxy"])
    return dict(totals)


def compute_national_quartile(
    code: str, population_by_code: dict[str, float], all_codes: list[str]
) -> int:
    ordered = sorted(all_codes, key=lambda c: (population_by_code.get(c, 0.0), c))
    rank = ordered.index(code)
    quartile_size = len(ordered) / 4
    return min(int(rank // quartile_size) + 1, 4)


def select_pilot_planning_areas(
    geography_rows: list[dict[str, Any]],
    population_proxy_rows: list[dict[str, Any]],
    *,
    per_region_picks: int = 2,
    mandated_code: str = MANDATED_NO_ZONING_SIGNAL_PLANNING_AREA_CODE,
) -> dict[str, Any]:
    """Deterministically select a pilot set of planning areas before any competitor
    discovery is run.

    Algorithm (frozen, no observed-competitor-count input):
    1. Derive the full planning-area roster and region assignment from the approved
       geography data (never a hardcoded count).
    2. Sum the approved age-7-16 population proxy per planning area (code-joined,
       not name-joined, to avoid a case-sensitivity mismatch between sources).
    3. In the region containing `mandated_code`, force-include it as one of that
       region's picks (a disclosed data-quality stress-test override, not a
       demographic criterion).
    4. For every region, pick the area with the single highest population proxy
       (excluded from consideration in the mandated region if it is the mandated
       area itself) as one pick.
    5. Pick a second area per region as the one whose population proxy is closest
       to that region's own median population proxy (ties broken alphabetically by
       planning-area code), excluding any area already picked. In the mandated
       region, this step is replaced by the mandated area itself.
    """
    region_by_code: dict[str, str] = {}
    name_by_code: dict[str, str] = {}
    for row in geography_rows:
        region_by_code[row["planning_area_code"]] = row["region_name"]
        name_by_code[row["planning_area_code"]] = row["planning_area_name"]

    population_by_code = compute_population_by_planning_area(population_proxy_rows)
    all_codes = sorted(region_by_code)
    if mandated_code not in region_by_code:
        raise RuntimeError(f"mandated planning-area code {mandated_code} not found in geography data")

    by_region: dict[str, list[str]] = defaultdict(list)
    for code in all_codes:
        by_region[region_by_code[code]].append(code)

    mandated_region = region_by_code[mandated_code]
    selections: list[dict[str, Any]] = []
    for region in sorted(by_region):
        codes = by_region[region]
        codes_by_population_desc = sorted(codes, key=lambda c: (-population_by_code.get(c, 0.0), c))
        if region == mandated_region:
            top_pick = next(c for c in codes_by_population_desc if c != mandated_code)
            picks = [mandated_code, top_pick]
            pick_reasons = {
                mandated_code: "mandated_no_commercial_zoning_signal_stress_test",
                top_pick: "highest_population_proxy_in_region_excluding_mandated_pick",
            }
        else:
            top_pick = codes_by_population_desc[0]
            median_population = statistics.median(population_by_code.get(c, 0.0) for c in codes)
            remaining = [c for c in codes if c != top_pick]
            second_pick = min(
                remaining, key=lambda c: (abs(population_by_code.get(c, 0.0) - median_population), c)
            )
            picks = [top_pick, second_pick]
            pick_reasons = {
                top_pick: "highest_population_proxy_in_region",
                second_pick: "closest_to_region_median_population_proxy",
            }
        if len(picks) > per_region_picks:
            picks = picks[:per_region_picks]
        for code in picks:
            selections.append(
                {
                    "planning_area_code": code,
                    "planning_area_name": name_by_code[code],
                    "region_name": region,
                    # Named distinctly from the foundation's subzone-level
                    # `accessible_target_population_proxy`: this is a planning-area
                    # sum used only for pilot stratification. No catchment/access
                    # calculation has been performed, so it must never be read as
                    # an accessibility result.
                    "planning_area_target_population_proxy": population_by_code.get(code, 0.0),
                    "national_population_quartile": compute_national_quartile(
                        code, population_by_code, all_codes
                    ),
                    "selection_reason": pick_reasons[code],
                }
            )

    quartiles_represented = sorted({row["national_population_quartile"] for row in selections})
    return {
        "selection_algorithm_version": "2026-09-13.1",
        "total_planning_areas_in_geography_data": len(all_codes),
        "total_regions": len(by_region),
        "per_region_picks": per_region_picks,
        "mandated_planning_area_code": mandated_code,
        "mandated_planning_area_name": name_by_code[mandated_code],
        "mandated_planning_area_reason": "Bukit Batok hosts Hume MRT Station, which carries an open no_commercial_zoning_signal review item; alphabetically first among the five such planning-area codes (BK, CH, PN, SK, TS) under the documented tie-break.",
        "selected": sorted(selections, key=lambda r: (r["region_name"], r["planning_area_code"])),
        "national_population_quartiles_represented": quartiles_represented,
        "not_based_on_observed_competitor_counts": True,
    }
