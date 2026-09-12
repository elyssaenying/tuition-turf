from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tuition_location_analytics.foundation.cli import (
    _foundation_paths,
    _overall_status,
    _s007_preflight_summary,
    run,
)
from tuition_location_analytics.foundation.common import scan_foundation_outputs_for_secrets
from tuition_location_analytics.foundation.geocode import school_geocode_cache_path


class FoundationControlTests(unittest.TestCase):
    def test_configured_snapshot_date_controls_all_foundation_output_paths(self) -> None:
        root = Path("/repository")
        processed, reports = _foundation_paths(root, "2031-04-05")
        cache = school_geocode_cache_path(root, "2031-04-05", "a" * 64)
        self.assertEqual(processed, root / "data/processed/foundation/2031-04-05")
        self.assertEqual(reports, root / "reports/foundation/2031-04-05")
        self.assertEqual(cache.parent, root / "data/interim/foundation/2031-04-05")

    def test_preflight_result_is_selected_explicitly_and_must_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "reports/preflight/earlier/result.json"
            selected.parent.mkdir(parents=True)
            selected.write_text(
                json.dumps(
                    {
                        "s007": {
                            "routes": [
                                {"mode": "walk", "category": "success"},
                                {"mode": "pt", "category": "missing_route"},
                            ],
                            "rate_limited_count": 0,
                        }
                    }
                ),
                encoding="utf-8",
            )
            summary = _s007_preflight_summary(
                root, "reports/preflight/earlier/result.json"
            )
            self.assertEqual(summary["preflight_result_ref"], "reports/preflight/earlier/result.json")
            self.assertEqual(summary["walking_success"], 1)
            self.assertEqual(summary["pt_missing_route"], 1)
            with self.assertRaisesRegex(RuntimeError, "does not exist"):
                _s007_preflight_summary(root, "reports/preflight/missing.json")

    def test_missing_preflight_reference_fails_before_acquisition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_dir = root / "config/foundation"
            config_dir.mkdir(parents=True)
            (config_dir / "sources.json").write_text(
                json.dumps({"sources": []}), encoding="utf-8"
            )
            (config_dir / "run.json").write_text(
                json.dumps(
                    {
                        "snapshot_date": "2031-04-05",
                        "preflight_result_ref": "reports/preflight/missing.json",
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "tuition_location_analytics.foundation.cli.acquire_sources"
            ) as acquire:
                with self.assertRaisesRegex(RuntimeError, "does not exist"):
                    run(root, credential_values=["synthetic-value-not-present"])
            acquire.assert_not_called()

    def test_secret_scan_finding_blocks_foundation_status_without_persisting_value(self) -> None:
        secret = "synthetic-foundation-secret-987654"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            processed = root / "data/processed/foundation/2031-04-05"
            reports = root / "reports/foundation/2031-04-05"
            processed.mkdir(parents=True)
            reports.mkdir(parents=True)
            (processed / "schools.csv").write_text(
                f"school_id,note\nS1,{secret}\n", encoding="utf-8"
            )
            (processed / "schools.parquet").write_bytes(secret.encode("utf-8"))
            scan = scan_foundation_outputs_for_secrets(
                root,
                processed_dir=processed,
                report_dir=reports,
                credential_values=[secret],
            )
        self.assertEqual(scan["status"], "fail")
        self.assertEqual(scan["assurance"], "full")
        self.assertEqual(scan["generic_pattern_finding_count"], 0)
        self.assertEqual(scan["exact_credential_finding_count"], 1)
        self.assertEqual(scan["exact_credential_comparison_status"], "performed")
        self.assertEqual(scan["finding_paths"], ["data/processed/foundation/2031-04-05/schools.csv"])
        self.assertNotIn(secret, json.dumps(scan))
        self.assertEqual(
            _overall_status([{"status": "warning"}, {"status": scan["status"]}]),
            "failed",
        )

    def test_no_credentials_and_clean_outputs_is_limited_warning_not_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            processed = root / "data/processed/foundation/2031-04-05"
            reports = root / "reports/foundation/2031-04-05"
            processed.mkdir(parents=True)
            reports.mkdir(parents=True)
            (reports / "report.json").write_text("{}\n", encoding="utf-8")
            scan = scan_foundation_outputs_for_secrets(
                root,
                processed_dir=processed,
                report_dir=reports,
                credential_values=[],
            )
        self.assertEqual(scan["status"], "warning")
        self.assertEqual(scan["assurance"], "limited")
        self.assertFalse(scan["credential_values_available"])
        self.assertEqual(
            scan["exact_credential_comparison_status"],
            "not_performed_credentials_unavailable",
        )
        self.assertEqual(scan["generic_pattern_scan_status"], "pass")
        self.assertEqual(scan["finding_count"], 0)
        self.assertEqual(_overall_status([{"status": scan["status"]}]), "passed_with_warnings")

    def test_no_credentials_and_generic_secret_pattern_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            processed = root / "data/processed/foundation/2031-04-05"
            reports = root / "reports/foundation/2031-04-05"
            processed.mkdir(parents=True)
            reports.mkdir(parents=True)
            (reports / "unsafe.txt").write_text(
                "Authorization: Bearer synthetic-token-value-987654\n",
                encoding="utf-8",
            )
            scan = scan_foundation_outputs_for_secrets(
                root,
                processed_dir=processed,
                report_dir=reports,
                credential_values=[],
            )
        self.assertEqual(scan["status"], "fail")
        self.assertEqual(scan["assurance"], "limited")
        self.assertEqual(scan["generic_pattern_scan_status"], "fail")
        self.assertEqual(scan["generic_pattern_finding_count"], 1)
        self.assertEqual(scan["exact_credential_finding_count"], 0)
        self.assertNotIn("synthetic-token-value-987654", json.dumps(scan))


if __name__ == "__main__":
    unittest.main()
