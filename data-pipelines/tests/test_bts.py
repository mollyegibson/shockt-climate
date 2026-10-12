import io
import zipfile
from pathlib import Path

import psycopg
import pytest

from shockt.config import BtsTransborderConfig, CountryFilter
from shockt.sources.bts_transborder import (
    TARGET,
    BtsFileError,
    archive_key,
    load_month,
    monthly_members,
    parse_zip,
    read_month_file,
    scan_dir,
)
from tests.conftest import FIXTURES, MemoryArchive

MEXICO = CountryFilter(codes=["2010"])
CHAPTERS = ["84", "85"]

CONFIG = BtsTransborderConfig(
    manual_dir="unused",
    tables=["dot2", "dot3"],
)
FIXTURE_DIR = FIXTURES / "bts"


def make_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in files.items():
            zf.writestr(zipfile.ZipInfo(name, date_time=(2024, 3, 15, 0, 0, 0)), text)
    return buffer.getvalue()


def month_zip(**extra: str) -> bytes:
    """January 2024's dot2 and dot3 fixtures in BTS's folder layout, plus any extra members."""
    files = {
        f"Jan2024/{table}_0124.csv": (FIXTURE_DIR / f"{table}_0124.csv").read_text()
        for table in ("dot2", "dot3")
    }
    files["Jan2024/dot1_0124.csv"] = "TRDTYPE\n1\n"
    return make_zip({**files, **extra})


def columns() -> tuple[str, ...]:
    return tuple(TARGET.columns[1:])


def test_monthly_members_ignores_year_to_date_annual_and_other_files() -> None:
    members = monthly_members(
        [
            "December2022/dot2_1222.csv",
            "December2022/dot2_ytd_1222.csv",
            "December2022/dot2_2022.csv",
            "December2022/dot3_1222.csv",
            "Press Release Excel sheets.twbx",
        ]
    )

    assert members == {
        "dot2": ("2022-12", "December2022/dot2_1222.csv"),
        "dot3": ("2022-12", "December2022/dot3_1222.csv"),
    }


def test_parse_zip_keeps_mexico_imports_in_the_configured_chapters() -> None:
    parsed = parse_zip(month_zip(), CONFIG, MEXICO, CHAPTERS)

    rows = [dict(zip(columns(), row, strict=True)) for row in parsed.rows]
    assert parsed.rows_received == 18
    assert len(rows) == 12
    assert {r["source_table"] for r in rows} == {"dot2", "dot3"}
    assert all(r["trdtype"] == 2 and r["country"] == "2010" for r in rows)
    assert {r["commodity2"] for r in rows} == {"84", "85"}
    assert parsed.source_version == "released 2024-03-15"


def test_parse_zip_types_values_and_maps_blank_cells_to_null() -> None:
    rail = next(
        dict(zip(columns(), row, strict=True))
        for row in parse_zip(month_zip(), CONFIG, MEXICO, CHAPTERS).rows
        if row[0] == "dot2" and row[7] == 6 and row[6] == "84"
    )

    assert rail == {
        "source_table": "dot2",
        "year": 2024,
        "month": 1,
        "trdtype": 2,
        "usastate": "AR",
        "depe": None,
        "commodity2": "84",
        "disagmot": 6,
        "mexstate": None,
        "country": "2010",
        "value": 335_699,
        "shipwt": 7_730,
        "freight_charges": 2_000,
        "df": None,
        "contcode": "1",
    }


def test_parse_zip_rejects_rows_for_another_month() -> None:
    dot2 = (FIXTURE_DIR / "dot2_0124.csv").read_text().replace(",01,2024", ",02,2024", 1)
    body = make_zip(
        {"dot2_0124.csv": dot2, "dot3_0124.csv": (FIXTURE_DIR / "dot3_0124.csv").read_text()}
    )

    with pytest.raises(BtsFileError, match="not for 2024-01"):
        parse_zip(body, CONFIG, MEXICO, CHAPTERS)


def test_parse_zip_rejects_a_missing_column() -> None:
    dot3 = (FIXTURE_DIR / "dot3_0124.csv").read_text().replace("SHIPWT", "WEIGHT", 1)
    body = make_zip(
        {"dot2_0124.csv": (FIXTURE_DIR / "dot2_0124.csv").read_text(), "dot3_0124.csv": dot3}
    )

    with pytest.raises(BtsFileError, match="SHIPWT"):
        parse_zip(body, CONFIG, MEXICO, CHAPTERS)


def test_read_month_file_reports_a_truncated_download(tmp_path: Path) -> None:
    path = tmp_path / "Jan2024.zip"
    body = month_zip()
    path.write_bytes(body[: len(body) // 2])

    with pytest.raises(BtsFileError, match="download it again"):
        read_month_file(path, CONFIG.tables)


def test_scan_dir_ignores_identical_copies_and_flags_conflicting_ones(tmp_path: Path) -> None:
    (tmp_path / "Jan2024.zip").write_bytes(month_zip())
    (tmp_path / "Jan2024 copy.zip").write_bytes(month_zip())
    (tmp_path / "January2024.zip").write_bytes(month_zip(**{"Jan2024/readme.txt": "x"}))
    (tmp_path / "broken.zip").write_bytes(b"PK\x03\x04 not really a zip")

    months, errors = scan_dir(tmp_path, CONFIG.tables)

    assert list(months) == ["2024-01"]
    assert len(errors) == 2
    assert any("broken.zip" in e for e in errors)
    assert any("January2024.zip" in e and "different contents" in e for e in errors)


def test_load_month_archives_the_zip_and_records_the_filter(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    body = month_zip()

    result = load_month(
        conn, memory_archive, "2024-01", lambda: body, CONFIG, MEXICO, CHAPTERS, "Jan2024.zip"
    )

    assert memory_archive.objects[archive_key("2024-01")] == body
    assert result.row_count == 12
    params = conn.execute(
        "SELECT params FROM raw.load_manifest WHERE load_id = %s", (result.load_id,)
    ).fetchone()
    assert params is not None
    assert params[0]["original_filename"] == "Jan2024.zip"
    assert params[0]["rows_received"] == 18
    assert params[0]["filters"]["hs2_chapters"] == ["84", "85"]
    assert params[0]["filters"]["countries"]["codes"] == ["2010"]
    count = conn.execute("SELECT count(*) FROM raw.bts_transborder").fetchone()
    assert count == (12,)


def test_load_month_from_the_archive_replaces_the_earlier_load(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    first = load_month(
        conn, memory_archive, "2024-01", month_zip, CONFIG, MEXICO, CHAPTERS, "Jan2024.zip"
    )

    second = load_month(conn, memory_archive, "2024-01", None, CONFIG, MEXICO, CHAPTERS)

    assert second.superseded_load_id == first.load_id
    assert conn.execute("SELECT count(*) FROM raw.bts_transborder").fetchone() == (12,)
