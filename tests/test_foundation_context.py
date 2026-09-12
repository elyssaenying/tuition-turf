from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tuition_location_analytics.foundation.context import process_point_source, process_schools


BOUNDS = {
    "minimum_longitude": 103.5,
    "maximum_longitude": 104.2,
    "minimum_latitude": 1.1,
    "maximum_latitude": 1.6,
}


class FoundationContextTests(unittest.TestCase):
    def test_school_fields_and_geocode_are_kept_separate(self) -> None:
        payload = {
            "success": True,
            "result": {
                "records": [
                    {
                        "_id": 1,
                        "school_name": "Example Primary School",
                        "address": "1 Example Road",
                        "postal_code": "123456",
                        "mainlevel_code": "PRIMARY",
                    }
                ]
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schools.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            initial = process_schools(path)
            school_id = initial["records"][0]["school_id"]
            result = process_schools(
                path,
                {
                    school_id: {
                        "status": "resolved_exact_postal_unique_coordinate",
                        "longitude_wgs84": 103.8,
                        "latitude_wgs84": 1.3,
                    }
                },
            )
        record = result["records"][0]
        self.assertEqual(record["coordinate_source_id"], "S007")
        self.assertEqual(record["coordinate_lookup_source_id"], "S007")
        self.assertIsNotNone(record["easting_3414"])
        self.assertNotIn("principal_name", record)

    def test_unresolved_school_does_not_claim_coordinate_provenance(self) -> None:
        payload = {
            "success": True,
            "result": {
                "records": [
                    {
                        "_id": 1,
                        "school_name": "Example Primary School",
                        "address": "1 Example Road",
                        "postal_code": "123456",
                        "mainlevel_code": "PRIMARY",
                    }
                ]
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schools.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            school_id = process_schools(path)["records"][0]["school_id"]
            result = process_schools(
                path,
                {
                    school_id: {
                        "status": "ambiguous_exact_postal_coordinates",
                        "longitude_wgs84": None,
                        "latitude_wgs84": None,
                    }
                },
            )
        record = result["records"][0]
        self.assertIsNone(record["coordinate_source_id"])
        self.assertEqual(record["coordinate_lookup_source_id"], "S007")
        self.assertIsNone(record["longitude_wgs84"])
        self.assertIsNone(record["latitude_wgs84"])

    def test_five_digit_postal_is_explicitly_left_padded(self) -> None:
        payload = {
            "success": True,
            "result": {
                "records": [
                    {
                        "_id": 1,
                        "school_name": "Example Primary School",
                        "address": "1 Example Road",
                        "postal_code": 88256,
                        "mainlevel_code": "PRIMARY",
                    }
                ]
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schools.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = process_schools(path)
        self.assertEqual(result["records"][0]["postal_code"], "088256")
        self.assertEqual(result["records"][0]["postal_code_source"], "88256")
        self.assertTrue(result["records"][0]["postal_code_normalized"])

    def test_point_validation_and_duplicate_business_key(self) -> None:
        features = []
        for object_id in (1, 2):
            features.append(
                {
                    "type": "Feature",
                    "properties": {"OBJECTID": object_id, "STATION_NA": "Example", "EXIT_CODE": "A"},
                    "geometry": {"type": "Point", "coordinates": [103.8, 1.3]},
                }
            )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "points.geojson"
            path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
            result = process_point_source(path, source_id="S005", singapore_bounds=BOUNDS)
        self.assertEqual(result["quality"]["duplicate_business_keys"], ["EXAMPLE|A"])
        self.assertEqual(result["quality"]["duplicate_coordinate_count"], 1)


if __name__ == "__main__":
    unittest.main()
