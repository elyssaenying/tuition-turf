from __future__ import annotations

import hashlib
from typing import Any

from .routing_plan import route_request_id


def _stable_key(seed: str, row: dict[str, Any]) -> str:
    identity = "|".join(
        [
            seed,
            str(row["origin_geo_id"]),
            str(row["commercial_node_id"]),
            str(row["destination_exit_id"]),
        ]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def select_balanced_pairs(
    rows: list[dict[str, Any]],
    *,
    scenario_id: str,
    distance_bands: list[dict[str, Any]],
    pairs_per_band: int,
    seed: str,
) -> list[dict[str, Any]]:
    if pairs_per_band <= 0:
        raise ValueError("pairs per band must be positive")
    selected: list[dict[str, Any]] = []
    for band in distance_bands:
        lower = float(band["minimum"])
        upper = band.get("maximum_exclusive")
        candidates = [
            row
            for row in rows
            if row["scenario_id"] == scenario_id
            and float(row["nearest_exit_straight_line_distance_metres"]) >= lower
            and (upper is None or float(row["nearest_exit_straight_line_distance_metres"]) < float(upper))
        ]
        candidates.sort(key=lambda row: _stable_key(seed, row))
        if len(candidates) < pairs_per_band:
            raise RuntimeError(f"insufficient routes in distance band {band['band_id']}")
        for row in candidates[:pairs_per_band]:
            pair_identity = "|".join(
                [str(row["origin_geo_id"]), str(row["commercial_node_id"]), str(row["destination_exit_id"])]
            )
            selected.append(
                {
                    **row,
                    "sample_pair_id": "PAIR_" + hashlib.sha256(pair_identity.encode("utf-8")).hexdigest()[:16].upper(),
                    "sample_distance_band": str(band["band_id"]),
                    "source_od_plan_id": row["od_plan_id"],
                }
            )
    return selected


def expand_walk_comparison(
    selected_pairs: list[dict[str, Any]], walk_distances_metres: list[int]
) -> list[dict[str, Any]]:
    if not walk_distances_metres or any(value <= 0 for value in walk_distances_metres):
        raise ValueError("walk distances must be positive")
    if len(set(walk_distances_metres)) != len(walk_distances_metres):
        raise ValueError("walk distances must be unique")
    expanded: list[dict[str, Any]] = []
    for row in selected_pairs:
        for max_walk in walk_distances_metres:
            expanded.append(
                {
                    **row,
                    "od_plan_id": route_request_id(
                        origin_geo_id=str(row["origin_geo_id"]),
                        commercial_node_id=str(row["commercial_node_id"]),
                        destination_exit_id=str(row["destination_exit_id"]),
                        scenario_id=str(row["scenario_id"]),
                        journey_timestamp=str(row["journey_timestamp"]),
                        pt_mode=str(row["pt_mode"]),
                        max_walk_distance_metres=int(max_walk),
                        num_itineraries=int(row["num_itineraries"]),
                    ),
                    "max_walk_distance_metres": int(max_walk),
                }
            )
    return expanded
