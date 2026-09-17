from __future__ import annotations

import unittest

from pyproj import Transformer
from shapely.geometry import Polygon

from tuition_location_analytics.competitors.geography import planning_area_for_coordinate


def _square_around(lon: float, lat: float, half_extent_m: float = 500.0):
    forward = Transformer.from_crs(4326, 3414, always_xy=True)
    easting, northing = forward.transform(lon, lat)
    return Polygon(
        [
            (easting - half_extent_m, northing - half_extent_m),
            (easting + half_extent_m, northing - half_extent_m),
            (easting + half_extent_m, northing + half_extent_m),
            (easting - half_extent_m, northing + half_extent_m),
        ]
    )


class PlanningAreaFromCoordinateTests(unittest.TestCase):
    def test_coordinate_inside_polygon_resolves_to_its_planning_area(self) -> None:
        polygons = [("EXAMPLE AREA", _square_around(103.85, 1.30))]
        result = planning_area_for_coordinate(103.85, 1.30, polygons)
        self.assertEqual(result, "EXAMPLE AREA")

    def test_coordinate_outside_every_polygon_is_unresolved_not_guessed(self) -> None:
        polygons = [("EXAMPLE AREA", _square_around(103.85, 1.30))]
        result = planning_area_for_coordinate(103.90, 1.40, polygons)
        self.assertIsNone(result)

    def test_missing_coordinate_is_unresolved(self) -> None:
        polygons = [("EXAMPLE AREA", _square_around(103.85, 1.30))]
        self.assertIsNone(planning_area_for_coordinate(None, None, polygons))
        self.assertIsNone(planning_area_for_coordinate(103.85, None, polygons))

    def test_planning_area_is_never_taken_from_a_search_query_label(self) -> None:
        # Regression for the corrected design: the function's only inputs are a
        # coordinate and geometry, so it structurally cannot fall back to a
        # planning-area name supplied by the caller's search query.
        import inspect

        signature = inspect.signature(planning_area_for_coordinate)
        self.assertEqual(list(signature.parameters), ["longitude_wgs84", "latitude_wgs84", "polygons"])


if __name__ == "__main__":
    unittest.main()
