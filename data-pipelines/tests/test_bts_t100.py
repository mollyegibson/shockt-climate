import io
import zipfile
from urllib.parse import parse_qs

import httpx
import psycopg
import pytest
import respx

from shockt.config import BtsT100Config
from shockt.months import MonthRange
from shockt.sources.bts_t100 import (
    DATA_FILE,
    DOCUMENTATION_FILE,
    FIELDS,
    TARGET,
    T100Error,
    archive_key,
    fetch_year,
    load_year,
    parse_zip,
    read_form,
)
from tests.conftest import FIXTURES, MemoryArchive

FORM_URL = "https://example.invalid/DL_SelectFields.aspx?gnoyr_VQ=FJE"
CONFIG = BtsT100Config(form_url=FORM_URL, origins_only=True, drop_rows_without_freight=True)
ORIGINS = ["CN", "JP", "KR", "MX", "TW"]
YEAR_2024 = MonthRange("2024-01", "2024-12")
EXTRACT = (FIXTURES / "bts_t100_2024_extract.csv").read_bytes().decode()
FORM_PAGE = """
<html><body>
<form method="get" action="https://search.usa.gov/search" id="usasearch-search-block-form">
  <input type="hidden" name="affiliate" value="bts" />
</form>
<form method="post" action="./DL_SelectFields.aspx?gnoyr_VQ=FJE" id="form1">
  <input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="state" />
  <input type="hidden" name="__EVENTVALIDATION" id="__EVENTVALIDATION" value="validation" />
  <FORM name='searchForm' METHOD=POST ACTION='Search.asp'>
    <input type="hidden" name="searchHidden" value="not the download form's" />
  </FORM>
  <select name="cboYear" id="cboYear">
    <option value="2025">2025</option>
    <option selected="selected" value="2026">2026</option>
  </select>
  <select name="cboPeriod" id="cboPeriod"><option value="All">All</option></select>
</form>
</body></html>
"""


def zip_of(text: str, name: str = DATA_FILE) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(DOCUMENTATION_FILE, "SYS_FIELD_NAME,FIELD_DESC\r\nYEAR,Year\r\n")
        zf.writestr(name, text)
    return buffer.getvalue()


def test_parse_zip_keeps_origin_segments_with_freight() -> None:
    parsed = parse_zip(zip_of(EXTRACT), 2024, YEAR_2024, CONFIG, ORIGINS)

    assert parsed.rows_received == 14
    assert [row[5] for row in parsed.rows] == [
        "TPE", "TPE", "PVG", "PVG", "ICN", "ICN", "MEX", "MEX",
    ]  # fmt: skip
    assert all(row[17] > 0 for row in parsed.rows)


def test_parse_zip_reads_columns_by_name_and_keys_rows_by_line() -> None:
    parsed = parse_zip(zip_of(EXTRACT), 2024, YEAR_2024, CONFIG, ORIGINS)

    assert parsed.rows[0] == (
        2, 2024, 1, "UA", 15306, "TPE", "TW", 781, 14771, "SFO", "US", 91,
        6, 637, 1, "P", 1.0, 67064.0, 0.0, 6469.0,
    )  # fmt: skip
    assert len(TARGET.columns) == len(parsed.rows[0]) + 1


def test_parse_zip_keeps_only_the_requested_months() -> None:
    parsed = parse_zip(zip_of(EXTRACT), 2024, MonthRange("2024-01", "2024-02"), CONFIG, ORIGINS)

    assert {row[2] for row in parsed.rows} == {1, 2}
    assert len(parsed.rows) == 6


def test_parse_zip_without_a_country_filter_keeps_every_origin() -> None:
    parsed = parse_zip(zip_of(EXTRACT), 2024, YEAR_2024, CONFIG, None)

    assert {"DE", "US"} <= {row[6] for row in parsed.rows}
    assert len(parsed.rows) == 12


def test_parse_zip_keeps_segments_without_freight_when_configured() -> None:
    config = CONFIG.model_copy(update={"drop_rows_without_freight": False})

    parsed = parse_zip(zip_of(EXTRACT), 2024, YEAR_2024, config, ORIGINS)

    assert len(parsed.rows) == 10


def test_parse_zip_reports_the_latest_month_in_the_file() -> None:
    parsed = parse_zip(zip_of(EXTRACT), 2024, MonthRange("2024-01", "2024-01"), CONFIG, ORIGINS)

    assert parsed.source_version == "data through 2024-03"


