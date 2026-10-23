import io
from collections.abc import Callable
from datetime import date

import openpyxl
import psycopg
import pytest

from shockt.sources.thetis_mrv import (
    HEADER_ROW,
    TARGET,
    MrvSourceError,
    _safe_float,
    load_year,
    parse_xlsx,
)
from tests.conftest import MemoryArchive

REQUIRED_HEADERS = [
    "IMO Number",
    "Name",
    "Ship type",
    "Port of Registry",
    "Home Port",
    "Ice Class",
    "DoC issue date",
    "DoC expiry date",
    "Reporting Period",
    "Total fuel consumption [m tonnes]",
    "Total CO₂ emissions [m tonnes]",
    "Time spent at sea [hours]",
]

OPTIONAL_HEADERS_2024 = [
    "Total CO₂eq emissions [m tonnes]",
    "Annual average Fuel consumption per distance [kg / n mile]",
    "Annual average CO₂ emissions per distance [kg CO₂ / n mile]",
    "Annual average CO₂ emissions per transport work (mass) [g CO₂ / m tonnes · n miles]",
]


def workbook_bytes(build: Callable[[openpyxl.Workbook], None]) -> bytes:
    wb = openpyxl.Workbook()
    build(wb)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def simple_mrv_workbook(
    year: int = 2023,
    rows: list[list[object]] | None = None,
    include_optional: bool = False,
    two_sheets: bool = False,
) -> bytes:
    headers = REQUIRED_HEADERS + (OPTIONAL_HEADERS_2024 if include_optional else [])
    if rows is None:
        row_data: list[object] = [
            9074729,
            "EVER GIVEN",
            "Container ship",
            "PA",
            "Panama",
            "N/A",
            date(2023, 1, 15),
            date(2023, 12, 31),
            year,
            45000.0,
            140000.0,
            7500.0,
        ]
        if include_optional:
            row_data.extend([142000.0, 85.5, 26.7, 12.3])
        rows = [row_data]

    def build(wb: openpyxl.Workbook) -> None:
        ws = wb.active
        ws.title = "Full ERs" if two_sheets else "Sheet1"
        for _ in range(HEADER_ROW - 1):
            ws.append([])
        ws.append(headers)
        for row in rows:
            ws.append(row)
        if two_sheets:
            ws2 = wb.create_sheet("Partial ERs")
            for _ in range(HEADER_ROW - 1):
                ws2.append([])
            ws2.append(headers)
            partial_row: list[object] = [
                9999999,
                "PARTIAL SHIP",
                "Container ship",
                "MT",
                "Valletta",
                "N/A",
                date(2024, 3, 1),
                date(2024, 6, 30),
                year,
                1000.0,
                3100.0,
                500.0,
            ]
            if include_optional:
                partial_row.extend([3200.0, 10.0, 3.1, 1.0])
            ws2.append(partial_row)

    return workbook_bytes(build)


def test_parse_xlsx_single_sheet() -> None:
    body = simple_mrv_workbook(year=2023)
    parsed = parse_xlsx(body, 2023)

    assert parsed.rows_received == 1
    assert len(parsed.rows) == 1
    row = parsed.rows[0]
    assert row[0] == 2023
    assert row[1] == "full"
    assert row[2] == "9074729"
    assert row[3] == "EVER GIVEN"
    assert row[4] == "Container ship"
    assert row[10] == 45000.0
    assert row[11] == 140000.0
    assert row[12] is None  # co2eq not in 2023 format


def test_parse_xlsx_two_sheets_2024() -> None:
    body = simple_mrv_workbook(year=2024, include_optional=True, two_sheets=True)
    parsed = parse_xlsx(body, 2024)

    assert parsed.rows_received == 2
    full_rows = [r for r in parsed.rows if r[1] == "full"]
    partial_rows = [r for r in parsed.rows if r[1] == "partial"]
    assert len(full_rows) == 1
    assert len(partial_rows) == 1
    assert full_rows[0][12] == 142000.0  # co2eq present
    assert partial_rows[0][2] == "9999999"


def test_safe_float_handles_division_by_zero() -> None:
    assert _safe_float("Division by zero!") is None
    assert _safe_float("N/A") is None
    assert _safe_float(None) is None
    assert _safe_float(42.5) == 42.5
    assert _safe_float("  3.14  ") == 3.14


def test_parse_xlsx_skips_rows_without_imo() -> None:
    rows = [
        [None, "Ghost", "Container ship", "PA", "", "", None, None, 2023, 0, 0, 0],
        [9074729, "Real", "Container ship", "PA", "", "", None, None, 2023, 100, 300, 50],
    ]
    body = simple_mrv_workbook(year=2023, rows=rows)
    parsed = parse_xlsx(body, 2023)

    assert parsed.rows_received == 1


def test_parse_xlsx_rejects_missing_columns() -> None:
    def build(wb: openpyxl.Workbook) -> None:
        ws = wb.active
        for _ in range(HEADER_ROW - 1):
            ws.append([])
        ws.append(["IMO Number", "Name"])
        ws.append([123, "Ship"])

    body = workbook_bytes(build)
    with pytest.raises(MrvSourceError, match="missing required columns"):
        parse_xlsx(body, 2023)


def test_target_columns_match_raw_table() -> None:
    assert TARGET.columns[0] == "load_id"
    assert TARGET.table == "thetis_mrv"


def test_load_year_writes_rows_and_archives(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    body = simple_mrv_workbook(year=2023)
    from shockt.config import ThetisMrvConfig

    config = ThetisMrvConfig(
        downloadable_files_url="https://test.example.com/files",
        download_url_template="https://test.example.com/{year}/{version}",
        start_year=2022,
    )
    result = load_year(conn, memory_archive, config, 2023, 1, lambda: body)

    assert result.row_count == 1
    rows = conn.execute(
        "SELECT imo_number, ship_name, total_co2_mt FROM raw.thetis_mrv WHERE load_id = %s",
        (result.load_id,),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0] == ("9074729", "EVER GIVEN", 140000.0)
