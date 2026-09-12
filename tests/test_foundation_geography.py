from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tuition_location_analytics.foundation.geography import (
    build_population_crosswalk,
    process_boundaries,
)


class FoundationGeographyTests(unittest.TestCase):
    def test_boundary_projection_and_exact_normalized_crosswalk(self) -> None:
        feature = {
            "type": "Feature",
            "properties": {
                "SUBZONE_NO": 1,
                "SUBZONE_N": "Example Subzone",
                "SUBZONE_C": "EXSZ",
                "PLN_AREA_N": "Example Area",
                "PLN_AREA_C": "EX",
                "REGION_N": "Example Region",
                "REGION_C": "ER",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[103.8, 1.3], [103.81, 1.3], [103.81, 1.31], [103.8, 1.31], [103.8, 1.3]]],
            },
        }
        bounds = {
            "minimum_longitude": 103.5,
            "maximum_longitude": 104.2,
            "minimum_latitude": 1.1,
            "maximum_latitude": 1.6,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "boundary.geojson"
            path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}), encoding="utf-8")
            boundary = process_boundaries(path, bounds)
        self.assertGreater(boundary["records"][0]["area_sqm_3414"], 0)
        self.assertNotIn(
            "duplicate_planning_area_code_name_pairs", boundary["quality"]
        )
        self.assertEqual(boundary["quality"]["planning_area_codes_with_multiple_names"], {})
        self.assertEqual(boundary["quality"]["planning_area_names_with_multiple_codes"], {})
        crosswalk = build_population_crosswalk(
            [{"planning_area_name": " example area ", "subzone_name": "EXAMPLE   SUBZONE"}],
            boundary["records"],
        )
        self.assertEqual(crosswalk["summary"]["matched_count"], 1)
        self.assertFalse(crosswalk["summary"]["fuzzy_matching_used"])

    def test_near_name_is_not_fuzzy_matched(self) -> None:
        boundaries = [
            {
                "planning_area_name": "Example Area",
                "subzone_name": "Example Subzone",
                "subzone_code": "EXSZ",
                "planning_area_code": "EX",
                "geo_id": "MP2019_SZ_EXSZ",
            }
        ]
        crosswalk = build_population_crosswalk(
            [{"planning_area_name": "Example Area", "subzone_name": "Example Sub-zone"}],
            boundaries,
        )
        self.assertEqual(crosswalk["summary"]["unmatched_count"], 1)

    def test_planning_area_code_name_consistency_is_computed(self) -> None:
        features = []
        for index, area_name in enumerate(("Example Area", "Conflicting Area"), start=1):
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "SUBZONE_NO": index,
                        "SUBZONE_N": f"Subzone {index}",
                        "SUBZONE_C": f"SZ{index}",
                        "PLN_AREA_N": area_name,
                        "PLN_AREA_C": "EX",
                        "REGION_N": "Example Region",
                        "REGION_C": "ER",
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [103.80 + index / 100, 1.30],
                            [103.805 + index / 100, 1.30],
                            [103.805 + index / 100, 1.305],
                            [103.80 + index / 100, 1.305],
                            [103.80 + index / 100, 1.30],
                        ]],
                    },
                }
            )
        bounds = {
            "minimum_longitude": 103.5,
            "maximum_longitude": 104.2,
            "minimum_latitude": 1.1,
            "maximum_latitude": 1.6,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "boundary.geojson"
            path.write_text(
                json.dumps({"type": "FeatureCollection", "features": features}),
                encoding="utf-8",
            )
            result = process_boundaries(path, bounds)
        self.assertEqual(
            result["quality"]["planning_area_codes_with_multiple_names"],
            {"EX": ["Conflicting Area", "Example Area"]},
        )


if __name__ == "__main__":
    unittest.main()
