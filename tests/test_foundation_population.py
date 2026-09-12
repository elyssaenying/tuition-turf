from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from tuition_location_analytics.foundation.population import process_population


def _fixture_archive(path: Path, duplicate: bool = False) -> None:
    strings = ["Planning Area", "Subzone", "Age", "Sex", "2025", "Total", "Example", "Example Subzone", "Males", "Females", "-"]
    index = {value: position for position, value in enumerate(strings)}

    def shared_cell(column: str, row: int, value: str) -> str:
        return f'<c r="{column}{row}" t="s"><v>{index[value]}</v></c>'

    def numeric_cell(column: str, row: int, value: int) -> str:
        return f'<c r="{column}{row}"><v>{value}</v></c>'

    rows = [
        '<row r="3">'
        + "".join(shared_cell(column, 3, value) for column, value in zip("ABCDE", strings[:5]))
        + "</row>"
    ]
    row_number = 4
    for sex, count in (("Total", None), ("Males", 0), ("Females", 0)):
        count_cell = (
            shared_cell("E", row_number, "-")
            if count is None
            else numeric_cell("E", row_number, count)
        )
        rows.append(
            f'<row r="{row_number}">'
            + shared_cell("A", row_number, "Example")
            + shared_cell("B", row_number, "Example Subzone")
            + numeric_cell("C", row_number, 6)
            + shared_cell("D", row_number, sex)
            + count_cell
            + "</row>"
        )
        row_number += 1
    for age in range(7, 17):
        values = [("Total", 20), ("Males", 10), ("Females", 10)]
        for sex, count in values:
            count_cell = shared_cell("E", row_number, "-") if age == 7 and sex == "Total" else numeric_cell("E", row_number, count)
            rows.append(
                f'<row r="{row_number}">'
                + shared_cell("A", row_number, "Example")
                + shared_cell("B", row_number, "Example Subzone")
                + numeric_cell("C", row_number, age)
                + shared_cell("D", row_number, sex)
                + count_cell
                + "</row>"
            )
            row_number += 1
    if duplicate:
        rows.append(rows[-1].replace(f'r="{row_number - 1}"', f'r="{row_number}"'))
    shared_xml = (
        '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        + "".join(f"<si><t>{escape(value)}</t></si>" for value in strings)
        + "</sst>"
    )
    sheet_xml = (
        '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        + "".join(rows)
        + "</sheetData></worksheet>"
    )
    workbook = io.BytesIO()
    with zipfile.ZipFile(workbook, "w") as target:
        target.writestr("xl/sharedStrings.xml", shared_xml)
        target.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    with zipfile.ZipFile(path, "w") as outer:
        outer.writestr(
            "Singapore Residents by Planning Area, Subzone, Single Year of Age and Sex, Jun 2025.xlsx",
            workbook.getvalue(),
        )


class FoundationPopulationTests(unittest.TestCase):
    def test_total_sex_target_proxy_and_nil_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "population.zip"
            _fixture_archive(archive)
            result = process_population(archive)
        self.assertEqual(len(result["target_age_rows"]), 10)
        self.assertEqual(result["proxy_rows"][0]["accessible_target_population_proxy"], 180)
        self.assertEqual(result["proxy_rows"][0]["nil_or_negligible_component_count"], 1)
        self.assertEqual(result["quality"]["source_composite_key_duplicate_count"], 0)
        self.assertEqual(
            result["quality"]["target_age_total_sex_nil_or_negligible_marker_count"], 1
        )
        self.assertEqual(
            result["quality"]["whole_workbook_nil_or_negligible_marker_count"], 2
        )
        self.assertNotIn("nil_or_negligible_marker_count", result["quality"])

    def test_duplicate_composite_key_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "population.zip"
            _fixture_archive(archive, duplicate=True)
            result = process_population(archive)
        self.assertEqual(result["quality"]["source_composite_key_duplicate_count"], 1)


if __name__ == "__main__":
    unittest.main()
