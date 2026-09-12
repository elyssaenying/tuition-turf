from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import CRS, Transformer
from shapely import make_valid, wkb
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union
from shapely.validation import explain_validity

from .common import duplicate_values, normalize_name, write_json

EXCHANGE_CRS = CRS.from_epsg(4326)
METRIC_CRS = CRS.from_epsg(3414)


def _property(properties: dict[str, Any], name: str) -> Any:
    if name in properties:
        return properties[name]
    lookup = {key.upper(): value for key, value in properties.items()}
    return lookup.get(name.upper())


def _in_bounds(bounds: tuple[float, float, float, float], configured: dict[str, float]) -> bool:
    minimum_x, minimum_y, maximum_x, maximum_y = bounds
    return (
        configured["minimum_longitude"] <= minimum_x <= configured["maximum_longitude"]
        and configured["minimum_longitude"] <= maximum_x <= configured["maximum_longitude"]
        and configured["minimum_latitude"] <= minimum_y <= configured["maximum_latitude"]
        and configured["minimum_latitude"] <= maximum_y <= configured["maximum_latitude"]
    )


def write_geoparquet(
    path: Path,
    records: list[dict[str, Any]],
    geometries: list[Any],
    *,
    crs: CRS = EXCHANGE_CRS,
) -> None:
    if len(records) != len(geometries):
        raise ValueError("record and geometry counts differ")
    table = pa.Table.from_pylist(records)
    geometry_array = pa.array([wkb.dumps(geometry) for geometry in geometries], type=pa.binary())
    table = table.append_column("geometry", geometry_array)
    geometry_types = sorted({geometry.geom_type for geometry in geometries})
    total_bounds = [
        min(geometry.bounds[0] for geometry in geometries),
        min(geometry.bounds[1] for geometry in geometries),
        max(geometry.bounds[2] for geometry in geometries),
        max(geometry.bounds[3] for geometry in geometries),
    ]
    geo_metadata = {
        "version": "1.1.0",
        "primary_column": "geometry",
        "columns": {
            "geometry": {
                "encoding": "WKB",
                "geometry_types": geometry_types,
                "crs": crs.to_json_dict(),
                "bbox": total_bounds,
            }
        },
    }
    metadata = dict(table.schema.metadata or {})
    metadata[b"geo"] = json.dumps(geo_metadata, sort_keys=True).encode("utf-8")
    table = table.replace_schema_metadata(metadata)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table, temporary, compression="zstd")
    os.replace(temporary, path)


