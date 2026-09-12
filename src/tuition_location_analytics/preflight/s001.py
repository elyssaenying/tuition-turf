from __future__ import annotations

import csv
import io
import json
import os
import re
import struct
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

from .common import sha256_file, utc_now, write_json

SOURCE_ID = "S001"
REQUESTED_URL = "https://www.singstat.gov.sg/files/971801ef-637f-4f75-9205-d3d481a3e5cc.zip"
LANDING_URL = "https://www.singstat.gov.sg/publication-resources/population-trends-2025"
TERMS_URL = "https://www.singstat.gov.sg/terms-of-use"
SNAPSHOT_DIR = Path("data/raw/s001_population_trends_2025/2026-09-12")
ARCHIVE_NAME = "population-trends-2025-geospatial.zip"
MAX_SCHEMA_BYTES = 256 * 1024


def _safe_response_headers(response: Any) -> dict[str, str]:
    allowed = {
        "content-type",
        "content-length",
        "content-disposition",
        "last-modified",
        "etag",
        "date",
    }
    return {
        key.lower(): value
        for key, value in response.headers.items()
        if key.lower() in allowed
    }


def download_snapshot(repo_root: Path) -> dict[str, Any]:
    destination_dir = repo_root / SNAPSHOT_DIR
    archive_path = destination_dir / ARCHIVE_NAME
    metadata_path = destination_dir / "snapshot-metadata.json"
    destination_dir.mkdir(parents=True, exist_ok=True)

    if archive_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
        return {
            "status": "reused_immutable_snapshot",
            "archive_path": archive_path,
            "metadata_path": metadata_path,
            "sha256": sha256_file(archive_path),
            "byte_size": archive_path.stat().st_size,
            "retrieved_at": metadata.get("retrieved_at"),
            "final_url": metadata.get("final_url", REQUESTED_URL),
            "http_status": metadata.get("http_status"),
            "http_response_metadata": metadata.get("http_response_metadata", {}),
        }

    temporary = archive_path.with_suffix(".zip.part")
    request = urllib.request.Request(
        REQUESTED_URL,
        headers={"User-Agent": "tuition-location-analytics-preflight/0.1"},
    )
    retrieved_at = utc_now()
    try:
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("xb") as output:
            response_headers = _safe_response_headers(response)
            final_url = response.geturl()
            status_code = response.status
            while block := response.read(1024 * 1024):
                output.write(block)
        os.replace(temporary, archive_path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    metadata = {
        "source_id": SOURCE_ID,
        "requested_url": REQUESTED_URL,
        "final_url": final_url,
        "retrieved_at": retrieved_at,
        "http_status": status_code,
        "http_response_metadata": response_headers,
        "byte_size": archive_path.stat().st_size,
        "checksum_algorithm": "sha256",
        "checksum": sha256_file(archive_path),
        "storage_ref": archive_path.relative_to(repo_root).as_posix(),
        "immutable": True,
    }
    write_json(metadata_path, metadata)
    return {
        "status": "downloaded",
        "archive_path": archive_path,
        "metadata_path": metadata_path,
        "sha256": metadata["checksum"],
        "byte_size": metadata["byte_size"],
        "retrieved_at": metadata["retrieved_at"],
        "final_url": metadata["final_url"],
        "http_status": metadata["http_status"],
        "http_response_metadata": metadata["http_response_metadata"],
    }


def _is_t3(name: str) -> bool:
    lowered = Path(name).name.lower()
    return bool(re.search(r"(?:^|[^a-z0-9])t0?3(?:[^a-z0-9]|$)", lowered)) or (
        "single year of age and sex" in lowered
    )


def _dbf_schema(raw: bytes) -> dict[str, Any]:
    if len(raw) < 32:
        return {"format": "dbf", "error": "header_too_short"}
    record_count = struct.unpack("<I", raw[4:8])[0]
    header_length = struct.unpack("<H", raw[8:10])[0]
    record_length = struct.unpack("<H", raw[10:12])[0]
    fields: list[dict[str, Any]] = []
    cursor = 32
    while cursor + 32 <= min(len(raw), header_length) and raw[cursor] != 0x0D:
        descriptor = raw[cursor : cursor + 32]
        name = descriptor[:11].split(b"\x00", 1)[0].decode("ascii", errors="replace")
        fields.append(
            {
                "name": name,
                "type": chr(descriptor[11]),
                "length": descriptor[16],
                "decimal_count": descriptor[17],
            }
        )
        cursor += 32
    return {
        "format": "dbf",
        "declared_record_count": record_count,
        "header_length": header_length,
        "record_length": record_length,
        "fields": fields,
    }


def _delimited_schema(raw: bytes, suffix: str) -> dict[str, Any]:
    text = raw.decode("utf-8-sig", errors="replace")
    sample = text[:8192]
    default = "\t" if suffix in {".tsv", ".txt"} else ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = default
    rows = csv.reader(io.StringIO(text), delimiter=delimiter)
    header = next(rows, [])
    examples = []
    for _, row in zip(range(3), rows):
        examples.append({header[index]: value for index, value in enumerate(row[: len(header)])})
    return {
        "format": "delimited_text",
        "delimiter": "tab" if delimiter == "\t" else delimiter,
        "fields": header,
        "sample_record_count": len(examples),
        "sample_records": examples,
        "inspection_byte_limit": MAX_SCHEMA_BYTES,
    }


def _xlsx_schema(raw: bytes) -> dict[str, Any]:
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(raw)) as workbook:
        shared_strings: list[str] = []
        shared_root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
        for item in shared_root.findall(namespace + "si"):
            shared_strings.append("".join(node.text or "" for node in item.iter(namespace + "t")))

        sheet_name = sorted(
            name for name in workbook.namelist() if name.startswith("xl/worksheets/sheet")
        )[0]
        selected_rows: list[dict[str, str]] = []
        dimension = None
        with workbook.open(sheet_name) as sheet:
            for event, element in ET.iterparse(sheet, events=("start", "end")):
                if event == "start" and element.tag == namespace + "dimension":
                    dimension = element.attrib.get("ref")
                if event != "end" or element.tag != namespace + "row":
                    continue
                row_number = int(element.attrib.get("r", "0"))
                if row_number in {1, 3, 4, 5, 6, 7, 8, 9}:
                    row: dict[str, str] = {}
                    for cell in element.findall(namespace + "c"):
                        reference = cell.attrib.get("r", "")
                        column = re.match(r"[A-Z]+", reference)
                        value_node = cell.find(namespace + "v")
                        if column is None or value_node is None or value_node.text is None:
                            continue
                        value = value_node.text
                        if cell.attrib.get("t") == "s":
                            value = shared_strings[int(value)]
                        row[column.group(0)] = value
                    selected_rows.append({"row": str(row_number), **row})
                if row_number > 9:
                    break

    header_row = next(row for row in selected_rows if row["row"] == "3")
    notes = [value for value in shared_strings if value.startswith("Planning areas refer") or value.startswith('"-"') or value.startswith("Data has been rounded")]
    return {
        "format": "xlsx",
        "worksheet": sheet_name,
        "declared_dimension": dimension,
        "fields": [header_row.get(column) for column in ("A", "B", "C", "D", "E")],
        "selected_header_and_schema_rows": selected_rows,
        "row_grain": "planning-area name × subzone name × single-year age/category × sex",
        "candidate_key": ["Planning Area", "Subzone", "Age", "Sex"],
        "stable_geography_identifiers_present": False,
        "mp2019_compatibility": any("Master Plan 2019" in value for value in shared_strings),
        "age_representation": "single-year strings 0 through 89, plus 90 & Over and Total",
        "sex_representation": ["Total", "Males", "Females"],
        "resident_count_representation": "numeric 2025 column, rounded to nearest 10",
        "suppression_or_missing_markers": {"-": "nil or negligible; not a missing-value marker"},
        "duplicate_key_risk": "Not tested without full ingestion. Aggregate Total rows and name-only geographies require explicit composite-key validation.",
        "workbook_notes": notes,
        "complete_dataset_loaded": False,
    }


