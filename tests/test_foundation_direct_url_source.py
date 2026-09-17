from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tuition_location_analytics.foundation.common import sha256_file, write_json
from tuition_location_analytics.foundation.sources import acquire_direct_url_source

_PDF_BYTES = b"%PDF-1.6 fixture bytes for testing only"
_PDF_CHECKSUM = hashlib.sha256(_PDF_BYTES).hexdigest()

_SOURCE = {
    "source_id": "S032",
    "publisher": "Land Transport Authority",
    "title": "System Map (SM-26-01-EN)",
    "landing_url": "https://example.invalid/rail_network.html",
    "resource_url": "https://example.invalid/system-map.pdf",
    "raw_directory": "s032_lta_system_map",
    "raw_filename": "lta-system-map-sm-26-01-en.pdf",
    "expected_sha256": _PDF_CHECKSUM,
    "expected_content_type": "application/pdf",
    "use_limitation": "test fixture",
}


def _headers(content_type: str = "application/pdf") -> dict[str, str]:
    return {"content-type": content_type, "content-length": str(len(_PDF_BYTES))}


class DirectUrlAcquisitionTests(unittest.TestCase):
    def test_fresh_download_verifies_checksum_and_writes_immutable_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            with patch(
                "tuition_location_analytics.foundation.sources._request_bytes",
                return_value=(_PDF_BYTES, 200, _SOURCE["resource_url"], _headers()),
            ) as mocked:
                result = acquire_direct_url_source(repo_root, _SOURCE, "2031-01-01")
            mocked.assert_called_once()
            self.assertEqual(result["acquisition_status"], "downloaded")
            self.assertTrue(result["raw_path"].exists())
            self.assertEqual(sha256_file(result["raw_path"]), _PDF_CHECKSUM)
            metadata = json.loads(result["metadata_path"].read_text(encoding="utf-8"))
            self.assertEqual(metadata["checksum"], _PDF_CHECKSUM)
            self.assertTrue(metadata["immutable"])
            # No sensitive/authentication material is recorded; only safe response headers.
            self.assertNotIn("authorization", metadata["download_response_headers"])

    def test_cached_reuse_makes_no_network_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            raw_dir = repo_root / "data/raw/s032_lta_system_map/2031-01-01"
            raw_dir.mkdir(parents=True)
            raw_path = raw_dir / _SOURCE["raw_filename"]
            raw_path.write_bytes(_PDF_BYTES)
            write_json(
                raw_dir / "snapshot-metadata.json",
                {"checksum": _PDF_CHECKSUM, "byte_size": len(_PDF_BYTES)},
            )
            with patch(
                "tuition_location_analytics.foundation.sources._request_bytes",
                side_effect=AssertionError("network must not be called for a cached reuse"),
            ):
                result = acquire_direct_url_source(repo_root, _SOURCE, "2031-01-01")
            self.assertEqual(result["acquisition_status"], "reused_immutable_snapshot")

    def test_existing_checksum_mismatch_fails_without_overwriting_or_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            raw_dir = repo_root / "data/raw/s032_lta_system_map/2031-01-01"
            raw_dir.mkdir(parents=True)
            raw_path = raw_dir / _SOURCE["raw_filename"]
            raw_path.write_bytes(b"corrupted content, wrong checksum")
            write_json(
                raw_dir / "snapshot-metadata.json",
                {"checksum": _PDF_CHECKSUM, "byte_size": len(_PDF_BYTES)},
            )
            original_bytes = raw_path.read_bytes()
            with patch(
                "tuition_location_analytics.foundation.sources._request_bytes",
                side_effect=AssertionError("network must not be called on a mismatch"),
            ):
                with self.assertRaises(RuntimeError):
                    acquire_direct_url_source(repo_root, _SOURCE, "2031-01-01")
            self.assertEqual(raw_path.read_bytes(), original_bytes, "existing file must not be overwritten")

    def test_downloaded_content_checksum_mismatch_is_rejected_and_not_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            with patch(
                "tuition_location_analytics.foundation.sources._request_bytes",
                return_value=(b"unexpected bytes", 200, _SOURCE["resource_url"], _headers()),
            ):
                with self.assertRaises(RuntimeError):
                    acquire_direct_url_source(repo_root, _SOURCE, "2031-01-01")
            raw_path = repo_root / "data/raw/s032_lta_system_map/2031-01-01" / _SOURCE["raw_filename"]
            self.assertFalse(raw_path.exists())

    def test_unexpected_content_type_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            with patch(
                "tuition_location_analytics.foundation.sources._request_bytes",
                return_value=(_PDF_BYTES, 200, _SOURCE["resource_url"], _headers("text/html")),
            ):
                with self.assertRaises(RuntimeError):
                    acquire_direct_url_source(repo_root, _SOURCE, "2031-01-01")

    def test_zero_byte_download_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            with patch(
                "tuition_location_analytics.foundation.sources._request_bytes",
                return_value=(b"", 200, _SOURCE["resource_url"], _headers()),
            ):
                with self.assertRaises(RuntimeError):
                    acquire_direct_url_source(repo_root, _SOURCE, "2031-01-01")

    def test_non_200_http_status_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            with patch(
                "tuition_location_analytics.foundation.sources._request_bytes",
                return_value=(_PDF_BYTES, 404, _SOURCE["resource_url"], _headers()),
            ):
                with self.assertRaises(RuntimeError):
                    acquire_direct_url_source(repo_root, _SOURCE, "2031-01-01")


if __name__ == "__main__":
    unittest.main()
