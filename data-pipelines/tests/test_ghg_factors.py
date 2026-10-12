import io
from collections.abc import Callable

import openpyxl
import psycopg
import pytest

from shockt.sources import reference
from shockt.sources.ghg_factors import (
    EPA_GWP,
    EPA_TRANSPORT,
    UK_FACTORS,
    FactorSourceError,
    parse_epa_gwp,
    parse_epa_transport,
    parse_uk_workbook,
)
from tests.conftest import MemoryArchive

UK_HEADER = (
    "ID",
    "Scope",
    "Level 1",
    "Level 2",
    "Level 3",
    "Level 4",
    "Column Text",
    "UOM",
    "GHG/Unit",
    "GHG Conversion Factor 2026",
)
UK_ROWS = [
    ("t1", "Scope 3", "Freighting goods", "Cargo ship", "Container ship", "Average", None,
     "tonne.km", "kg CO2e", 0.0161),
    ("w1", "Scope 3", "WTT- delivery vehs & freight", "WTT- cargo ship", "Container ship",
     "Average", None, "tonne.km", "kg CO2e", 0.0037),
    ("f1", "Scope 1", "Fuels", "Liquid fuels", "Diesel (100% mineral diesel)", None, None,
     "litres", "kg CO2e", 2.66),
    ("b1", "Scope 1", "Fuels", "Liquid fuels", "Blank cell", None, None, "litres", "kg CO2e",
     None),
]  # fmt: skip


def workbook_bytes(build: Callable[[openpyxl.Workbook], None]) -> bytes:
    wb = openpyxl.Workbook()
    build(wb)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def uk_workbook(rows: list[tuple[object, ...]] = UK_ROWS) -> bytes:
    def build(wb: openpyxl.Workbook) -> None:
        wb.active.title = "Front page"
        sheet = wb.create_sheet("Factors by Category")
        sheet.append(["UK Government GHG Conversion Factors for Company Reporting"])
        sheet.append([])
        sheet.append(UK_HEADER)
        for row in rows:
            sheet.append(row)

    return workbook_bytes(build)


def epa_workbook(table_8_extra: list[object] | None = None) -> bytes:
    def build(wb: openpyxl.Workbook) -> None:
        sheet = wb.active
        sheet.title = "Emission Factors Hub"
        sheet.append(["Table 8", "Scope 3 Category 4 and Category 9"])
        sheet.append(["These factors are intended for the distance-based method."])
        sheet.append(["Vehicle Type", "CO2 Factor", "CH4 Factor", "N2O Factor", "Units"])
        sheet.append(["Medium- and Heavy-Duty Truck", 1.298, 0.0115, 0.0376, "vehicle-mile"])
        sheet.append(["Medium- and Heavy-Duty TruckC", 0.186, 0.0016, 0.0054, "short ton-mile"])
        sheet.append(["Rail", 0.021, 0.0016, 0.0005, "short ton-mile"])
        if table_8_extra:
            sheet.append(table_8_extra)
        sheet.append(["Source: \nEPA Inventory of U.S. Greenhouse Gas Emissions and Sinks."])
        sheet.append(["Table 9", "Waste"])
        sheet.append(["Table 11", "Global Warming Potential (GWP)"])
        sheet.append([])
        sheet.append(["Industrial Designation or \nCommon Name\xa0", "Chemical Formula", "GWP"])
        sheet.append(["Carbon dioxide", "CO2", 1])
        sheet.append(["Methane", "CH4", 28])
        sheet.append(["Nitrous oxide", "N2O", 265])
        sheet.append(["Source: \n100-year GWP values from IPCC AR5."])
        sheet.append(["Table 12", "Blended refrigerants"])

    return workbook_bytes(build)


def test_parse_uk_workbook_keeps_every_row_with_source_labels() -> None:
    parsed = parse_uk_workbook(uk_workbook())

    assert [row[0] for row in parsed.rows] == ["t1", "w1", "f1", "b1"]
    assert parsed.rows[1] == (
        "w1",
        "Scope 3",
        "WTT- delivery vehs & freight",
        "WTT- cargo ship",
        "Container ship",
        "Average",
        None,
        "tonne.km",
        "kg CO2e",
        0.0037,
    )
    assert parsed.rows[3][-1] is None
    assert len(UK_FACTORS.columns) == len(parsed.rows[0]) + 1


def test_parse_uk_workbook_rejects_a_repeated_id() -> None:
    with pytest.raises(FactorSourceError, match="t1 appears twice"):
        parse_uk_workbook(uk_workbook([*UK_ROWS, UK_ROWS[0]]))


def test_parse_uk_workbook_rejects_a_text_factor() -> None:
    bad = (*UK_ROWS[0][:-1], "n/a")

    with pytest.raises(FactorSourceError, match="not a number"):
        parse_uk_workbook(uk_workbook([bad]))


def test_parse_epa_transport_reads_table_8_up_to_its_source_note() -> None:
    parsed = parse_epa_transport(epa_workbook())

    assert parsed.rows == [
        ("Medium- and Heavy-Duty Truck", 1.298, 0.0115, 0.0376, "vehicle-mile"),
        ("Medium- and Heavy-Duty TruckC", 0.186, 0.0016, 0.0054, "short ton-mile"),
        ("Rail", 0.021, 0.0016, 0.0005, "short ton-mile"),
    ]
    assert len(EPA_TRANSPORT.columns) == len(parsed.rows[0]) + 1


def test_parse_epa_transport_rejects_a_row_it_cant_read() -> None:
    with pytest.raises(FactorSourceError, match="unexpected shape"):
        parse_epa_transport(epa_workbook(["Barge", "n/a", 0.1, 0.1, "short ton-mile"]))


def test_parse_epa_gwp_reads_table_11() -> None:
    parsed = parse_epa_gwp(epa_workbook())

    assert parsed.rows == [
        ("Carbon dioxide", "CO2", 1.0),
        ("Methane", "CH4", 28.0),
        ("Nitrous oxide", "N2O", 265.0),
    ]
    assert len(EPA_GWP.columns) == len(parsed.rows[0]) + 1


def test_load_writes_every_uk_row_and_archives_the_workbook(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    body = uk_workbook()

    result = reference.load(
        conn,
        memory_archive,
        UK_FACTORS,
        "uk.xlsx",
        "application/octet-stream",
        {"version": "2026"},
        lambda: body,
        parse_uk_workbook,
        "Mon, 27 Jul 2026 00:00:00 GMT",
    )

    assert result.row_count == 4
    assert memory_archive.objects["raw/uk_ghg_conversion_factors/latest/uk.xlsx"] == body
    blank = conn.execute(
        "SELECT factor FROM raw.uk_ghg_conversion_factors WHERE load_id = %s AND id = 'b1'",
        (result.load_id,),
    ).fetchone()
    assert blank == (None,)
