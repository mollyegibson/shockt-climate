import io
from collections.abc import Sequence

import openpyxl
import psycopg
import pytest

from shockt.sources import open_ceda, reference
from shockt.sources.open_ceda import OPEN_CEDA_FACTORS, CedaSourceError, parse_workbook
from tests.conftest import MemoryArchive

UNIT = "kgCO2e/US Dollar"
NAMES = (None, None, None, "Oilseed farming", "Grain farming", None)
HEADER = ("Country Code", "Country", "country", "1111A0", 111200, None)
DATA = [
    ("AFG", "Afghanistan", UNIT, 0.89, 1.45, None),
    ("ZAF", "South Africa", UNIT, 0.5, 2, None),
    (None, None, None, None, None, None),
]  # fmt: skip


def ceda_workbook(
    data: Sequence[tuple[object, ...]] = DATA,
    header: tuple[object, ...] = HEADER,
    sheet_name: str = open_ceda.SHEET,
) -> bytes:
    wb = openpyxl.Workbook()
    wb.active.title = "Cover"
    sheet = wb.create_sheet(sheet_name)
    sheet.append(["Year", "2023"])
    sheet.append(["Price type", "Producer price", "Currency", "US Dollar"])
    sheet.append(NAMES)
    sheet.append(header)
    for row in data:
        sheet.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def test_parse_workbook_unpivots_the_country_by_industry_matrix() -> None:
    parsed = parse_workbook(ceda_workbook())

    assert parsed.rows_received == 4
    assert parsed.rows[0] == (
        "AFG",
        "Afghanistan",
        "1111A0",
        "Oilseed farming",
        UNIT,
        2023,
        "Producer price",
        0.89,
    )
    assert parsed.rows[3][2:4] == ("111200", "Grain farming")
    assert parsed.rows[3][-1] == 2.0
    assert len(OPEN_CEDA_FACTORS.columns) == len(parsed.rows[0]) + 1


def test_parse_workbook_rejects_a_missing_sheet() -> None:
    with pytest.raises(CedaSourceError, match="no 'GHG_t_Raw' sheet"):
        parse_workbook(ceda_workbook(sheet_name="GHG_t"))


def test_parse_workbook_rejects_a_text_factor() -> None:
    with pytest.raises(CedaSourceError, match="not a number"):
        parse_workbook(ceda_workbook([("AFG", "Afghanistan", UNIT, "n/a", 1.0, None)]))


def test_parse_workbook_rejects_a_repeated_country() -> None:
    with pytest.raises(CedaSourceError, match="AFG appears twice"):
        parse_workbook(ceda_workbook([*DATA, DATA[0]]))


def test_parse_workbook_rejects_a_repeated_sector_code() -> None:
    header = ("Country Code", "Country", "country", "1111A0", "1111A0", None)

    with pytest.raises(CedaSourceError, match="sector code 1111A0 appears twice"):
        parse_workbook(ceda_workbook(header=header))


def test_load_writes_every_factor_and_archives_the_workbook(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    body = ceda_workbook()

    result = reference.load(
        conn,
        memory_archive,
        OPEN_CEDA_FACTORS,
        open_ceda.FILENAME,
        open_ceda.XLSX,
        {"version": "test"},
        lambda: body,
        parse_workbook,
        None,
    )

    assert result.row_count == 4
    assert memory_archive.objects["raw/open_ceda_factors/latest/open_ceda.xlsx"] == body
    row = conn.execute(
        "SELECT sector_name, price_year, factor FROM raw.open_ceda_factors"
        " WHERE load_id = %s AND country_code = 'ZAF' AND sector_code = '111200'",
        (result.load_id,),
    ).fetchone()
    assert row == ("Grain farming", 2023, 2.0)
