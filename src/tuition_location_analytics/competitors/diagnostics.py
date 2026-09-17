from __future__ import annotations

from typing import Any


def channel_overlap_diagnostics(channel_a_ids: set[str], channel_b_ids: set[str], *, label_a: str, label_b: str) -> dict[str, Any]:
    """Descriptive discovery-channel diagnostics only. Deliberately does not
    produce a Lincoln-Petersen or any other capture-recapture population
    estimate: the two channels here (a third-party directory and general web
    search) violate the independence and equal-catchability assumptions that
    such an estimator requires (both substantially index the same operator
    websites), so any numerical completeness estimate from them would be
    invalid, not merely imprecise.
    """
    overlap = channel_a_ids & channel_b_ids
    union = channel_a_ids | channel_b_ids
    jaccard = len(overlap) / len(union) if union else 0.0
    return {
        f"{label_a}_count": len(channel_a_ids),
        f"{label_b}_count": len(channel_b_ids),
        "overlap_count": len(overlap),
        f"unique_to_{label_a}": len(channel_a_ids - channel_b_ids),
        f"unique_to_{label_b}": len(channel_b_ids - channel_a_ids),
        "union_count": len(union),
        "jaccard_overlap": jaccard,
        "estimator_statement": (
            "These are descriptive discovery-channel counts only. They do not "
            "estimate the true number of tuition centres in any planning area. "
            "No capture-recapture or other population estimator is computed "
            "because the two channels are not independent, equally-catchable "
            "samples of the same population."
        ),
    }