def test_parse_zip_rejects_a_file_for_another_year() -> None:
    with pytest.raises(T100Error, match="not 2025"):
        parse_zip(zip_of(EXTRACT), 2025, MonthRange("2025-01", "2025-12"), CONFIG, ORIGINS)


def test_parse_zip_rejects_a_file_without_a_requested_column() -> None:
    header, _, body = EXTRACT.partition("\r\n")
    without_class = header.removesuffix(",CLASS") + "\r\n" + body

    with pytest.raises(T100Error, match="CLASS"):
        parse_zip(zip_of(without_class), 2024, YEAR_2024, CONFIG, ORIGINS)


def test_parse_zip_rejects_a_zip_without_the_data_file() -> None:
    with pytest.raises(T100Error, match=DATA_FILE):
        parse_zip(zip_of(EXTRACT, "other.csv"), 2024, YEAR_2024, CONFIG, ORIGINS)


def test_parse_zip_rejects_a_non_numeric_amount() -> None:
    broken = EXTRACT.replace("67064.00", "n/a", 1)

    with pytest.raises(T100Error, match="line 2"):
        parse_zip(zip_of(broken), 2024, YEAR_2024, CONFIG, ORIGINS)


def test_read_form_takes_the_download_forms_hidden_fields_and_years() -> None:
    hidden, years = read_form(FORM_PAGE)

    assert hidden == {"__VIEWSTATE": "state", "__EVENTVALIDATION": "validation"}
    assert years == ["2025", "2026"]


def test_read_form_rejects_a_page_without_the_form() -> None:
    with pytest.raises(T100Error, match="no form"):
        read_form("<html><body>Maintenance</body></html>")


@respx.mock
def test_fetch_year_returns_none_when_the_form_does_not_offer_the_year() -> None:
    respx.get(FORM_URL).mock(return_value=httpx.Response(200, text=FORM_PAGE))

    with httpx.Client() as client:
        assert fetch_year(client, CONFIG, 2027) is None


@respx.mock
def test_fetch_year_posts_the_form_back_with_the_year_and_fields() -> None:
    respx.get(FORM_URL).mock(return_value=httpx.Response(200, text=FORM_PAGE))
    post = respx.post(FORM_URL).mock(return_value=httpx.Response(200, content=zip_of(EXTRACT)))

    with httpx.Client() as client:
        body = fetch_year(client, CONFIG, 2025)

    assert body == zip_of(EXTRACT)
    sent = parse_qs(post.calls.last.request.content.decode())
    assert sent["__VIEWSTATE"] == ["state"]
    assert sent["cboYear"] == ["2025"]
    assert all(sent[field] == ["on"] for field in FIELDS)


@respx.mock
def test_fetch_year_rejects_a_response_that_is_not_a_zip() -> None:
    respx.get(FORM_URL).mock(return_value=httpx.Response(200, text=FORM_PAGE))
    respx.post(FORM_URL).mock(return_value=httpx.Response(200, text="<html>Error</html>"))

    with httpx.Client() as client, pytest.raises(T100Error, match="not a ZIP"):
        fetch_year(client, CONFIG, 2025)


def test_load_year_rejects_months_outside_the_year(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    with pytest.raises(T100Error, match="not all in 2024"):
        load_year(
            conn, memory_archive, CONFIG, ORIGINS, 2024, MonthRange("2023-12", "2024-01"), None
        )


def test_load_year_archives_the_zip_and_records_the_filters_and_version(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    body = zip_of(EXTRACT)

    result = load_year(conn, memory_archive, CONFIG, ORIGINS, 2024, YEAR_2024, lambda: body)

    assert memory_archive.objects[archive_key(2024)] == body
    assert result.row_count == 8
    manifest = conn.execute(
        "SELECT partition_key, source_version, params FROM raw.load_manifest WHERE load_id = %s",
        (result.load_id,),
    ).fetchone()
    assert manifest is not None
    partition, version, params = manifest
    assert (partition, version) == ("2024", "data through 2024-03")
    assert params["rows_received"] == 14
    assert (params["first_month"], params["last_month"]) == ("2024-01", "2024-12")
    assert params["filters"] == {"drop_rows_without_freight": True, "origin_countries": ORIGINS}
    assert conn.execute("SELECT count(*) FROM raw.bts_t100_segments").fetchone() == (8,)
