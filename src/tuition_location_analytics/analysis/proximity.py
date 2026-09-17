from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from shapely.geometry import Point
from shapely.ops import unary_union


METHOD = "exit_union_straight_line_proximity_proxy"


def exit_union_catchment(exit_points: Iterable[Point], radius_metres: float):
    points = list(exit_points)
    if not points:
        raise ValueError("a node catchment requires at least one station exit")
    if radius_metres <= 0:
        raise ValueError("catchment radius must be positive")
    return unary_union([point.buffer(radius_metres) for point in points])


def area_weighted_population(
    catchment,
    subzones: Iterable[dict[str, Any]],
) -> tuple[float, int]:
    """Allocate subzone population by the share of metric polygon area intersected.

    This is a transparent spatial proxy. It assumes population is uniformly
    distributed within each subzone and must not be described as observed
    residents, enrolment, customers, or a travel-time catchment.
    """

    total = 0.0
    intersected = 0
    for row in subzones:
        geometry = row["geometry_3414"]
        population = float(row["target_population_proxy"] or 0.0)
        if geometry.is_empty or geometry.area <= 0 or not geometry.intersects(catchment):
            continue
        overlap_area = geometry.intersection(catchment).area
        if overlap_area <= 0:
            continue
        intersected += 1
        share = min(1.0, max(0.0, overlap_area / geometry.area))
        total += population * share
    return total, intersected


def point_count(catchment, points: Iterable[Point]) -> int:
    return sum(1 for point in points if catchment.covers(point))


def stable_descending_ranks(
    records: list[dict[str, Any]],
    *,
    value_field: str,
    id_field: str,
) -> dict[str, int]:
    ordered = sorted(
        records,
        key=lambda row: (-float(row[value_field]), str(row[id_field])),
    )
    return {str(row[id_field]): index for index, row in enumerate(ordered, start=1)}


def add_demand_ranks(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not records:
        return []
    ranks = stable_descending_ranks(
        records,
        value_field="proximity_target_population_proxy_800m",
        id_field="commercial_node_id",
    )
    denominator = max(1, len(records) - 1)
    enriched: list[dict[str, Any]] = []
    for row in records:
        rank = ranks[str(row["commercial_node_id"])]
        percentile = (len(records) - rank) / denominator
        if percentile >= 0.75:
            quartile = 4
        elif percentile >= 0.50:
            quartile = 3
        elif percentile >= 0.25:
            quartile = 2
        else:
            quartile = 1
        enriched.append(
            {
                **row,
                "population_proxy_800m_rank": rank,
                "population_proxy_800m_percentile": percentile,
                "population_proxy_800m_quartile": quartile,
            }
        )
    return sorted(enriched, key=lambda row: row["population_proxy_800m_rank"])
