import json

import httpx
import pytest
import respx
from tenacity import wait_none

from shockt import http
from shockt.archive import NeonArchive
from shockt.config import CensusApiConfig, CensusRowFilter, HsCodesConfig, HsPrefix
from shockt.settings import Settings
from shockt.sources.census_api import DATASETS, CensusResponseError, fetch_bundle
from tests.conftest import census_fixture

BASE = "https://api.census.gov/data/timeseries/intltrade/imports"
KEY = "0123456789abcdef0123456789abcdef01234567"
KEEP_ALL = CensusRowFilter(drop_country_groups=False, drop_all_zero=False)
CONFIG = CensusApiConfig(
    base_url=BASE,
    comm_lvl={"hs": "HS10", "porths": "HS6", "statehs": "HS6"},
    timeout_seconds=10,
    filters={"hs": KEEP_ALL, "porths": KEEP_ALL, "statehs": KEEP_ALL},
)
HS_CODES = HsCodesConfig(
    prefixes=[
        HsPrefix(prefix="847150", level="HS6", label="servers", cases=[]),
        HsPrefix(prefix="8504", level="HS4", label="transformers", cases=[]),
    ]
)


@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http, "RETRY_WAIT", wait_none())


@respx.mock
def test_get_retries_server_errors_then_succeeds() -> None:
    route = respx.get(f"{BASE}/hs").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=[["A"], ["1"]])]
    )
    with httpx.Client() as client:
        response = http.get(client, f"{BASE}/hs", {"key": KEY}, secrets=(KEY,))

    assert response.status_code == 200
    assert route.call_count == 2


@respx.mock
def test_get_error_message_never_contains_the_key() -> None:
    respx.get(f"{BASE}/hs").mock(return_value=httpx.Response(404))
    with httpx.Client() as client, pytest.raises(http.SourceRequestError) as raised:
        http.get(client, f"{BASE}/hs", {"key": KEY}, secrets=(KEY,))

    assert KEY not in str(raised.value)
    assert "<redacted>" in str(raised.value)


@respx.mock
def test_fetch_bundle_requests_each_prefix_and_omits_the_key() -> None:
    route = respx.get(f"{BASE}/hs").mock(
        side_effect=[httpx.Response(200, json=census_fixture("hs")), httpx.Response(204)]
    )
    with httpx.Client() as client:
        bundle = fetch_bundle(client, DATASETS["hs"], "2024-12", CONFIG, HS_CODES, KEY)

    requested = [call.request.url.params["I_COMMODITY"] for call in route.calls]
    assert requested == ["847150*", "8504*"]
    assert KEY not in bundle.decode()
    data = json.loads(bundle)
    assert [r["status"] for r in data["responses"]] == [200, 204]
    assert data["responses"][1]["body"] is None


@respx.mock
def test_fetch_bundle_reports_an_invalid_key_page() -> None:
    respx.get(f"{BASE}/hs").mock(
        return_value=httpx.Response(200, text="<html><title>Invalid Key</title></html>")
    )
    with httpx.Client() as client, pytest.raises(CensusResponseError, match="Invalid Key"):
        fetch_bundle(client, DATASETS["hs"], "2024-12", CONFIG, HS_CODES, KEY)


def test_neon_archive_ignores_the_shells_aws_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_PROFILE", "a-profile-that-does-not-exist")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "shell-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "shell-secret")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    settings = Settings(
        database_url="postgresql://unused@localhost/unused",
        neon_s3_endpoint_url="https://example.invalid",
        neon_s3_access_key_id="neon-key",
        neon_s3_secret_access_key="neon-secret",
    )

    client = NeonArchive(settings).client

    credentials = client._request_signer._credentials
    assert credentials.access_key == "neon-key"
    assert client.meta.region_name == "us-east-2"
