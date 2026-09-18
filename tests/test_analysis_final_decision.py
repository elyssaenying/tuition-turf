from tuition_location_analytics.analysis.final_decision import (
    _average_percentiles,
    _competition_value,
    financial_outputs,
    pareto_frontier,
)


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
