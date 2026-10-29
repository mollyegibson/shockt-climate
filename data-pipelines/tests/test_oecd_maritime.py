import psycopg
import pytest

from shockt.config import OecdMaritimeConfig
from shockt.months import MonthRange
from shockt.sources.oecd_maritime import (
    DATASET,
    TARGET,
    OecdMaritimeError,
    load_year,
    parse_csv,
    partition_key,
    sdmx_key,
)
from tests.conftest import MemoryArchive

HEADER = (
    "DATAFLOW,REF_AREA,FREQ,MEASURE,UNIT_MEASURE,ADJUSTMENT,POLLUTANT,SOURCE,VESSEL,"
    "TIME_PERIOD,OBS_VALUE,OBS_STATUS,UNIT_MULT,DECIMALS\n"
)
PREFIX = "OECD.SDD.NAD.SEEA:DSD_MARITIME_TRANSPORT@DF_MARITIME_TRANSPORT(1.0)"
ROW_DNK = f"{PREFIX},DNK,M,EMISSIONS,T,N,CO2,ESTIMATED,ALL_VESSELS,2024-02,3814777.85,,0,0\n"
ROW_WORLD = f"{PREFIX},W,M,EMISSIONS,T,N,CO2,ESTIMATED,CONTAINER,2024-02,9000000.5,,0,0\n"
ROW_BLANK = f"{PREFIX},FIN,M,EMISSIONS,T,N,CO2,ESTIMATED,ALL_VESSELS,2024-03,,E,0,0\n"
ROW_QUARTER = f"{PREFIX},DNK,Q,EMISSIONS,T,N,CO2,ESTIMATED,ALL_VESSELS,2024-Q1,1.0,,0,0\n"

CONFIG = OecdMaritimeConfig(
    base_url="https://test.example.com", dataflow="A,B,1.0", timeout_seconds=10
)


def csv_body(*rows: str) -> bytes:
    return (HEADER + "".join(rows)).encode()


def test_sdmx_key_leaves_every_dimension_open_except_monthly_frequency() -> None:
    assert sdmx_key() == ".M......"


def test_parse_csv_keeps_aggregates_and_ship_types() -> None:
    parsed = parse_csv(csv_body(ROW_DNK, ROW_WORLD))

    assert parsed.rows_received == 2
    assert parsed.rows[0] == (
        "2024-02", "DNK", "EMISSIONS", "T", "N", "CO2", "ESTIMATED", "ALL_VESSELS",
        None, 0, 3814777.85,
    )  # fmt: skip
    assert parsed.rows[1][1] == "W"
    assert parsed.rows[1][7] == "CONTAINER"
    assert len(TARGET.columns) == len(parsed.rows[0]) + 1


def test_parse_csv_reads_a_blank_value_as_null_and_keeps_the_status() -> None:
    parsed = parse_csv(csv_body(ROW_BLANK))

    assert parsed.rows[0][-3:] == ("E", 0, None)


def test_parse_csv_rejects_a_quarterly_row() -> None:
    with pytest.raises(OecdMaritimeError, match="not monthly"):
        parse_csv(csv_body(ROW_DNK, ROW_QUARTER))


def test_parse_csv_rejects_an_empty_response() -> None:
    with pytest.raises(OecdMaritimeError, match="empty response"):
        parse_csv(b"")


def test_parse_csv_rejects_a_header_without_observations() -> None:
    with pytest.raises(OecdMaritimeError, match="no observations"):
        parse_csv(csv_body())


def test_parse_csv_rejects_a_bad_header() -> None:
    with pytest.raises(OecdMaritimeError, match="missing columns"):
        parse_csv(b"col_a,col_b\nval,val\n")


def test_load_year_rejects_months_outside_the_year(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    with pytest.raises(OecdMaritimeError, match="not all in 2024"):
        load_year(conn, memory_archive, CONFIG, 2024, MonthRange("2023-12", "2024-02"), None)


def test_load_writes_rows_and_archives(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    body = csv_body(ROW_DNK, ROW_WORLD, ROW_BLANK)

    result = load_year(
        conn, memory_archive, CONFIG, 2024, MonthRange("2024-01", "2024-12"), lambda: body
    )

    assert partition_key(2024) == "2024"
    assert result.row_count == 3
    assert memory_archive.objects[f"raw/{DATASET}/2024/2024.csv"] == body
    rows = conn.execute(
        "SELECT ref_area, vessel, obs_value FROM raw.oecd_maritime_emissions"
        " WHERE load_id = %s ORDER BY ref_area",
        (result.load_id,),
    ).fetchall()
    assert rows == [("DNK", "ALL_VESSELS", 3814777.85), ("FIN", "ALL_VESSELS", None),
                    ("W", "CONTAINER", 9000000.5)]  # fmt: skip
