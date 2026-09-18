from __future__ import annotations

from tuition_location_analytics.competitors.outside_audit import draw_outside_audit


def test_outside_audit_is_reproducible_stratified_and_disjoint() -> None:
    eligible = []
    for index in range(12):
        eligible.append(
            {
                "commercial_node_id": f"N{index:02d}",
                "planning_region": "A" if index < 6 else "B",
                "screen_score": str(12 - index),
            }
        )
    candidates = [{"commercial_node_id": "N00"}, {"commercial_node_id": "N06"}]
    config = {
        "sample_size": 6,
        "random_seed": 42,
        "screen_bands": {"labels_high_to_low": ["high", "middle", "lower"]},
        "allocation": {"minimum_per_nonempty_stratum": 1},
    }

    first, strata, quality = draw_outside_audit(eligible, candidates, config)
    second, _, _ = draw_outside_audit(eligible, candidates, config)

    assert [row["commercial_node_id"] for row in first] == [
        row["commercial_node_id"] for row in second
    ]
    assert len(first) == 6
    assert len(strata) <= 6
    assert quality["candidate_overlap_count"] == 0
    assert all(0 < row["inclusion_probability"] <= 1 for row in first)
    assert all(row["design_weight"] >= 1 for row in first)
