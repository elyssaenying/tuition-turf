from __future__ import annotations

from pathlib import Path
from typing import Any

from shapely import wkb
from shapely.geometry import Point


def load_planning_area_polygons(mp2019_subzones_parquet: Path) -> list[tuple[str, Any]]:
    """Load (planning_area_name, EPSG:3414 geometry) pairs from the approved,
    unmodified MP2019 subzone geoparquet. Read-only against approved node/
    foundation output; never mutated."""
    import pyarrow.parquet as pq
    from pyproj import Transformer

    table = pq.read_table(mp2019_subzones_parquet)
    rows = table.to_pylist()
    forward = Transformer.from_crs(4326, 3414, always_xy=True)
    from shapely.ops import transform as shapely_transform

    polygons = []
    for row, geometry_bytes in zip(rows, table.column("geometry").to_pylist()):
        geometry = wkb.loads(geometry_bytes)
        metric_geometry = shapely_transform(forward.transform, geometry)
        polygons.append((row["planning_area_name"], metric_geometry))
    return polygons


def planning_area_for_coordinate(
    longitude_wgs84: float | None,
    latitude_wgs84: float | None,
    polygons: list[tuple[str, Any]],
) -> str | None:
    """Deterministic point-in-polygon lookup against the approved MP2019 subzone
    geometry. Returns None (unresolved) rather than guessing when the coordinate
    is missing or falls outside every polygon (for example due to indicative
    no-sea boundary gaps)."""
    if longitude_wgs84 is None or latitude_wgs84 is None:
        return None
    from pyproj import Transformer

    forward = Transformer.from_crs(4326, 3414, always_xy=True)
    easting, northing = forward.transform(longitude_wgs84, latitude_wgs84)
    point = Point(easting, northing)
    for planning_area_name, geometry in polygons:
        if geometry.contains(point):
            return planning_area_name
    return None
