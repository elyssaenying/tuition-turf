from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pyproj import Transformer

from tuition_location_analytics.nodes.landuse import (
    build_commercial_nodes,
    process_land_use,
)


class CommercialEvidenceTests(unittest.TestCase):
    def test_exit_buffers_evidence_independence_and_missing_signal(self) -> None:
        payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"OBJECTID": 1, "LU_DESC": "COMMERCIAL", "GPR": "3.0"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [103.799, 1.299],
                            [103.801, 1.299],
                            [103.801, 1.301],
                            [103.799, 1.301],
                            [103.799, 1.299],
                        ]],
                    },
                },
                {
                    "type": "Feature",
                    "properties": {"OBJECTID": 2, "LU_DESC": "BUSINESS 2"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [103.802, 1.299],
                            [103.803, 1.299],
                            [103.803, 1.300],
                            [103.802, 1.300],
                            [103.802, 1.299],
                        ]],
                    },
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "landuse.geojson"
            path.write_text(json.dumps(payload), encoding="utf-8")
            land_use = process_land_use(path, ["COMMERCIAL"])
        easting, northing = Transformer.from_crs(4326, 3414, always_xy=True).transform(
            103.8, 1.3
        )
        complex_record = {
            "station_complex_id": "STC_EXAMPLE",
            "station_name": "Example MRT Station",
            "rail_mode": "mrt",
            "representative_longitude_wgs84": 103.8,
            "representative_latitude_wgs84": 1.3,
            "exit_count": 1,
            "operational_status": "verified_operational",
            "operational_status_basis": "test fixture",
            "operational_status_evidence_json": "[]",
        }
        membership = {
            "station_complex_id": "STC_EXAMPLE",
            "easting_3414": easting,
            "northing_3414": northing,
        }
        result = build_commercial_nodes(
            [complex_record],
            [membership],
            [],
            land_use,
            buffer_metres=[400, 800],
            minimum_independent_signals=2,
        )
        self.assertEqual(len(result["candidates"]), 1)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["commercial_signal_count"], 1)
        self.assertEqual(candidate["qualification_status"], "provisional")
        self.assertEqual(len(result["evidence"]), 4)
        hdb = [
            row
            for row in result["evidence"]
            if row["independent_signal_key"] == "hdb_commercial_building"
        ]
        self.assertTrue(all(row["measurement_status"] == "missing" for row in hdb))
        self.assertTrue(all(row["relevant_feature_count"] is None for row in hdb))
        self.assertFalse(result["quality"]["missing_evidence_treated_as_zero"])

    def test_no_observed_commercial_signal_requires_review(self) -> None:
        payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"OBJECTID": 1, "LU_DESC": "COMMERCIAL"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [103.70, 1.20],
                            [103.701, 1.20],
                            [103.701, 1.201],
                            [103.70, 1.201],
                            [103.70, 1.20],
                        ]],
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "landuse.geojson"
            path.write_text(json.dumps(payload), encoding="utf-8")
            land_use = process_land_use(path, ["COMMERCIAL"])
        easting, northing = Transformer.from_crs(4326, 3414, always_xy=True).transform(
            103.9, 1.4
        )
        result = build_commercial_nodes(
            [
                {
                    "station_complex_id": "STC_FAR",
                    "station_name": "Far MRT Station",
                    "rail_mode": "mrt",
                    "representative_longitude_wgs84": 103.9,
                    "representative_latitude_wgs84": 1.4,
                    "exit_count": 1,
                    "operational_status": "verified_operational",
                    "operational_status_basis": "test fixture",
                    "operational_status_evidence_json": "[]",
                }
            ],
            [
                {
                    "station_complex_id": "STC_FAR",
                    "easting_3414": easting,
                    "northing_3414": northing,
                }
            ],
            [],
            land_use,
            buffer_metres=[400, 800],
            minimum_independent_signals=2,
        )
        self.assertEqual(result["candidates"][0]["qualification_status"], "needs_manual_review")
        self.assertEqual(result["quality"]["review_queue_row_count"], 1)


if __name__ == "__main__":
    unittest.main()
