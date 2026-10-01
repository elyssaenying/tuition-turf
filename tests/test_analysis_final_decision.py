import json
from pathlib import Path

from tuition_location_analytics.analysis.final_decision import (
    _average_percentiles,
    _competition_value,
    financial_outputs,
    pareto_frontier,
)


def test_dashboard_has_no_location_specific_benchmark_commentary() -> None:
    source = (Path(__file__).resolve().parents[1] / "app/src/App.tsx").read_text(encoding="utf-8")
    assert "Bukit Timah benchmark" not in source
    assert "Beauty World has" not in source
    assert "strategic_benchmark" not in source
    assert "36 candidates compared" in source
    assert "40 extra areas checked" in source
    assert "coverage.walking_routes_completed" not in source
    assert "Competition-recheck watchlist" not in source
    assert "rank movement diagnostic" not in source.lower()
    assert "competition stress test" not in source.lower()
    assert "What the analysis found" in source
    assert "Who can reach the area?" in source
    assert "Who lives near the station?" in source
    assert "Show the modelling assumptions behind these measures" in source
    assert "median absolute relative difference" not in source
    assert "Early signal" not in source
    assert "median rank" not in source
    assert "worst rank" not in source
    assert "How to use this map" in source
    assert "How the final decision was built" in source
    assert "What changes if the public-transport limit is 15, 20 or 25 minutes?" in source
    assert "same original 36 MRT areas" in source
    assert "not its chance of business success" in source
    assert "Do areas accessible to more students tend to have more tuition branches?" in source
    assert "Higher-cost case" not in source
    assert "Middle case" not in source
    assert "Lower-cost case" not in source
    assert "Why cost was not used to rank locations" in source
    assert "identical cost assumptions cannot change the location order" in source
    assert "decision rule" not in source
    assert "walking fallback" not in source
    assert "sensitivity check" not in source
    assert "An “MRT area” means the station and its immediate surroundings" in source
    assert "Count physical branches" in source
    assert "Interpret “zero found” carefully" in source
    assert "Test a more cautious ranking" in source
    assert "This is a safeguard, not an invented branch count" in source
    assert "—" not in source
    assert "not a guarantee of success" in source
    assert "does not identify demand" in source
    assert "not an official registry" in source
    assert "investigate sengkang first" in source.lower()
    assert "Serangoon only ranks near the top when 25 minutes are allowed" in source
    assert "cannot change which MRT area ranks higher" in source
    assert "check available units, current rent" in source
    assert 'aria-label="Follow the analysis"' in source
    assert 'aria-label="What the estimated journey measures"' in source
    assert "not an exact home or school" in source
    assert "not a rank or a chance of success" in source
    assert "Extra research: does population access relate" in source
    assert "100% complete" not in source
    assert "{item.selection_count}/200" not in source


def test_public_travel_time_check_matches_the_audited_results() -> None:
    root = Path(__file__).resolve().parents[1]
    audit = json.loads(
        (root / "reports/analysis/2026-09-28/travel-time-sensitivity/travel-time-sensitivity.json").read_text(
            encoding="utf-8"
        )
    )
    public = json.loads((root / "app/public/data/travel-time-sensitivity.json").read_text(encoding="utf-8"))
    assert audit["quality"]["frozen_20_minute_candidate_order_reproduced"]
    assert audit["quality"]["all_200_published_top_three_counts_reproduced"]
    assert public["comparison_scope"] == "same_original_36_mrt_areas"
    assert public["walking_fallback_minutes"] == 10
    assert public["straight_line_fallback_metres"] == 800
    assert public["comparisons_per_limit"] == 40
    assert [row["public_transport_minutes"] for row in public["thresholds"]] == [15, 20, 25]
    for row in public["thresholds"]:
        case = audit["thresholds"][str(row["public_transport_minutes"])]
        assert row["candidate_screen_overlap_with_20_minutes"] == case["overlap_with_frozen_20_minute_count"]
        results = case["fixed_36_ranking_both_days"]
        assert results["status"] == "complete"
        assert results["evaluations"] == public["comparisons_per_limit"]
        by_name = {result["node_name"].removesuffix(" MRT STATION"): result for result in results["candidate_results"]}
        for name, count in row["top_three_counts"].items():
            assert count == by_name[name]["top_three_count"]


def test_pareto_frontier_keeps_tradeoffs_and_removes_dominated_option() -> None:
    points = {
        "balanced": (2.0, 2.0, 2.0),
        "demand_tradeoff": (3.0, 1.0, 2.0),
        "dominated": (1.0, 2.0, 1.0),
    }
    assert pareto_frontier(points) == {"balanced", "demand_tradeoff"}


def test_average_percentiles_share_tied_rank() -> None:
    scores = _average_percentiles({"a": 10, "b": 10, "c": 1}, higher_is_better=True)
    assert scores["a"] == scores["b"]
    assert scores["a"] > scores["c"]


def test_zero_confirmed_caution_removes_automatic_best_score_without_inventing_count() -> None:
    assert _competition_value(0, zero_confirmed_caution=False) == 0
    assert _competition_value(0, zero_confirmed_caution=True) == 1
    assert _competition_value(3, zero_confirmed_caution=True) == 3


def test_financial_outputs_follow_frozen_linear_formula() -> None:
    rows = financial_outputs(
        {
            "capacity_active_students": 180,
            "target_active_students": 120,
            "scenarios": [
                {
                    "scenario_id": "base",
                    "effective_fee_per_student": 320,
                    "variable_cost_per_student": 30,
                    "non_occupancy_fixed_cost": 15000,
                    "occupancy_cost": 9000,
                }
            ],
        }
    )
    assert rows[0]["break_even_active_enrolments"] == 83
    assert rows[0]["capacity_feasible"] is True
    assert rows[0]["maximum_affordable_monthly_occupancy_cost_at_target"] == 19800
