import json
from datetime import date

import httpx
import psycopg
import pytest
import respx
from tenacity import wait_none

from shockt import http
from shockt.config import PortwatchConfig
from shockt.sources.portwatch import (
    TARGET,
    PortwatchError,
    archive_key,
    data_last_edited,
    fetch_bundle,
    load_year,
    parse_bundle,
)
from tests.conftest import FIXTURES, MemoryArchive

QUERY_URL = "https://example.invalid/arcgis/FeatureServer/0/query"
CONFIG = PortwatchConfig(query_url=QUERY_URL, page_size=2, chokepoints={"chokepoint2": "Panama"})
EDITED = "2026-10-05T12:00:00+00:00"


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
    parsed = parse_bundle(bundle(fixture_page()))

    first = dict(zip(TARGET.columns[1:], parsed.rows[0], strict=True))
    assert len(parsed.rows) == 3
    assert first["date"] == date(2023, 1, 1)
    assert first["portname"] == "Panama Canal"
    assert first["n_container"] == 7
    assert first["capacity"] == 1_088_424
    assert parsed.source_version == f"data last edited {EDITED}"


def test_parse_bundle_drops_rows_repeated_across_pages() -> None:
    page = fixture_page()

    assert len(parse_bundle(bundle(page, page)).rows) == 3


def test_parse_bundle_rejects_rows_for_another_chokepoint() -> None:
    with pytest.raises(PortwatchError, match="not chokepoint1 2023"):
        parse_bundle(bundle(fixture_page(), portid="chokepoint1"))


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
        data = json.loads(fetch_bundle(client, CONFIG, "chokepoint2", 2023, EDITED))

    offsets = [call.request.url.params["resultOffset"] for call in route.calls]
    assert offsets == ["0", "2"]
    assert route.calls[0].request.url.params["where"] == "portid='chokepoint2' AND year=2023"
    assert len(parse_bundle(json.dumps(data).encode()).rows) == 3


@respx.mock
def test_an_error_returned_with_http_200_fails_the_fetch() -> None:
    respx.get(QUERY_URL).mock(
        return_value=httpx.Response(200, json={"error": {"code": 400, "message": "Invalid query"}})
    )

    with httpx.Client() as client, pytest.raises(PortwatchError, match="Invalid query"):
        fetch_bundle(client, CONFIG, "chokepoint2", 2023, EDITED)


@respx.mock
def test_data_last_edited_reads_the_layer_info() -> None:
    respx.get(QUERY_URL.removesuffix("/query")).mock(
        return_value=httpx.Response(200, json={"editingInfo": {"dataLastEditDate": 1791288541457}})
    )

    with httpx.Client() as client:
        assert data_last_edited(client, CONFIG) == "2026-10-06T12:09:01+00:00"


def test_load_year_archives_and_writes_the_partition(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    body = bundle(fixture_page())

    result = load_year(conn, memory_archive, "chokepoint2", 2023, lambda: body)

    assert memory_archive.objects[archive_key("chokepoint2", 2023)] == body
    assert result.row_count == 3
    manifest = conn.execute(
        "SELECT partition_key, source_version FROM raw.load_manifest WHERE load_id = %s",
        (result.load_id,),
    ).fetchone()
    assert manifest == ("chokepoint2:2023", f"data last edited {EDITED}")
