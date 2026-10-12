import io
import zipfile

import httpx
import psycopg
import pytest
import respx

from shockt.config import CensusStatePortConfig, CountryFilter
from shockt.sources.census_state_port import (
    TARGET,
    StatePortError,
    archive_key,
    fetch_quarter,
    load_quarter,
    parse_zip,
)
from tests.conftest import FIXTURES, MemoryArchive

CONFIG = CensusStatePortConfig(
    url_template="https://example.invalid/ISTPORT{yy}Q{quarter}.ZIP",
    origins_only=True,
    states=["VA", "GA", "OH", "CA", "OR", "WA", "AZ", "TX", "IL"],
    drop_rows_without_air_or_vessel_weight=True,
)
ORIGINS = CountryFilter(code_prefixes=["5"], codes=["2010"])
EXTRACT = (FIXTURES / "census_state_port_2024Q1_extract.dat").read_text(encoding="latin-1")


def zip_of(text: str, name: str = "IQ953_2024_Q1.dat") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(name, text.encode("latin-1"))
    return buffer.getvalue()


def test_parse_zip_reads_fields_by_position() -> None:
    parsed = parse_zip(zip_of(EXTRACT), 2024, 1, CONFIG, ORIGINS)

    assert parsed.rows[0] == (
        2024, "1", "VA", "04", "01", "04", "01", "5330",
        19122, 0, 0, 19122, 19122, 20715, 20715,
    )  # fmt: skip
    assert len(TARGET.columns) == len(parsed.rows[0]) + 1


def test_parse_zip_keeps_configured_states_origins_and_rows_with_weight() -> None:
    parsed = parse_zip(zip_of(EXTRACT), 2024, 1, CONFIG, ORIGINS)

    assert parsed.rows_received == 21
    assert len(parsed.rows) == 12
    assert {row[2] for row in parsed.rows} == {"VA", "CA", "TX", "GA"}
    assert all(row[7].startswith("5") or row[7] == "2010" for row in parsed.rows)
    assert all(row[10] > 0 or row[13] > 0 for row in parsed.rows)


def test_parse_zip_without_a_country_filter_keeps_every_origin() -> None:
    parsed = parse_zip(zip_of(EXTRACT), 2024, 1, CONFIG, None)

    assert "1220" in {row[7] for row in parsed.rows}


def test_parse_zip_reads_the_2026_file_name() -> None:
    parsed = parse_zip(zip_of(EXTRACT, "ISTPORT24Q1.TXT"), 2024, 1, CONFIG, ORIGINS)

    assert len(parsed.rows) == 12


def test_parse_zip_rejects_a_file_for_another_quarter() -> None:
    with pytest.raises(StatePortError, match="not 2024 Q2"):
        parse_zip(zip_of(EXTRACT), 2024, 2, CONFIG, ORIGINS)


def test_parse_zip_rejects_a_line_of_the_wrong_length() -> None:
    with pytest.raises(StatePortError, match="characters"):
        parse_zip(zip_of(EXTRACT + "VA 0401\n"), 2024, 1, CONFIG, ORIGINS)


def test_parse_zip_rejects_a_zip_with_more_than_one_file() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("a.dat", EXTRACT)
        zf.writestr("b.dat", EXTRACT)

    with pytest.raises(StatePortError, match="one data file"):
        parse_zip(buffer.getvalue(), 2024, 1, CONFIG, ORIGINS)


@respx.mock
def test_fetch_quarter_returns_none_when_the_quarter_is_not_published() -> None:
    respx.head("https://example.invalid/ISTPORT26Q3.ZIP").mock(return_value=httpx.Response(404))

    with httpx.Client() as client:
        assert fetch_quarter(client, CONFIG, 2026, 3) is None


@respx.mock
def test_fetch_quarter_returns_the_zip_and_its_last_modified_header() -> None:
    source = "https://example.invalid/ISTPORT24Q1.ZIP"
    modified = "Tue, 06 Oct 2026 12:42:23 GMT"
    respx.head(source).mock(return_value=httpx.Response(200, headers={"last-modified": modified}))
    respx.get(source).mock(return_value=httpx.Response(200, content=b"zip bytes"))

    with httpx.Client() as client:
        assert fetch_quarter(client, CONFIG, 2024, 1) == (b"zip bytes", modified)


def test_load_quarter_archives_the_zip_and_records_the_filters_and_version(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    body = zip_of(EXTRACT)

    result = load_quarter(
        conn, memory_archive, CONFIG, ORIGINS, 2024, 1, lambda: body, "Tue, 06 Oct 2026"
    )

    assert memory_archive.objects[archive_key(2024, 1)] == body
    assert result.row_count == 12
    manifest = conn.execute(
        "SELECT partition_key, source_version, params FROM raw.load_manifest WHERE load_id = %s",
        (result.load_id,),
    ).fetchone()
    assert manifest is not None
    partition, version, params = manifest
    assert (partition, version) == ("2024Q1", "Tue, 06 Oct 2026")
    assert params["rows_received"] == 21
    assert params["filters"]["states"] == CONFIG.states
    assert params["filters"]["countries"]["codes"] == ["2010"]
    assert conn.execute("SELECT count(*) FROM raw.census_state_port").fetchone() == (12,)
