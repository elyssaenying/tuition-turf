from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tuition_location_analytics.foundation.common import sanitize_url, sha256_file
from tuition_location_analytics.foundation.sources import (
    _existing_snapshot,
    source_snapshot_paths,
)


class FoundationSourceTests(unittest.TestCase):
    def test_configured_snapshot_date_controls_raw_snapshot_path(self) -> None:
        root = Path("/repository")
        raw, metadata = source_snapshot_paths(
            root,
            {
                "source_id": "S001",
                "raw_directory": "s001_population",
                "raw_filename": "population.zip",
            },
            "2031-04-05",
        )
        self.assertEqual(
            raw, root / "data/raw/s001_population/2031-04-05/population.zip"
        )
        self.assertEqual(metadata, raw.parent / "snapshot-metadata.json")

    def test_signed_download_query_is_removed(self) -> None:
        self.assertEqual(
            sanitize_url("https://example.invalid/file.geojson?Signature=secret&token=secret"),
            "https://example.invalid/file.geojson",
        )

    def test_existing_snapshot_requires_matching_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "raw.json"
            metadata = Path(directory) / "snapshot-metadata.json"
            raw.write_text("{}", encoding="utf-8")
            metadata.write_text(json.dumps({"checksum": sha256_file(raw)}), encoding="utf-8")
            result = _existing_snapshot(raw, metadata)
            self.assertEqual(result["checksum"], sha256_file(raw))
            raw.write_text('{"changed": true}', encoding="utf-8")
            with self.assertRaises(RuntimeError):
                _existing_snapshot(raw, metadata)


if __name__ == "__main__":
    unittest.main()
