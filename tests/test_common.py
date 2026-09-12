from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tuition_location_analytics.preflight.common import (
    contains_secret_like,
    read_env,
    scan_reportable_files,
)


class CommonTests(unittest.TestCase):
    def test_read_env_returns_only_expected_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "ONEMAP_EMAIL=person@example.test\n"
                "ONEMAP_EMAIL_PASSWORD='private-value'\n"
                "UNRELATED=ignored\n",
                encoding="utf-8",
            )
            self.assertEqual(
                read_env(path),
                {
                    "ONEMAP_EMAIL": "person@example.test",
                    "ONEMAP_EMAIL_PASSWORD": "private-value",
                },
            )

    def test_secret_like_detection(self) -> None:
        self.assertTrue(contains_secret_like("Authorization: " + ("a" * 16)))
        self.assertTrue(contains_secret_like("prefix-known-value-suffix", ["known-value"]))
        self.assertFalse(contains_secret_like("ONEMAP_EMAIL="))

    def test_scan_ignores_env_but_detects_leak(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("ONEMAP_EMAIL_PASSWORD=known-value\n", encoding="utf-8")
            (root / "safe.txt").write_text("ONEMAP_EMAIL_PASSWORD=\n", encoding="utf-8")
            self.assertEqual(scan_reportable_files(root, ["known-value"]), [])
            (root / "leak.txt").write_text("known-value\n", encoding="utf-8")
            self.assertEqual(scan_reportable_files(root, ["known-value"]), ["leak.txt"])


if __name__ == "__main__":
    unittest.main()
