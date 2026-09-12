from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .common import duplicate_values

T3_MEMBER_FRAGMENT = "Single Year of Age and Sex, Jun 2025.xlsx"
EXPECTED_FIELDS = ["Planning Area", "Subzone", "Age", "Sex", "2025"]
EXPECTED_SEXES = {"Total", "Males", "Females"}
XML_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _shared_strings(workbook: zipfile.ZipFile) -> list[str]:
    root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in item.iter(XML_NS + "t"))
        for item in root.findall(XML_NS + "si")
    ]


def _cell_value(cell: ET.Element, shared: list[str]) -> str:
    value_node = cell.find(XML_NS + "v")
    if cell.attrib.get("t") == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(XML_NS + "t"))
    if value_node is None or value_node.text is None:
        return ""
    value = value_node.text
    if cell.attrib.get("t") == "s":
        return shared[int(value)]
    return value


def _parse_count(value: str) -> tuple[int | None, str | None]:
    cleaned = value.strip()
    if cleaned == "-":
        return 0, "nil_or_negligible"
    if not cleaned:
        return None, "missing"
    try:
        numeric = float(cleaned)
    except ValueError:
        return None, f"unknown:{cleaned}"
    if not numeric.is_integer():
        return None, f"non_integer:{cleaned}"
    return int(numeric), None


def _load_rows(archive_path: Path) -> tuple[list[dict[str, str]], str]:
    with zipfile.ZipFile(archive_path) as outer:
        candidates = [name for name in outer.namelist() if T3_MEMBER_FRAGMENT in name]
        if len(candidates) != 1:
            raise RuntimeError(f"expected one S001 T3 workbook, found {len(candidates)}")
        member = candidates[0]
        workbook_bytes = outer.read(member)
    rows: list[dict[str, str]] = []
    with zipfile.ZipFile(io.BytesIO(workbook_bytes)) as workbook:
        shared = _shared_strings(workbook)
        sheet_names = sorted(
            name for name in workbook.namelist() if name.startswith("xl/worksheets/sheet")
        )
        if not sheet_names:
            raise RuntimeError("S001 workbook has no worksheet")
        header: list[str] | None = None
        with workbook.open(sheet_names[0]) as sheet:
            for _, element in ET.iterparse(sheet, events=("end",)):
                if element.tag != XML_NS + "row":
                    continue
                row_number = int(element.attrib.get("r", "0"))
                values: dict[str, str] = {}
                for cell in element.findall(XML_NS + "c"):
                    match = re.match(r"[A-Z]+", cell.attrib.get("r", ""))
                    if match:
                        values[match.group(0)] = _cell_value(cell, shared)
                if row_number == 3:
                    header = [values.get(column, "") for column in ("A", "B", "C", "D", "E")]
                    if header != EXPECTED_FIELDS:
                        raise RuntimeError(f"unexpected S001 fields: {header}")
                elif row_number > 3 and header:
                    rows.append(
                        {
                            header[index]: values.get(column, "")
                            for index, column in enumerate(("A", "B", "C", "D", "E"))
                        }
                    )
                element.clear()
    return rows, member