def inspect_archive(archive_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(archive_path) as archive:
        members = [
            {
                "name": item.filename,
                "uncompressed_bytes": item.file_size,
                "compressed_bytes": item.compress_size,
            }
            for item in archive.infolist()
            if not item.is_dir()
        ]
        candidates = [item["name"] for item in members if _is_t3(item["name"])]
        schemas: list[dict[str, Any]] = []
        for name in candidates:
            suffix = Path(name).suffix.lower()
            if suffix not in {".csv", ".tsv", ".txt", ".dbf", ".prj", ".cpg", ".xlsx"}:
                continue
            with archive.open(name) as member:
                raw = member.read() if suffix == ".xlsx" else member.read(MAX_SCHEMA_BYTES)
            if suffix == ".xlsx":
                schema = _xlsx_schema(raw)
            elif suffix == ".dbf":
                schema = _dbf_schema(raw)
            elif suffix in {".csv", ".tsv", ".txt"}:
                schema = _delimited_schema(raw, suffix)
            else:
                schema = {
                    "format": suffix.removeprefix("."),
                    "text": raw.decode("utf-8", errors="replace").strip(),
                }
            schemas.append({"member": name, "schema": schema})
    return {
        "archive_members": members,
        "t3_candidates": candidates,
        "t3_schema_inspection": schemas,
        "complete_dataset_loaded": False,
    }


def run(repo_root: Path) -> dict[str, Any]:
    downloaded = download_snapshot(repo_root)
    inspection = inspect_archive(downloaded["archive_path"])
    result = {
        "source_id": SOURCE_ID,
        "status": "completed_with_limitations" if inspection["t3_schema_inspection"] else "blocked_schema_unreadable",
        "requested_url": REQUESTED_URL,
        "final_url": downloaded["final_url"],
        "retrieved_at": downloaded["retrieved_at"],
        "http_status": downloaded["http_status"],
        "http_response_metadata": downloaded["http_response_metadata"],
        "landing_url": LANDING_URL,
        "terms_url": TERMS_URL,
        "storage_ref": downloaded["archive_path"].relative_to(repo_root).as_posix(),
        "metadata_ref": downloaded["metadata_path"].relative_to(repo_root).as_posix(),
        "byte_size": downloaded["byte_size"],
        "sha256": downloaded["sha256"],
        "inspection": inspection,
        "licence_assessment": {
            "status": "unestablished_for_raw_redistribution",
            "observed": "The publication identifies the Singapore Department of Statistics as source and links website terms of use.",
            "limitation": "No resource-specific raw-archive redistribution permission was established in this preflight; retain the raw ZIP outside public outputs.",
            "attribution": "Singapore Department of Statistics, Population Trends 2025, Table T3.",
        },
    }
    return result