def process_boundaries(raw_path: Path, singapore_bounds: dict[str, float]) -> dict[str, Any]:
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
        raise RuntimeError("S003 is not a GeoJSON FeatureCollection")
    forward = Transformer.from_crs(EXCHANGE_CRS, METRIC_CRS, always_xy=True)
    reverse = Transformer.from_crs(METRIC_CRS, EXCHANGE_CRS, always_xy=True)
    records: list[dict[str, Any]] = []
    geometries: list[Any] = []
    output_features: list[dict[str, Any]] = []
    source_invalid_geometry: list[dict[str, Any]] = []
    processed_invalid_geometry: list[dict[str, Any]] = []
    geometry_repairs: list[dict[str, Any]] = []
    out_of_bounds: list[str] = []
    missing_fields: list[dict[str, Any]] = []
    geometry_types: Counter[str] = Counter()

    required = (
        "SUBZONE_NO",
        "SUBZONE_N",
        "SUBZONE_C",
        "PLN_AREA_N",
        "PLN_AREA_C",
        "REGION_N",
        "REGION_C",
    )
    for index, feature in enumerate(payload["features"]):
        properties = feature.get("properties") or {}
        selected = {name: _property(properties, name) for name in required}
        missing = [name for name, value in selected.items() if value in {None, ""}]
        if missing:
            missing_fields.append({"feature_index": index, "fields": missing})
        geometry = shape(feature.get("geometry"))
        subzone_code = str(selected["SUBZONE_C"] or "")
        geometry_types[geometry.geom_type] += 1
        if not geometry.is_valid:
            source_reason = explain_validity(geometry)
            source_invalid_geometry.append(
                {"subzone_code": subzone_code, "reason": source_reason}
            )
            repaired = make_valid(geometry)
            if repaired.geom_type == "GeometryCollection":
                polygon_parts = [
                    part for part in repaired.geoms if part.geom_type in {"Polygon", "MultiPolygon"}
                ]
                repaired = unary_union(polygon_parts)
            geometry_repairs.append(
                {
                    "subzone_code": subzone_code,
                    "method": "shapely.make_valid",
                    "source_reason": source_reason,
                    "result_geometry_type": repaired.geom_type,
                }
            )
            geometry = repaired
        if not geometry.is_valid or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            processed_invalid_geometry.append(
                {
                    "subzone_code": subzone_code,
                    "reason": explain_validity(geometry),
                    "geometry_type": geometry.geom_type,
                }
            )
        if not _in_bounds(geometry.bounds, singapore_bounds):
            out_of_bounds.append(subzone_code)
        metric_geometry = transform(forward.transform, geometry)
        metric_centroid = metric_geometry.centroid
        centroid = transform(reverse.transform, metric_centroid)
        record = {
            "source_id": "S003",
            "geo_id": f"MP2019_SZ_{subzone_code}",
            "subzone_number": int(selected["SUBZONE_NO"]) if selected["SUBZONE_NO"] is not None else None,
            "subzone_name": str(selected["SUBZONE_N"] or ""),
            "subzone_code": subzone_code,
            "planning_area_name": str(selected["PLN_AREA_N"] or ""),
            "planning_area_code": str(selected["PLN_AREA_C"] or ""),
            "region_name": str(selected["REGION_N"] or ""),
            "region_code": str(selected["REGION_C"] or ""),
            "exchange_crs": "EPSG:4326",
            "metric_crs": "EPSG:3414",
            "area_sqm_3414": metric_geometry.area,
            "centroid_longitude_wgs84": centroid.x,
            "centroid_latitude_wgs84": centroid.y,
            "centroid_easting_3414": metric_centroid.x,
            "centroid_northing_3414": metric_centroid.y,
        }
        records.append(record)
        geometries.append(geometry)
        output_features.append(
            {"type": "Feature", "id": record["geo_id"], "properties": record, "geometry": mapping(geometry)}
        )

    quality = {
        "source_feature_count": len(payload["features"]),
        "processed_feature_count": len(records),
        "geometry_types": dict(geometry_types),
        "source_invalid_geometry_count": len(source_invalid_geometry),
        "source_invalid_geometry": source_invalid_geometry,
        "geometry_repair_count": len(geometry_repairs),
        "geometry_repairs": geometry_repairs,
        "processed_invalid_geometry_count": len(processed_invalid_geometry),
        "processed_invalid_geometry": processed_invalid_geometry,
        "out_of_singapore_bounds_count": len(out_of_bounds),
        "out_of_singapore_bounds_subzone_codes": out_of_bounds,
        "missing_required_field_count": len(missing_fields),
        "missing_required_fields": missing_fields,
        "duplicate_subzone_codes": duplicate_values(record["subzone_code"] for record in records),
        "duplicate_geo_ids": duplicate_values(record["geo_id"] for record in records),
        "source_crs_interpretation": "GeoJSON coordinates validated as WGS84 longitude/latitude under RFC 7946; no coordinate reprojection was silently inferred.",
        "area_calculation_crs": "EPSG:3414",
    }
    planning_names_by_code: dict[str, set[str]] = defaultdict(set)
    planning_codes_by_name: dict[str, set[str]] = defaultdict(set)
    for record in records:
        planning_names_by_code[record["planning_area_code"]].add(record["planning_area_name"])
        planning_codes_by_name[record["planning_area_name"]].add(record["planning_area_code"])
    quality["planning_area_codes_with_multiple_names"] = {
        code: sorted(names) for code, names in planning_names_by_code.items() if len(names) > 1
    }
    quality["planning_area_names_with_multiple_codes"] = {
        name: sorted(codes) for name, codes in planning_codes_by_name.items() if len(codes) > 1
    }
    return {
        "records": records,
        "geometries": geometries,
        "geojson": {"type": "FeatureCollection", "features": output_features},
        "quality": quality,
    }