def process_population(
    archive_path: Path,
    *,
    target_age_min: int = 7,
    target_age_max: int = 16,
    rounding_unit: int = 10,
) -> dict[str, Any]:
    rows, member = _load_rows(archive_path)
    note_rows = [
        row
        for row in rows
        if not row["Subzone"].strip() and not row["Age"].strip() and not row["Sex"].strip()
    ]
    data_rows = [row for row in rows if row not in note_rows]
    keys: list[str] = []
    parsed: list[dict[str, Any]] = []
    unknown_markers: Counter[str] = Counter()
    negative_count = 0
    observed_ages: set[str] = set()
    observed_sexes: set[str] = set()
    marker_counts: Counter[str] = Counter()

    for row in data_rows:
        planning_area = row["Planning Area"].strip()
        subzone = row["Subzone"].strip()
        age = row["Age"].strip()
        sex = row["Sex"].strip()
        count, marker = _parse_count(row["2025"])
        key = "\x1f".join((planning_area, subzone, age, sex))
        keys.append(key)
        observed_ages.add(age)
        observed_sexes.add(sex)
        if marker:
            marker_counts[marker] += 1
            if marker not in {"nil_or_negligible", "missing"}:
                unknown_markers[marker] += 1
        if count is not None and count < 0:
            negative_count += 1
        parsed.append(
            {
                "planning_area": planning_area,
                "subzone": subzone,
                "age": age,
                "sex": sex,
                "count": count,
                "marker": marker,
            }
        )

    duplicates = duplicate_values(keys)
    target_ages = set(range(target_age_min, target_age_max + 1))
    target_rows: list[dict[str, Any]] = []
    per_subzone: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    sex_groups: dict[tuple[str, str, int], dict[str, int | None]] = defaultdict(dict)
    planning_aggregate: dict[tuple[str, int], int] = {}
    national_aggregate: dict[int, int] = {}

    for row in parsed:
        try:
            numeric_age = int(row["age"])
        except ValueError:
            continue
        if numeric_age not in target_ages:
            continue
        if row["planning_area"] == "Total" and row["subzone"] == "Total" and row["sex"] == "Total":
            if row["count"] is not None:
                national_aggregate[numeric_age] = row["count"]
            continue
        if row["planning_area"] != "Total" and row["subzone"] == "Total" and row["sex"] == "Total":
            if row["count"] is not None:
                planning_aggregate[(row["planning_area"], numeric_age)] = row["count"]
            continue
        if row["planning_area"] == "Total" or row["subzone"] == "Total":
            continue
        sex_groups[(row["planning_area"], row["subzone"], numeric_age)][row["sex"]] = row["count"]
        if row["sex"] != "Total":
            continue
        record = {
            "source_id": "S001",
            "reference_period": "2025-06",
            "planning_area_name": row["planning_area"],
            "subzone_name": row["subzone"],
            "age": numeric_age,
            "sex": "Total",
            "resident_count_rounded": row["count"],
            "source_count_marker": row["marker"] or "numeric",
            "rounding_unit": rounding_unit,
        }
        target_rows.append(record)
        per_subzone[(row["planning_area"], row["subzone"])].append(record)

    sex_missing: list[dict[str, Any]] = []
    sex_discrepancies: list[dict[str, Any]] = []
    for (planning_area, subzone, age), values in sorted(sex_groups.items()):
        if set(values) != EXPECTED_SEXES or any(values.get(sex) is None for sex in EXPECTED_SEXES):
            sex_missing.append(
                {"planning_area_name": planning_area, "subzone_name": subzone, "age": age, "sexes": sorted(values)}
            )
            continue
        difference = int(values["Total"]) - int(values["Males"]) - int(values["Females"])
        if difference:
            sex_discrepancies.append(
                {
                    "planning_area_name": planning_area,
                    "subzone_name": subzone,
                    "age": age,
                    "total_minus_males_females": difference,
                }
            )

    proxy_rows: list[dict[str, Any]] = []
    incomplete_subzones: list[dict[str, Any]] = []
    for (planning_area, subzone), components in sorted(per_subzone.items()):
        ages = {record["age"] for record in components}
        null_ages = [record["age"] for record in components if record["resident_count_rounded"] is None]
        if ages != target_ages or null_ages:
            incomplete_subzones.append(
                {
                    "planning_area_name": planning_area,
                    "subzone_name": subzone,
                    "observed_ages": sorted(ages),
                    "null_ages": sorted(null_ages),
                }
            )
            continue
        proxy_rows.append(
            {
                "source_id": "S001",
                "reference_period": "2025-06",
                "planning_area_name": planning_area,
                "subzone_name": subzone,
                "target_age_min": target_age_min,
                "target_age_max": target_age_max,
                "accessible_target_population_proxy": sum(
                    int(record["resident_count_rounded"]) for record in components
                ),
                "component_age_count": len(components),
                "nil_or_negligible_component_count": sum(
                    record["source_count_marker"] == "nil_or_negligible" for record in components
                ),
                "rounding_unit": rounding_unit,
                "maximum_rounding_error_abs": len(components) * rounding_unit / 2,
            }
        )

    subzone_age_sums: dict[tuple[str, int], int] = defaultdict(int)
    for record in target_rows:
        if record["resident_count_rounded"] is not None:
            subzone_age_sums[(record["planning_area_name"], record["age"])] += int(
                record["resident_count_rounded"]
            )
    planning_reconciliation: list[dict[str, Any]] = []
    for key, aggregate_count in sorted(planning_aggregate.items()):
        detail_count = subzone_age_sums.get(key, 0)
        planning_reconciliation.append(
            {
                "planning_area_name": key[0],
                "age": key[1],
                "published_total": aggregate_count,
                "subzone_sum": detail_count,
                "difference": detail_count - aggregate_count,
            }
        )

    published_national = sum(national_aggregate.values())
    detail_national = sum(int(record["accessible_target_population_proxy"]) for record in proxy_rows)
    max_sex_difference = max(
        (abs(item["total_minus_males_females"]) for item in sex_discrepancies), default=0
    )
    quality = {
        "workbook_member": member,
        "worksheet_row_count_after_header": len(rows),
        "source_data_row_count": len(data_rows),
        "source_note_row_count": len(note_rows),
        "source_note_text": [row["Planning Area"] for row in note_rows],
        "source_composite_key_duplicate_count": len(duplicates),
        "source_composite_key_duplicate_examples": duplicates[:20],
        "observed_age_values": sorted(observed_ages, key=lambda value: (not value.isdigit(), int(value) if value.isdigit() else value)),
        "observed_sex_values": sorted(observed_sexes),
        "unexpected_age_values": sorted(observed_ages - {*(str(age) for age in range(90)), "90 & Over", "Total"}),
        "unexpected_sex_values": sorted(observed_sexes - EXPECTED_SEXES),
        "negative_count": negative_count,
        "missing_count_marker_count": marker_counts.get("missing", 0),
        "whole_workbook_nil_or_negligible_marker_count": marker_counts.get(
            "nil_or_negligible", 0
        ),
        "target_age_total_sex_nil_or_negligible_marker_count": sum(
            record["source_count_marker"] == "nil_or_negligible" for record in target_rows
        ),
        "unknown_count_markers": dict(unknown_markers),
        "target_age_row_count": len(target_rows),
        "target_subzone_count": len(proxy_rows),
        "incomplete_target_subzones": incomplete_subzones,
        "sex_set_or_count_missing_count": len(sex_missing),
        "sex_set_or_count_missing_examples": sex_missing[:20],
        "sex_rounding_discrepancy_count": len(sex_discrepancies),
        "sex_rounding_discrepancy_max_abs": max_sex_difference,
        "sex_rounding_discrepancy_examples": sex_discrepancies[:20],
        "planning_area_age_reconciliation": planning_reconciliation,
        "planning_area_age_reconciliation_max_abs": max(
            (abs(item["difference"]) for item in planning_reconciliation), default=0
        ),
        "national_target_age_published_total": published_national,
        "national_target_age_subzone_sum": detail_national,
        "national_target_age_difference": detail_national - published_national,
        "rounding_limitation": "Each published count is rounded to the nearest 10; sums preserve but compound that limitation.",
    }
    return {"target_age_rows": target_rows, "proxy_rows": proxy_rows, "quality": quality}
