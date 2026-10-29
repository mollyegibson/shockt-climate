import datetime
import io
from collections.abc import Sequence

import openpyxl
import psycopg
import pytest

from shockt.sources import reference, sbti
from shockt.sources.sbti import (
    COMPANIES,
    COMPANY_COLUMNS,
    TARGET_COLUMNS,
    TARGETS,
    SbtiSourceError,
    parse_companies,
    parse_targets,
)
from tests.conftest import MemoryArchive

STAMP = datetime.datetime(2026, 10, 29, 1, 0)
COMPANY_HEADER = [name for name, _ in COMPANY_COLUMNS]
TARGET_HEADER = [name for name, _ in TARGET_COLUMNS]


def workbook_bytes(header: Sequence[object | None], rows: Sequence[Sequence[object]]) -> bytes:
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.append([*header, None, None])
    for row in rows:
        sheet.append(list(row))
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def company(sbti_id: object = 40023788.0, **overrides: object) -> list[object]:
    values: dict[str, object] = dict.fromkeys(COMPANY_HEADER, "")
    values.update(
        sbti_id=sbti_id,
        company_name="Hytex",
        near_term_status="Validated Targets",
        near_term_target_year=2032.0,
        long_term_target_year="FY2050",
        date_updated=STAMP,
        **overrides,
    )
    return list(values.values())


def target(row_entry_id: str = "1-40023788", **overrides: object) -> list[object]:
    values: dict[str, object] = dict.fromkeys(TARGET_HEADER, "")
    values.update(
        row_entry_id=row_entry_id,
        sbti_id=40023788.0,
        company_name="Hytex",
        commitment_deadline=STAMP,
        scope=3.0,
        base_year="NA",
        date_published=STAMP,
        **overrides,
    )
    return list(values.values())


def test_parse_companies_keeps_source_labels_and_writes_empty_cells_as_null() -> None:
    parsed = parse_companies(workbook_bytes(COMPANY_HEADER, [company()]))

    row = dict(zip(COMPANY_HEADER, parsed.rows[0], strict=True))
    assert row["sbti_id"] == 40023788
    assert row["near_term_target_year"] == "2032"
    assert row["long_term_target_year"] == "FY2050"
    assert row["isin"] is None
    assert row["date_updated"] == STAMP
    assert len(COMPANIES.columns) == len(parsed.rows[0]) + 1


def test_parse_targets_writes_numbers_and_dates_in_text_columns_as_text() -> None:
    parsed = parse_targets(workbook_bytes(TARGET_HEADER, [target()]))

    row = dict(zip(TARGET_HEADER, parsed.rows[0], strict=True))
    assert row["scope"] == "3"
    assert row["base_year"] == "NA"
    assert row["commitment_deadline"] == "2026-10-29T01:00:00"
    assert row["date_published"] == STAMP
    assert len(TARGETS.columns) == len(parsed.rows[0]) + 1


def test_parse_targets_allows_a_company_on_several_rows() -> None:
    rows = [target("1-40023788"), target("2-40023788")]

    assert parse_targets(workbook_bytes(TARGET_HEADER, rows)).rows_received == 2


def test_parse_companies_rejects_a_repeated_company() -> None:
    with pytest.raises(SbtiSourceError, match="appears twice"):
        parse_companies(workbook_bytes(COMPANY_HEADER, [company(), company()]))


def test_parse_companies_rejects_a_changed_header() -> None:
    header = ["id", *COMPANY_HEADER[1:]]

    with pytest.raises(SbtiSourceError, match="not the expected columns"):
        parse_companies(workbook_bytes(header, [company()]))


def test_parse_companies_rejects_a_text_id() -> None:
    with pytest.raises(SbtiSourceError, match="sbti_id is not a whole number"):
        parse_companies(workbook_bytes(COMPANY_HEADER, [company(sbti_id="n/a")]))


def test_load_writes_both_workbooks_and_archives_them(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    companies = workbook_bytes(COMPANY_HEADER, [company()])
    targets = workbook_bytes(TARGET_HEADER, [target("1-40023788"), target("2-40023788")])

    for source, filename, body, parse in (
        (COMPANIES, sbti.COMPANIES_FILENAME, companies, parse_companies),
        (TARGETS, sbti.TARGETS_FILENAME, targets, parse_targets),
    ):
        result = reference.load(
            conn,
            memory_archive,
            source,
            filename,
            sbti.XLSX,
            {"url": filename},
            lambda body=body: body,
            parse,
            "Thu, 29 Oct 2026 13:36:22 GMT",
        )
        assert memory_archive.objects[f"raw/{source.dataset}/latest/{filename}"] == body
        assert result.row_count == (1 if source is COMPANIES else 2)

    row = conn.execute(
        "SELECT sbti_id, scope, commitment_deadline, date_published FROM raw.sbti_targets"
        " WHERE row_entry_id = '2-40023788'"
    ).fetchone()
    assert row == (40023788, "3", "2026-10-29T01:00:00", STAMP)
