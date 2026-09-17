from __future__ import annotations

from typing import Any

BRANCH_STATUS_VALUES = {"current", "closed", "relocated", "future", "unresolved"}


def record_relocation(
    previous_branch: dict[str, Any],
    new_branch: dict[str, Any],
    *,
    effective_date_known: bool,
    source_ref: str,
) -> dict[str, Any]:
    """Link a relocation: the previous branch becomes `relocated` and the new
    branch becomes `current`, preserving both records rather than overwriting.
    Only the new (current) site counts as an operating branch at the cutoff.
    """
    if previous_branch["branch_id"] == new_branch["branch_id"]:
        raise ValueError("a relocation must link two distinct branch records")
    updated_previous = {**previous_branch, "status": "relocated", "superseded_by_branch_id": new_branch["branch_id"]}
    updated_new = {**new_branch, "status": "current", "previous_branch_id": previous_branch["branch_id"]}
    history_row = {
        "branch_id": new_branch["branch_id"],
        "previous_branch_id": previous_branch["branch_id"],
        "change_type": "relocated",
        "effective_date_known": effective_date_known,
        "source_ref": source_ref,
    }
    return {"previous_branch": updated_previous, "new_branch": updated_new, "history_row": history_row}


def count_current_branches(branches: list[dict[str, Any]]) -> int:
    """Only 'current' branches count as operating at the analysis cutoff; a
    relocated branch's previous site is never double-counted alongside its
    successor."""
    return sum(1 for branch in branches if branch.get("status") == "current")


def count_distinct_brands(branches: list[dict[str, Any]]) -> int:
    return len({branch["brand_id"] for branch in branches})
