import json
from datetime import date

import httpx
import psycopg
import pytest
import respx
from tenacity import wait_none

from shockt import http
from shockt.config import PortwatchConfig
from shockt.months import MonthRange
from shockt.sources.portwatch import (
    TARGET,
    LayerInfo,
    PortwatchError,
    archive_key,
    fetch_bundle,
    layer_info,
    load_year,
    parse_bundle,
)
from tests.conftest import FIXTURES, MemoryArchive

QUERY_URL = "https://example.invalid/arcgis/FeatureServer/0/query"
CONFIG = PortwatchConfig(query_url=QUERY_URL, chokepoints=["chokepoint2"])
EDITED = "2026-10-05T12:00:00+00:00"
LAYER = LayerInfo(data_last_edited=EDITED, max_record_count=2)
YEAR_2023 = MonthRange("2023-01", "2023-12")


def fixture_page() -> dict[str, object]:
    return json.loads((FIXTURES / "portwatch_chokepoint2_2023_page.json").read_text())


def bundle(*pages: dict[str, object], portid: str = "chokepoint2", year: int = 2023) -> bytes:
    return json.dumps(
        {
            "portid": portid,
            "year": year,
            "fetched_at": "2026-10-09T00:00:00+00:00",
            "data_last_edited": EDITED,
            "pages": [{"params": {}, "body": page} for page in pages],
        }
    ).encode()


@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http, "RETRY_WAIT", wait_none())


def test_parse_bundle_types_values_and_records_the_version() -> None:
    parsed = parse_bundle(bundle(fixture_page()), YEAR_2023)

    first = dict(zip(TARGET.columns[1:], parsed.rows[0], strict=True))
    assert len(parsed.rows) == 3
    assert first["date"] == date(2023, 1, 1)
    assert first["portname"] == "Panama Canal"
    assert first["n_container"] == 7
    assert first["capacity"] == 1_088_424
    assert parsed.source_version == f"data last edited {EDITED}"


def test_parse_bundle_drops_rows_repeated_across_pages() -> None:
    page = fixture_page()

    assert len(parse_bundle(bundle(page, page), YEAR_2023).rows) == 3


def test_parse_bundle_rejects_rows_for_another_chokepoint() -> None:
    with pytest.raises(PortwatchError, match="not chokepoint1 2023"):
        parse_bundle(bundle(fixture_page(), portid="chokepoint1"), YEAR_2023)


@respx.mock
def test_fetch_bundle_follows_pages_until_the_limit_flag_clears() -> None:
    page = fixture_page()
    features = page["features"]
    assert isinstance(features, list)
    first = {"features": features[:2], "exceededTransferLimit": True}
    second = {"features": features[2:]}
    route = respx.get(QUERY_URL).mock(
        side_effect=[httpx.Response(200, json=first), httpx.Response(200, json=second)]
    )

    with httpx.Client() as client:
        data = json.loads(fetch_bundle(client, CONFIG, "chokepoint2", 2023, LAYER))

    offsets = [call.request.url.params["resultOffset"] for call in route.calls]
    assert offsets == ["0", "2"]
    assert route.calls[0].request.url.params["where"] == "portid='chokepoint2' AND year=2023"
    assert len(parse_bundle(json.dumps(data).encode(), YEAR_2023).rows) == 3


@respx.mock
def test_an_error_returned_with_http_200_fails_the_fetch() -> None:
    respx.get(QUERY_URL).mock(
        return_value=httpx.Response(200, json={"error": {"code": 400, "message": "Invalid query"}})
    )

    with httpx.Client() as client, pytest.raises(PortwatchError, match="Invalid query"):
        fetch_bundle(client, CONFIG, "chokepoint2", 2023, LAYER)


@respx.mock
def test_layer_info_reads_the_last_edit_and_page_size() -> None:
    respx.get(QUERY_URL.removesuffix("/query")).mock(
        return_value=httpx.Response(
            200, json={"editingInfo": {"dataLastEditDate": 1791288541457}, "maxRecordCount": 1000}
        )
    )

    with httpx.Client() as client:
        assert layer_info(client, CONFIG) == LayerInfo("2026-10-06T12:09:01+00:00", 1000)


@respx.mock
def test_layer_info_fails_without_a_page_size() -> None:
    respx.get(QUERY_URL.removesuffix("/query")).mock(
        return_value=httpx.Response(200, json={"editingInfo": {"dataLastEditDate": 1791288541457}})
    )

    with httpx.Client() as client, pytest.raises(PortwatchError, match="maxRecordCount"):
        layer_info(client, CONFIG)


def test_load_year_archives_and_writes_the_partition(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    body = bundle(fixture_page())

    result = load_year(conn, memory_archive, "chokepoint2", 2023, YEAR_2023, lambda: body)

    assert memory_archive.objects[archive_key("chokepoint2", 2023)] == body
    assert result.row_count == 3
    manifest = conn.execute(
        "SELECT partition_key, source_version FROM raw.load_manifest WHERE load_id = %s",
        (result.load_id,),
    ).fetchone()
    assert manifest == ("chokepoint2:2023", f"data last edited {EDITED}")


def test_parse_bundle_keeps_only_days_in_the_requested_months() -> None:
    parsed = parse_bundle(bundle(fixture_page()), MonthRange("2023-02", "2023-12"))

    assert parsed.rows == []
    assert parsed.rows_received == 3


def test_load_year_records_the_months_loaded(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    body = bundle(fixture_page())

    result = load_year(
        conn, memory_archive, "chokepoint2", 2023, MonthRange("2023-01", "2023-06"), lambda: body
    )

    params = conn.execute(
        "SELECT params FROM raw.load_manifest WHERE load_id = %s", (result.load_id,)
    ).fetchone()
    assert params is not None
    assert (params[0]["first_month"], params[0]["last_month"]) == ("2023-01", "2023-06")


def test_load_year_rejects_months_outside_the_year(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    with pytest.raises(PortwatchError, match="not all in 2023"):
        load_year(
            conn, memory_archive, "chokepoint2", 2023, MonthRange("2022-12", "2023-02"), lambda: b""
        )
