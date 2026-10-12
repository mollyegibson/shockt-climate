import io
import json
import zipfile
from collections.abc import Callable
from datetime import date

import httpx
import psycopg
import pytest
import respx
from tenacity import wait_none

from shockt import http
from shockt.config import BorderCrossingsConfig, GeonamesCitiesConfig
from shockt.sources import reference
from tests.conftest import MemoryArchive

AIRPORTS_CSV = (
    '"id","ident","type","name","latitude_deg","longitude_deg","elevation_ft","continent",'
    '"iso_country","iso_region","municipality","scheduled_service","icao_code","iata_code",'
    '"gps_code","local_code","home_link","wikipedia_link","keywords"\n'
    '3878,"KSFO","large_airport","San Francisco International Airport",37.619806,-122.374821,'
    '13,"NA","US","US-CA","San Francisco","yes","KSFO","SFO","KSFO","SFO",,,\n'
    '6523,"00A","heliport","Total RF Heliport",40.070985,-74.933689,11,"NA","US","US-PA",'
    '"Bensalem","no",,,"K00A","00A",,,\n'
)
BORDER = BorderCrossingsConfig(
    url="https://example.invalid/resource/x.json", border="US-Mexico Border", page_size=2
)


def geonames_line(geonameid: str, name: str, country: str, population: str) -> str:
    fields = [""] * 19
    values = {
        0: geonameid,
        1: name,
        2: name,
        3: "Alt1,Alt2",
        4: "39.04",
        5: "-77.49",
        6: "P",
        7: "PPL",
        8: country,
        10: "VA",
        14: population,
        17: "America/New_York",
        18: "2024-01-10",
    }
    for index, value in values.items():
        fields[index] = value
    return "\t".join(fields)


def geonames_zip(*lines: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("cities5000.txt", "\n".join(lines))
    return buffer.getvalue()


def crossing(port_code: str, day: str, measure: str, value: str) -> dict[str, object]:
    return {
        "port_name": "Laredo",
        "state": "Texas",
        "port_code": port_code,
        "border": "US-Mexico Border",
        "date": f"{day}T00:00:00.000",
        "measure": measure,
        "value": value,
        "latitude": "27.499561",
        "longitude": "-99.507412",
    }


@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http, "RETRY_WAIT", wait_none())


def test_parse_ourairports_keeps_airports_with_an_iata_code() -> None:
    parsed = reference.parse_ourairports(AIRPORTS_CSV.encode())

    assert parsed.rows_received == 2
    row = dict(zip(reference.OURAIRPORTS.columns[1:], parsed.rows[0], strict=True))
    assert len(parsed.rows) == 1
    assert row["iata_code"] == "SFO"
    assert row["longitude_deg"] == -122.374821
    assert row["elevation_ft"] == 13


def test_parse_ourairports_rejects_a_file_without_coordinates() -> None:
    with pytest.raises(reference.ReferenceSourceError, match="latitude_deg"):
        reference.parse_ourairports(b'"id","iata_code"\n1,"SFO"\n')


def test_parse_geonames_filters_countries_and_drops_alternate_names() -> None:
    config = GeonamesCitiesConfig(url="unused", countries=["US", "MX"])
    body = geonames_zip(
        geonames_line("4744870", "Ashburn", "US", "43511"),
        geonames_line("3121070", "Guadalajara", "ES", "93470"),
    )

    parsed = reference.parse_geonames(body, config)

    assert parsed.rows_received == 2
    row = dict(zip(reference.GEONAMES.columns[1:], parsed.rows[0], strict=True))
    assert len(parsed.rows) == 1
    assert row["name"] == "Ashburn" and row["population"] == 43511
    assert row["modification_date"] == date(2024, 1, 10)
    assert "Alt1,Alt2" not in parsed.rows[0]


def test_parse_geonames_rejects_a_changed_layout() -> None:
    config = GeonamesCitiesConfig(url="unused", countries=["US"])

    with pytest.raises(reference.ReferenceSourceError, match="18 fields"):
        reference.parse_geonames(geonames_zip("\t".join([""] * 18)), config)


@respx.mock
def test_fetch_border_crossings_pages_until_a_short_page() -> None:
    route = respx.get(BORDER.url).mock(
        side_effect=[
            httpx.Response(
                200,
                json=[
                    crossing("2304", "2024-01-01", "Trucks", "1"),
                    crossing("2304", "2024-01-01", "Trains", "2"),
                ],
            ),
            httpx.Response(200, json=[crossing("2304", "2024-02-01", "Trucks", "3")]),
        ]
    )

    with httpx.Client() as client:
        bundle = reference.fetch_border_crossings(client, BORDER, "2022-01")

    assert [c.request.url.params["$offset"] for c in route.calls] == ["0", "2"]
    assert "date >= '2022-01-01'" in route.calls[0].request.url.params["$where"]
    assert len(reference.parse_border_crossings(bundle).rows) == 3


def test_parse_border_crossings_types_values_and_drops_duplicates() -> None:
    row = crossing("2304", "2024-01-01", "Trucks", "1")
    bundle = json.dumps(
        {"fetched_at": "2026-10-12T00:00:00+00:00", "pages": [{"params": {}, "rows": [row, row]}]}
    ).encode()

    parsed = reference.parse_border_crossings(bundle)

    assert parsed.rows_received == 2
    assert parsed.rows == [
        (
            "Laredo",
            "Texas",
            "2304",
            "US-Mexico Border",
            date(2024, 1, 1),
            "Trucks",
            1,
            27.499561,
            -99.507412,
        )
    ]


def test_reload_replaces_the_latest_snapshot(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    def load() -> reference.LoadResult:
        return reference.load(
            conn,
            memory_archive,
            reference.OURAIRPORTS,
            "airports.csv",
            "text/csv",
            {},
            AIRPORTS_CSV.encode,
            reference.parse_ourairports,
            "Tue, 01 Oct 2026 00:00:00 GMT",
        )

    first = load()
    second = load()

    assert second.superseded_load_id == first.load_id
    assert conn.execute("SELECT count(*) FROM raw.ourairports_airports").fetchone() == (1,)
    manifest = conn.execute(
        "SELECT partition_key, source_version FROM raw.load_manifest WHERE load_id = %s",
        (second.load_id,),
    ).fetchone()
    assert manifest == ("latest", "Tue, 01 Oct 2026 00:00:00 GMT")


def test_reload_from_the_archive_keeps_the_archived_source_version(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    def load(obtain: Callable[[], bytes] | None, version: str | None) -> reference.LoadResult:
        return reference.load(
            conn,
            memory_archive,
            reference.OURAIRPORTS,
            "airports.csv",
            "text/csv",
            {},
            obtain,
            reference.parse_ourairports,
            version,
        )

    load(AIRPORTS_CSV.encode, "Tue, 01 Oct 2026 00:00:00 GMT")
    reloaded = load(None, None)

    manifest = conn.execute(
        "SELECT source_version, params ? 'from_archive' FROM raw.load_manifest WHERE load_id = %s",
        (reloaded.load_id,),
    ).fetchone()
    assert manifest == ("Tue, 01 Oct 2026 00:00:00 GMT", True)
