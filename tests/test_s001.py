from __future__ import annotations

import csv
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from tuition_location_analytics.preflight.s001 import _dbf_schema, inspect_archive


class S001Tests(unittest.TestCase):
    def test_dbf_header_schema(self) -> None:
        raw = bytearray(97)
        raw[4:8] = (2).to_bytes(4, "little")
        raw[8:10] = (97).to_bytes(2, "little")
        raw[10:12] = (21).to_bytes(2, "little")
        raw[32:43] = b"AGE\x00\x00\x00\x00\x00\x00\x00\x00"
        raw[43] = ord("N")
        raw[48] = 3
        raw[64:75] = b"RESIDENTS\x00\x00"
        raw[75] = ord("N")
        raw[80] = 8
        raw[96] = 0x0D
        schema = _dbf_schema(bytes(raw))
        self.assertEqual(schema["declared_record_count"], 2)
        self.assertEqual([field["name"] for field in schema["fields"]], ["AGE", "RESIDENTS"])

    def test_archive_inspection_reads_t3_header_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "fixture.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("T3_population.csv", "PA,SZ,AGE,SEX,RESIDENTS\nA,B,7,TOTAL,10\n")
                archive.writestr("T2_other.csv", "ignored\n")
            result = inspect_archive(archive_path)
            self.assertEqual(result["t3_candidates"], ["T3_population.csv"])
            fields = result["t3_schema_inspection"][0]["schema"]["fields"]
            self.assertEqual(fields, ["PA", "SZ", "AGE", "SEX", "RESIDENTS"])
            self.assertFalse(result["complete_dataset_loaded"])

    def test_descriptive_single_year_filename_is_t3_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "fixture.zip"
            workbook_bytes = io.BytesIO()
            shared = (
                '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                + "".join(f"<si><t>{value}</t></si>" for value in ["Planning Area", "Subzone", "Age", "Sex", "2025", "Total"])
                + "</sst>"
            )
            sheet = '''<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:E4"/><sheetData><row r="3"><c r="A3" t="s"><v>0</v></c><c r="B3" t="s"><v>1</v></c><c r="C3" t="s"><v>2</v></c><c r="D3" t="s"><v>3</v></c><c r="E3" t="s"><v>4</v></c></row><row r="4"><c r="A4" t="s"><v>5</v></c><c r="E4"><v>10</v></c></row></sheetData></worksheet>'''
            with zipfile.ZipFile(workbook_bytes, "w") as workbook:
                workbook.writestr("xl/sharedStrings.xml", shared)
                workbook.writestr("xl/worksheets/sheet1.xml", sheet)
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(
                    "Singapore Residents by Planning Area, Subzone, Single Year of Age and Sex, Jun 2025.xlsx",
                    workbook_bytes.getvalue(),
                )
            result = inspect_archive(archive_path)
            self.assertEqual(len(result["t3_schema_inspection"]), 1)
            self.assertEqual(result["t3_schema_inspection"][0]["schema"]["format"], "xlsx")


if __name__ == "__main__":
    unittest.main()
