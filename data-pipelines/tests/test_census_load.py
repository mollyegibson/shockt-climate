import json

import psycopg
import pytest

from shockt.config import CensusRowFilter
from shockt.sources.census_api import DATASETS, CensusResponseError, load_month
from tests.conftest import MemoryArchive, census_fixture

MONTH = "2024-12"
PREFIX = "847150"
KEY = "raw/census_porths/2024-12:847150/responses.json"
KEEP_ALL = CensusRowFilter(drop_country_groups=False, drop_all_zero=False)


def bundle(endpoint: str, body: list[list[str]] | None = None) -> bytes:
    return json.dumps(
        {
            "fetched_at": "2026-10-08T12:00:00+00:00",
            "responses": [
                {"params": {}, "status": 200, "body": body or census_fixture(endpoint)},
            ],
        }
    ).encode()


def manifest(conn: psycopg.Connection) -> list[tuple[object, ...]]:
    return conn.execute(
        "SELECT status, row_count, object_key, error IS NOT NULL FROM raw.load_manifest "
        "ORDER BY started_at, status"
    ).fetchall()


def row_count(conn: psycopg.Connection, table: str) -> int:
    row = conn.execute(f"SELECT count(*) FROM raw.{table}").fetchone()
    assert row is not None
    return row[0]


def test_load_archives_then_writes_rows_and_manifest(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    spec = DATASETS["porths"]
    expected = len(census_fixture("porths")) - 1

    result = load_month(
        conn, memory_archive, spec, MONTH, PREFIX, lambda: bundle("porths"), row_filter=KEEP_ALL
    )

    assert result.row_count == expected
    assert KEY in memory_archive.objects
    assert row_count(conn, "census_porths") == expected
    assert manifest(conn) == [("succeeded", expected, KEY, False)]


def test_reloading_a_month_supersedes_the_earlier_load(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    spec = DATASETS["porths"]
    first = load_month(
        conn, memory_archive, spec, MONTH, PREFIX, lambda: bundle("porths"), row_filter=KEEP_ALL
    )

    second = load_month(
        conn, memory_archive, spec, MONTH, PREFIX, lambda: bundle("porths"), row_filter=KEEP_ALL
    )

    assert second.superseded_load_id == first.load_id
    assert row_count(conn, "census_porths") == second.row_count
    statuses = conn.execute(
        "SELECT load_id, status, superseded_by FROM raw.load_manifest"
    ).fetchall()
    assert (first.load_id, "superseded", second.load_id) in statuses
    assert (second.load_id, "succeeded", None) in statuses


def test_a_failed_load_records_the_error_and_keeps_the_earlier_rows(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    spec = DATASETS["porths"]
    good = load_month(
        conn, memory_archive, spec, MONTH, PREFIX, lambda: bundle("porths"), row_filter=KEEP_ALL
    )
    broken = census_fixture("porths")
    broken[1][broken[0].index("AIR_WGT_MO")] = "not-a-number"

    with pytest.raises(CensusResponseError):
        load_month(
            conn,
            memory_archive,
            spec,
            MONTH,
            PREFIX,
            lambda: bundle("porths", broken),
            row_filter=KEEP_ALL,
        )

    assert row_count(conn, "census_porths") == good.row_count
    rows = conn.execute(
        "SELECT status, error FROM raw.load_manifest ORDER BY started_at"
    ).fetchall()
    assert [status for status, _ in rows] == ["succeeded", "failed"]
    assert "not-a-number" in rows[1][1]


def test_reparsing_from_the_archive_does_not_fetch(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    spec = DATASETS["porths"]
    load_month(
        conn, memory_archive, spec, MONTH, PREFIX, lambda: bundle("porths"), row_filter=KEEP_ALL
    )

    result = load_month(conn, memory_archive, spec, MONTH, PREFIX, fetch=None, row_filter=KEEP_ALL)

    assert result.row_count == len(census_fixture("porths")) - 1
    params = conn.execute(
        "SELECT params FROM raw.load_manifest WHERE load_id = %s", (result.load_id,)
    ).fetchone()
    assert params is not None and params[0]["from_archive"] is True


@pytest.mark.parametrize("endpoint", ["hs", "statehs"])
def test_every_endpoint_loads_its_fixture(
    conn: psycopg.Connection, memory_archive: MemoryArchive, endpoint: str
) -> None:
    result = load_month(
        conn,
        memory_archive,
        DATASETS[endpoint],
        MONTH,
        PREFIX,
        lambda: bundle(endpoint),
        row_filter=KEEP_ALL,
    )

    assert (
        row_count(conn, f"census_{endpoint}")
        == result.row_count
        == len(census_fixture(endpoint)) - 1
    )


def test_the_filter_drops_rows_and_is_recorded_in_the_manifest(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    asia_and_mexico = CensusRowFilter.model_validate(
        {
            "drop_country_groups": True,
            "drop_all_zero": True,
            "countries": {"code_prefixes": ["5"], "codes": ["2010", "-"]},
        }
    )

    result = load_month(
        conn,
        memory_archive,
        DATASETS["porths"],
        MONTH,
        PREFIX,
        lambda: bundle("porths"),
        asia_and_mexico,
    )

    kept = conn.execute("SELECT cty_code, port FROM raw.census_porths ORDER BY 1, 2").fetchall()
    assert kept == [
        ("-", "1001"),
        ("2010", "-"),
        ("5830", "1001"),
        ("5830", "1003"),
        ("5830", "1012"),
    ]
    params = conn.execute(
        "SELECT params FROM raw.load_manifest WHERE load_id = %s", (result.load_id,)
    ).fetchone()
    assert params is not None
    assert params[0]["rows_received"] == len(census_fixture("porths")) - 1
    assert params[0]["filters"] == asia_and_mexico.model_dump()


def test_each_partition_commits_even_after_an_earlier_read(
    conn: psycopg.Connection, memory_archive: MemoryArchive, migrated_database_url: str
) -> None:
    spec = DATASETS["porths"]
    conn.execute("SELECT 1")
    load_month(conn, memory_archive, spec, MONTH, PREFIX, lambda: bundle("porths"), KEEP_ALL)
    broken = census_fixture("porths")
    broken[1][broken[0].index("AIR_WGT_MO")] = "not-a-number"

    with pytest.raises(CensusResponseError):
        load_month(
            conn, memory_archive, spec, MONTH, "8504", lambda: bundle("porths", broken), KEEP_ALL
        )

    with psycopg.connect(migrated_database_url) as other:
        statuses = other.execute(
            "SELECT partition_key, status FROM raw.load_manifest ORDER BY partition_key"
        ).fetchall()
    assert statuses == [("2024-12:847150", "succeeded"), ("2024-12:8504", "failed")]


def test_loads_refuse_a_connection_without_autocommit(
    migrated_database_url: str, memory_archive: MemoryArchive
) -> None:
    with (
        psycopg.connect(migrated_database_url) as plain,
        pytest.raises(ValueError, match="autocommit"),
    ):
        load_month(
            plain,
            memory_archive,
            DATASETS["porths"],
            MONTH,
            PREFIX,
            lambda: bundle("porths"),
            KEEP_ALL,
        )