def build_population_crosswalk(
    population_pairs: list[dict[str, str]], boundary_records: list[dict[str, Any]]
) -> dict[str, Any]:
    boundary_index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in boundary_records:
        key = (normalize_name(record["planning_area_name"]), normalize_name(record["subzone_name"]))
        boundary_index[key].append(record)

    rows: list[dict[str, Any]] = []
    matched_boundary_codes: set[str] = set()
    unmatched: list[dict[str, str]] = []
    ambiguous: list[dict[str, Any]] = []
    for pair in sorted(population_pairs, key=lambda item: (item["planning_area_name"], item["subzone_name"])):
        key = (normalize_name(pair["planning_area_name"]), normalize_name(pair["subzone_name"]))
        matches = boundary_index.get(key, [])
        base = {
            "source_id_population": "S001",
            "source_id_geography": "S003",
            "population_planning_area_name": pair["planning_area_name"],
            "population_subzone_name": pair["subzone_name"],
            "normalized_planning_area_name": key[0],
            "normalized_subzone_name": key[1],
            "match_method": "exact_after_case_whitespace_normalization",
        }
        if len(matches) == 1:
            match = matches[0]
            matched_boundary_codes.add(match["subzone_code"])
            rows.append(
                {
                    **base,
                    "match_status": "matched",
                    "geo_id": match["geo_id"],
                    "planning_area_code": match["planning_area_code"],
                    "subzone_code": match["subzone_code"],
                    "boundary_planning_area_name": match["planning_area_name"],
                    "boundary_subzone_name": match["subzone_name"],
                }
            )
        elif not matches:
            item = {"planning_area_name": pair["planning_area_name"], "subzone_name": pair["subzone_name"]}
            unmatched.append(item)
            rows.append(
                {
                    **base,
                    "match_status": "unmatched",
                    "geo_id": None,
                    "planning_area_code": None,
                    "subzone_code": None,
                    "boundary_planning_area_name": None,
                    "boundary_subzone_name": None,
                }
            )
        else:
            item = {
                "planning_area_name": pair["planning_area_name"],
                "subzone_name": pair["subzone_name"],
                "candidate_subzone_codes": sorted(match["subzone_code"] for match in matches),
            }
            ambiguous.append(item)
            rows.append(
                {
                    **base,
                    "match_status": "ambiguous",
                    "geo_id": None,
                    "planning_area_code": None,
                    "subzone_code": None,
                    "boundary_planning_area_name": None,
                    "boundary_subzone_name": None,
                }
            )

    boundary_only = [
        {
            "planning_area_name": record["planning_area_name"],
            "subzone_name": record["subzone_name"],
            "subzone_code": record["subzone_code"],
        }
        for record in boundary_records
        if record["subzone_code"] not in matched_boundary_codes
    ]
    return {
        "rows": rows,
        "summary": {
            "population_pair_count": len(population_pairs),
            "matched_count": sum(row["match_status"] == "matched" for row in rows),
            "unmatched_count": len(unmatched),
            "ambiguous_count": len(ambiguous),
            "boundary_only_count": len(boundary_only),
            "unmatched": unmatched,
            "ambiguous": ambiguous,
            "boundary_only": boundary_only,
            "fuzzy_matching_used": False,
            "normalization": "uppercase, trim and collapse whitespace only",
        },
    }


def enrich_population_rows(
    records: list[dict[str, Any]], crosswalk_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    lookup = {
        (row["population_planning_area_name"], row["population_subzone_name"]): row
        for row in crosswalk_rows
    }
    enriched: list[dict[str, Any]] = []
    for record in records:
        match = lookup[(record["planning_area_name"], record["subzone_name"])]
        enriched.append(
            {
                **record,
                "geo_id": match["geo_id"],
                "planning_area_code": match["planning_area_code"],
                "subzone_code": match["subzone_code"],
                "geography_match_status": match["match_status"],
            }
        )
    return enriched


def write_boundary_geojson(path: Path, payload: dict[str, Any]) -> None:
    write_json(path, payload)
