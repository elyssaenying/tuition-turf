from __future__ import annotations

from datetime import date
from typing import Any

CONFIRMED_ELEMENTS = ("branch_address_or_existence", "mathematics_subject", "level_overlap")
EXCLUSION_OBSERVATION_TYPES = {
    "branch_closed",
    "branch_online_only",
    "branch_preschool_only",
    "branch_adult_only",
    "branch_no_mathematics",
    "branch_no_p1_s4_level",
    "branch_future_not_yet_open",
}
OPERATOR_CONTROLLED = "operator_controlled"


def _is_fresh(observed_at: str, analysis_cutoff: str, freshness_days: int) -> bool:
    try:
        observed = date.fromisoformat(observed_at)
        cutoff = date.fromisoformat(analysis_cutoff)
    except ValueError:
        return False
    return 0 <= (cutoff - observed).days <= freshness_days


def evaluate_branch_evidence(
    observations: list[dict[str, Any]],
    *,
    analysis_cutoff: str,
    freshness_days: int = 30,
) -> dict[str, Any]:
    """Evaluate confirmed/possible/excluded/unresolved for one branch's collected
    evidence observations, per the frozen inclusion rules.

    A directory result, ACRA registration, search snippet or map pin alone can
    never itself produce `confirmed`; only operator_controlled evidence can supply
    a confirmed element. Contradictory evidence (an exclusion signal alongside
    positive evidence of the same or comparable strength) yields `unresolved`
    rather than a guessed status.
    """
    exclusion_hits = [
        obs
        for obs in observations
        if obs["observation_type"] in EXCLUSION_OBSERVATION_TYPES
        and obs["evidence_scope"] != "search_snippet"
    ]
    positive_hits = {
        element: [
            obs
            for obs in observations
            if obs["observation_type"] == element and obs.get("polarity", "supports") == "supports"
        ]
        for element in CONFIRMED_ELEMENTS
    }
    any_positive_evidence = any(positive_hits[element] for element in CONFIRMED_ELEMENTS)

    if exclusion_hits and any_positive_evidence:
        return {
            "status": "unresolved",
            "reasons": ["conflicting_evidence: exclusion signal present alongside positive in-scope evidence"],
            "exclusion_observation_ids": [obs["evidence_id"] for obs in exclusion_hits],
        }
    if exclusion_hits:
        return {
            "status": "excluded",
            "reasons": [f"{obs['observation_type']} ({obs['evidence_scope']})" for obs in exclusion_hits],
            "exclusion_observation_ids": [obs["evidence_id"] for obs in exclusion_hits],
        }

    confirmed_elements_met = []
    stale_or_generic_elements = []
    for element in CONFIRMED_ELEMENTS:
        operator_hits = [
            obs
            for obs in positive_hits[element]
            if obs["evidence_scope"] == OPERATOR_CONTROLLED
        ]
        fresh_operator_hits = [
            obs for obs in operator_hits if _is_fresh(obs["observed_at"], analysis_cutoff, freshness_days)
        ]
        if fresh_operator_hits:
            confirmed_elements_met.append(element)
        elif operator_hits or positive_hits[element]:
            stale_or_generic_elements.append(element)

    if len(confirmed_elements_met) == len(CONFIRMED_ELEMENTS):
        return {
            "status": "confirmed",
            "reasons": [f"{element}: fresh operator-controlled evidence" for element in confirmed_elements_met],
            "missing_or_stale_elements": [],
        }

    if any_positive_evidence:
        missing = [e for e in CONFIRMED_ELEMENTS if e not in confirmed_elements_met]
        return {
            "status": "possible",
            "reasons": [
                f"{element}: {'stale or generic evidence' if element in stale_or_generic_elements else 'no evidence found'}"
                for element in missing
            ],
            "missing_or_stale_elements": missing,
        }

    return {
        "status": "unresolved",
        "reasons": ["no positive or exclusion evidence recorded for this branch"],
        "missing_or_stale_elements": list(CONFIRMED_ELEMENTS),
    }
