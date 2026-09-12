from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely.geometry import Point, shape

from .common import duplicate_values, normalize_name


def _value(record: dict[str, Any], name: str) -> Any:
    if name in record:
        return record[name]
    lookup = {key.lower(): value for key, value in record.items()}
    return lookup.get(name.lower())


def _school_id(name: str, postal_code: str) -> str:
    key = f"{normalize_name(name)}\x1f{postal_code.strip()}".encode("utf-8")
    return "MOE_" + hashlib.sha256(key).hexdigest()[:16].upper()


def _canonical_postal(value: Any) -> tuple[str, str, bool]:
    source = str(value or "").strip()
    if re.fullmatch(r"\d{5}", source):
        return source.zfill(6), source, True
    return source, source, False


def process_schools(
    raw_path: Path, geocodes: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    if payload.get("success") is not True or not isinstance(payload.get("result"), dict):
        raise RuntimeError("S004 DataStore snapshot did not report success")
    source_records = payload["result"].get("records")
    if not isinstance(source_records, list):
        raise RuntimeError("S004 DataStore snapshot has no records array")
    records: list[dict[str, Any]] = []
    missing_by_field: Counter[str] = Counter()
    invalid_postal: list[dict[str, str]] = []
    mainlevels: Counter[str] = Counter()
    normalized_postal_count = 0
    transformer = Transformer.from_crs(4326, 3414, always_xy=True)
    retained_fields = (
        "school_name",
        "url_address",
        "address",
        "postal_code",
        "mrt_desc",
        "bus_desc",
        "dgp_code",
        "zone_code",
        "type_code",
        "nature_code",
        "session_code",
        "mainlevel_code",
        "sap_ind",
        "autonomous_ind",
        "gifted_ind",
        "ip_ind",
    )
    for index, source in enumerate(source_records):
        selected = {
            field: str(_value(source, field) or "").strip() for field in retained_fields
        }
        postal_code, postal_code_source, postal_normalized = _canonical_postal(
            _value(source, "postal_code")
        )
        selected["postal_code"] = postal_code
        normalized_postal_count += int(postal_normalized)
        for field in ("school_name", "address", "postal_code", "mainlevel_code"):
            if not selected[field]:
                missing_by_field[field] += 1
        if selected["postal_code"] and not re.fullmatch(r"\d{6}", selected["postal_code"]):
            invalid_postal.append(
                {"school_name": selected["school_name"], "postal_code": selected["postal_code"]}
            )
        mainlevels[selected["mainlevel_code"]] += 1
        source_record_id = str(_value(source, "_id") or index + 1)
        school_id = _school_id(selected["school_name"], selected["postal_code"])
        geocode = (geocodes or {}).get(school_id, {})
        longitude = geocode.get("longitude_wgs84")
        latitude = geocode.get("latitude_wgs84")
        if longitude is not None and latitude is not None:
            easting, northing = transformer.transform(longitude, latitude)
        else:
            easting = northing = None
        records.append(
            {
                "source_id": "S004",
                "source_record_id": source_record_id,
                "school_id": school_id,
                **selected,
                "postal_code_source": postal_code_source,
                "postal_code_normalized": postal_normalized,
                "is_primary_secondary_context": selected["mainlevel_code"].startswith(
                    ("PRIMARY", "SECONDARY", "MIXED LEVEL")
                ),
                "longitude_wgs84": longitude,
                "latitude_wgs84": latitude,
                "easting_3414": easting,
                "northing_3414": northing,
                "coordinate_source_id": (
                    "S007" if longitude is not None and latitude is not None else None
                ),
                "coordinate_lookup_source_id": "S007" if geocode else None,
                "coordinate_status": geocode.get("status", "not_supplied_by_source"),
            }
        )
    quality = {
        "source_record_count": len(source_records),
        "processed_record_count": len(records),
        "primary_secondary_context_count": sum(
            record["is_primary_secondary_context"] for record in records
        ),
        "mainlevel_counts": dict(sorted(mainlevels.items())),
        "missing_required_by_field": dict(missing_by_field),
        "invalid_postal_count": len(invalid_postal),
        "invalid_postal_examples": invalid_postal[:20],
        "leading_zero_postal_normalization_count": normalized_postal_count,
        "duplicate_source_record_ids": duplicate_values(record["source_record_id"] for record in records),
        "duplicate_school_ids": duplicate_values(record["school_id"] for record in records),
        "duplicate_normalized_name_postal": duplicate_values(
            normalize_name(record["school_name"]) + "|" + record["postal_code"] for record in records
        ),
        "coordinate_missing_count": sum(record["longitude_wgs84"] is None for record in records),
        "coordinate_bounds_validated_count": sum(record["longitude_wgs84"] is not None for record in records),
        "coordinate_status_counts": dict(
            Counter(record["coordinate_status"] for record in records)
        ),
        "unresolved_coordinates": [
            {
                "school_id": record["school_id"],
                "school_name": record["school_name"],
                "postal_code": record["postal_code"],
                "coordinate_status": record["coordinate_status"],
            }
            for record in records
            if record["longitude_wgs84"] is None
        ],
        "coordinate_limitation": "S004 supplies no coordinates. S007 exact-postal search coordinates are retained only when one unique in-bounds coordinate is returned; unresolved or ambiguous coordinates remain null.",
        "retained_personal_contact_fields": False,
    }
    return {"records": records, "quality": quality}


def process_point_source(
    raw_path: Path,
    *,
    source_id: str,
    singapore_bounds: dict[str, float],
) -> dict[str, Any]:
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
        raise RuntimeError(f"{source_id} is not a GeoJSON FeatureCollection")
    transformer = Transformer.from_crs(4326, 3414, always_xy=True)
    records: list[dict[str, Any]] = []
    geometries: list[Point] = []
    invalid_geometry: list[dict[str, Any]] = []
    out_of_bounds: list[str] = []
    missing_required: list[dict[str, Any]] = []

    for index, feature in enumerate(payload["features"]):
        properties = feature.get("properties") or {}
        geometry = shape(feature.get("geometry"))
        if source_id == "S005":
            object_id = str(_value(properties, "OBJECTID") or "")
            station_name = str(_value(properties, "STATION_NA") or "").strip()
            exit_code = str(_value(properties, "EXIT_CODE") or "").strip()
            stable_source_id = object_id
            point_id = f"MRT_EXIT_{object_id}"
            required_values = {
                "OBJECTID": object_id,
                "STATION_NA": station_name,
                "EXIT_CODE": exit_code,
            }
            source_fields = {
                "station_name": station_name,
                "exit_code": exit_code,
                "bus_stop_number": None,
                "bus_roof_number": None,
                "source_unique_id": object_id,
            }
            business_key = normalize_name(station_name) + "|" + normalize_name(exit_code)
        elif source_id == "S006":
            unique_id = str(_value(properties, "UNIQUE_ID") or "")
            bus_stop_number = str(_value(properties, "BUS_STOP_NUM") or "").strip()
            bus_roof_number = str(_value(properties, "BUS_ROOF_NUM") or "").strip()
            stable_source_id = unique_id
            point_id = f"BUS_STOP_{unique_id}"
            required_values = {"UNIQUE_ID": unique_id, "BUS_STOP_NUM": bus_stop_number}
            source_fields = {
                "station_name": None,
                "exit_code": None,
                "bus_stop_number": bus_stop_number,
                "bus_roof_number": bus_roof_number or None,
                "source_unique_id": unique_id,
            }
            business_key = bus_stop_number
        else:
            raise ValueError(f"unsupported point source {source_id}")

        missing = [name for name, value in required_values.items() if not value]
        if missing:
            missing_required.append({"feature_index": index, "fields": missing})
        if geometry.geom_type != "Point" or geometry.is_empty or not geometry.is_valid:
            invalid_geometry.append({"source_record_id": stable_source_id, "geometry_type": geometry.geom_type})
            continue
        longitude, latitude = geometry.x, geometry.y
        if not (
            singapore_bounds["minimum_longitude"] <= longitude <= singapore_bounds["maximum_longitude"]
            and singapore_bounds["minimum_latitude"] <= latitude <= singapore_bounds["maximum_latitude"]
        ):
            out_of_bounds.append(stable_source_id)
        easting, northing = transformer.transform(longitude, latitude)
        records.append(
            {
                "source_id": source_id,
                "transit_point_id": point_id,
                **source_fields,
                "longitude_wgs84": longitude,
                "latitude_wgs84": latitude,
                "easting_3414": easting,
                "northing_3414": northing,
                "exchange_crs": "EPSG:4326",
                "metric_crs": "EPSG:3414",
                "business_key": business_key,
            }
        )
        geometries.append(geometry)

    coordinate_keys = [
        f"{record['longitude_wgs84']:.8f}|{record['latitude_wgs84']:.8f}" for record in records
    ]
    quality = {
        "source_feature_count": len(payload["features"]),
        "processed_point_count": len(records),
        "invalid_geometry_count": len(invalid_geometry),
        "invalid_geometry": invalid_geometry,
        "out_of_singapore_bounds_count": len(out_of_bounds),
        "out_of_singapore_bounds_source_ids": out_of_bounds,
        "missing_required_field_count": len(missing_required),
        "missing_required_fields": missing_required,
        "duplicate_transit_point_ids": duplicate_values(record["transit_point_id"] for record in records),
        "duplicate_source_unique_ids": duplicate_values(record["source_unique_id"] for record in records),
        "duplicate_business_keys": duplicate_values(record["business_key"] for record in records),
        "duplicate_coordinate_count": len(duplicate_values(coordinate_keys)),
        "duplicate_coordinates": duplicate_values(coordinate_keys)[:20],
        "coordinate_bounds_validated_count": len(records),
        "source_crs_interpretation": "GeoJSON coordinates validated as WGS84 longitude/latitude under RFC 7946.",
    }
    return {"records": records, "geometries": geometries, "quality": quality}
