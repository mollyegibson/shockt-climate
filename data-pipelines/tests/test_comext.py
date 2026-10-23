import psycopg
import pytest

from shockt.sources.comext import (
    DATASET,
    TARGET,
    ComextSourceError,
    load_month,
    parse_csv,
    partition_key,
)
from tests.conftest import MemoryArchive

HEADER = (
    "DATAFLOW,LAST UPDATE,freq,reporter,partner,product,"
    "flow,transport_mode,indicators,TIME_PERIOD,OBS_VALUE,OBS_FLAG\n"
)

ROW_KG = "DS-059334,20260901,M,DE,CN,850434,1,1,QUANTITY_KG,2024-06,1234567,\n"
ROW_EUR = "DS-059334,20260901,M,DE,CN,850434,1,1,VALUE_EUR,2024-06,9876543,\n"
ROW_MISSING = "DS-059334,20260901,M,FR,JP,850434,1,3,QUANTITY_KG,2024-06,:,\n"


def csv_body(*rows: str) -> bytes:
    return (HEADER + "".join(rows)).encode()


def test_parse_csv_pivots_nothing_by_default() -> None:
    parsed = parse_csv(csv_body(ROW_KG, ROW_EUR))

    assert len(parsed.rows) == 2
    assert parsed.rows_received == 2
    assert parsed.rows[0] == ("2024-06", "DE", "CN", "850434", "1", "1", "QUANTITY_KG", 1234567.0)
    assert parsed.rows[1] == ("2024-06", "DE", "CN", "850434", "1", "1", "VALUE_EUR", 9876543.0)


def test_parse_csv_treats_colon_as_null() -> None:
    parsed = parse_csv(csv_body(ROW_MISSING))

    assert parsed.rows[0][-1] is None


def test_parse_csv_rejects_empty_response() -> None:
    with pytest.raises(ComextSourceError, match="empty response"):
        parse_csv(b"")


def test_parse_csv_rejects_bad_header() -> None:
    with pytest.raises(ComextSourceError, match="missing columns"):
        parse_csv(b"col_a,col_b\nval,val\n")


def test_partition_key_format() -> None:
    assert partition_key("2024-06", "850434") == "2024-06:850434"


def test_target_columns_match_raw_table() -> None:
    assert TARGET.columns[0] == "load_id"
    assert TARGET.table == "comext_trade"
    assert TARGET.dataset == DATASET


def test_load_writes_rows_and_archives(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    body = csv_body(ROW_KG, ROW_EUR)
    from shockt.config import ComextConfig

    config = ComextConfig(
        base_url="https://test.example.com",
        dataset="DS-059334",
        flow="1",
        indicators=["QUANTITY_KG", "VALUE_EUR"],
        timeout_seconds=10,
    )
    result = load_month(
        conn, memory_archive, config, ["DE"], ["CN"], "850434", "2024-06", lambda: body
    )

    assert result.row_count == 2
    rows = conn.execute(
        "SELECT reporter, partner, indicator, obs_value"
        " FROM raw.comext_trade WHERE load_id = %s ORDER BY indicator",
        (result.load_id,),
    ).fetchall()
    assert len(rows) == 2
    assert rows[0] == ("DE", "CN", "QUANTITY_KG", 1234567)
    assert rows[1] == ("DE", "CN", "VALUE_EUR", 9876543)
