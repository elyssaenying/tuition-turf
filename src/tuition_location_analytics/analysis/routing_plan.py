from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from typing import Any


def route_request_id(
    *,
    origin_geo_id: str,
    commercial_node_id: str,
    destination_exit_id: str,
    scenario_id: str,
    journey_timestamp: str,
    pt_mode: str,
    max_walk_distance_metres: int,
    num_itineraries: int,
) -> str:
    identity = "|".join(
        [
            origin_geo_id,
            commercial_node_id,
            destination_exit_id,
            scenario_id,
            journey_timestamp,
            pt_mode,
            str(max_walk_distance_metres),
            str(num_itineraries),
        ]
    )
    return "OD_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20].upper()


def closest_exit(origin: dict[str, Any], exits: list[dict[str, Any]]) -> tuple[dict[str, Any], float]:
    if not exits:
        raise ValueError("station complex has no exits")
    selected = min(
        exits,
        key=lambda row: (
            (float(row["easting_3414"]) - float(origin["centroid_easting_3414"])) ** 2
            + (float(row["northing_3414"]) - float(origin["centroid_northing_3414"])) ** 2,
            str(row["transit_point_id"]),
        ),
    )
    distance = math.hypot(
        float(selected["easting_3414"]) - float(origin["centroid_easting_3414"]),
        float(selected["northing_3414"]) - float(origin["centroid_northing_3414"]),
    )
    return selected, distance


def build_routing_plan(
    subzones: list[dict[str, Any]],
    population_by_geo_id: dict[str, float],
    nodes: list[dict[str, Any]],
    exit_rows: list[dict[str, Any]],
    scenarios: list[dict[str, Any]],
    *,
    max_walk_distance_metres: int,
    num_itineraries: int,
) -> list[dict[str, Any]]:
    if max_walk_distance_metres <= 0:
        raise ValueError("max walk distance must be positive")
    if not 1 <= num_itineraries <= 3:
        raise ValueError("num itineraries must be between 1 and 3")
    exits_by_complex: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in exit_rows:
        exits_by_complex[str(row["station_complex_id"])].append(row)

    records: list[dict[str, Any]] = []
    for origin in sorted(subzones, key=lambda row: str(row["geo_id"])):
        for node in sorted(nodes, key=lambda row: str(row["commercial_node_id"])):
            selected, straight_line_distance = closest_exit(
                origin,
                exits_by_complex[str(node["station_complex_id"])],
            )
            for scenario in scenarios:
                records.append(
                    {
                        "od_plan_id": route_request_id(
                            origin_geo_id=str(origin["geo_id"]),
                            commercial_node_id=str(node["commercial_node_id"]),
                            destination_exit_id=str(selected["transit_point_id"]),
                            scenario_id=str(scenario["scenario_id"]),
                            journey_timestamp=str(scenario["journey_timestamp"]),
                            pt_mode="TRANSIT",
                            max_walk_distance_metres=max_walk_distance_metres,
                            num_itineraries=num_itineraries,
                        ),
                        "origin_geo_id": origin["geo_id"],
                        "origin_subzone_name": origin["subzone_name"],
                        "origin_planning_area_name": origin["planning_area_name"],
                        "origin_region_name": origin["region_name"],
                        "origin_target_population_proxy": float(population_by_geo_id[origin["geo_id"]]),
                        "origin_latitude_wgs84": float(origin["centroid_latitude_wgs84"]),
                        "origin_longitude_wgs84": float(origin["centroid_longitude_wgs84"]),
                        "commercial_node_id": node["commercial_node_id"],
                        "node_name": node["node_name"],
                        "station_complex_id": node["station_complex_id"],
                        "destination_exit_id": selected["transit_point_id"],
                        "destination_exit_label": selected["exit_label_official"],
                        "destination_latitude_wgs84": float(selected["latitude_wgs84"]),
                        "destination_longitude_wgs84": float(selected["longitude_wgs84"]),
                        "nearest_exit_straight_line_distance_metres": straight_line_distance,
                        "scenario_id": scenario["scenario_id"],
                        "journey_timestamp": scenario["journey_timestamp"],
                        "pt_threshold_minutes": scenario["pt_threshold_minutes"],
                        "walking_fallback_threshold_minutes": scenario["walking_threshold_minutes"],
                        "proximity_fallback_metres": scenario["proximity_fallback_metres"],
                        "pt_mode": "TRANSIT",
                        "max_walk_distance_metres": max_walk_distance_metres,
                        "num_itineraries": num_itineraries,
                        "planned_primary_request": "onemap_pt",
                        "planned_missing_pt_fallback": "onemap_walk_then_proximity_proxy",
                    }
                )
    return records
