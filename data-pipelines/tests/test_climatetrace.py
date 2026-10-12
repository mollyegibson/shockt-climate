import io
import json
from collections.abc import Sequence
from datetime import UTC, datetime

import psycopg
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from shockt.config import ClimateTraceConfig
from shockt.sources.climatetrace import (
    METADATA_KEY,
    RESULT_COLUMNS,
    TARGET,
    ClimateTraceError,
    archive_key,
    fetch_year,
    load_year,
    parse_year,
    year_query,
)
from tests.conftest import MemoryArchive

CONFIG = ClimateTraceConfig(
    table="project.dataset.shipping_voyages", origin_iso3=["TWN", "MEX"], destination_iso3=["USA"]
)


def voyage(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "start_date": datetime(2024, 1, 12, 8, 1, 34, tzinfo=UTC),
        "end_date": datetime(2024, 1, 28, 12, 5, 3, tzinfo=UTC),
        "asset_identifier": "om-imo-9757876",
        "model_number": "om.30062026",
        "asset_name": "Example Ship",
        "iso3_country": "HKG",
        "type": "container",
        "capacity": 145300.0,
        "capacity_factor": 0.043,
        "activity": 6268.439,
        "CO2_emissions_factor": 0.846,
        "CO2_emissions": 5303.1,
        "total_CO2e_100yrGWP": 5388.714,
        "other1": "16.04:03:29",
        "other2": "Kaohsiung",
        "other3": "Port of Long Beach,CA",
        "other4": "TWN",
        "other5": "USA",
        "other6": "TWN_1",
        "other7": "USA_2",
        "other8": True,
        "other11": 153949.0,
        "other12": 847.498,
        "original_inventory_sector": "international-shipping",
        "start_lon": 120.28,
        "start_lat": 22.61,
        "end_lon": -118.21,
        "end_lat": 33.75,
    }
    return {**base, **overrides}


class FakeJob:
    def __init__(self, table: pa.Table, scanned: int) -> None:
        self._table = table
        self.total_bytes_processed = scanned

    def to_arrow(self) -> pa.Table:
        return self._table


class FakeRunner:
    def __init__(self, estimate: int, rows: list[dict[str, object]]) -> None:
        self.estimate = estimate
        self.rows = rows
        self.runs: list[int] = []

    def dry_run(self, sql: str, params: Sequence[tuple[str, str, object]]) -> int:
        return self.estimate

    def run(self, sql: str, params: Sequence[tuple[str, str, object]], max_bytes: int) -> FakeJob:
        self.runs.append(max_bytes)
        return FakeJob(pa.Table.from_pylist(self.rows), self.estimate)

    def table_release(self, table: str) -> str:
        return "v5_11_0"


def parquet(rows: list[dict[str, object]], year: int) -> bytes:
    return fetch_year(FakeRunner(10**9, rows), CONFIG, year, max_bytes=10**10)


def test_year_query_passes_values_as_parameters() -> None:
    query = year_query(CONFIG, 2024)

    assert "@start" in query.sql and "@origins" in query.sql
    assert "TWN" not in query.sql and "2024" not in query.sql
    assert dict((n, v) for n, _, v in query.params)["origins"] == ["TWN", "MEX"]
    assert "ST_X(ST_ENDPOINT(location)) AS end_lon" in query.sql


def test_fetch_year_refuses_a_query_over_the_cap_without_running_it() -> None:
    runner = FakeRunner(estimate=200 * 10**9, rows=[voyage()])

    with pytest.raises(ClimateTraceError, match="200.0 GB"):
        fetch_year(runner, CONFIG, 2024, max_bytes=100 * 10**9)

    assert runner.runs == []


def test_fetch_year_runs_with_the_cap_and_records_metadata() -> None:
    runner = FakeRunner(estimate=6 * 10**9, rows=[voyage()])

    body = fetch_year(runner, CONFIG, 2024, max_bytes=100 * 10**9)

    assert runner.runs == [100 * 10**9]
    metadata = json.loads(pq.read_table(io.BytesIO(body)).schema.metadata[METADATA_KEY])
    assert metadata["release"] == "v5_11_0"
    assert metadata["bytes_processed"] == 6 * 10**9
    assert metadata["year"] == 2024


def test_parse_year_maps_columns_and_drops_duplicate_voyages() -> None:
    parsed = parse_year(parquet([voyage(), voyage()], 2024), 2024)

    assert parsed.rows_received == 2
    assert len(parsed.rows) == 1
    row = dict(zip(TARGET.columns[1:], parsed.rows[0], strict=True))
    assert row["activity"] == 6268.439
    assert row["co2_emissions_factor"] == 0.846
    assert row["other3"] == "Port of Long Beach,CA"
    assert parsed.source_version == "release v5_11_0"
    assert parsed.bytes_processed == 10**9
    assert row["end_lon"] == -118.21
    assert len(TARGET.columns) == len(RESULT_COLUMNS) + 1


def test_parse_year_rejects_a_voyage_from_another_year() -> None:
    body = parquet([voyage(start_date=datetime(2023, 12, 31, tzinfo=UTC))], 2024)

    with pytest.raises(ClimateTraceError, match="not in 2024"):
        parse_year(body, 2024)


def test_parse_year_rejects_a_file_archived_for_another_year() -> None:
    with pytest.raises(ClimateTraceError, match="for 2024, not 2025"):
        parse_year(parquet([voyage()], 2024), 2025)


def test_load_year_records_bytes_processed_in_the_manifest(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    body = parquet([voyage(), voyage(asset_identifier="om-imo-1")], 2024)

    result = load_year(conn, memory_archive, CONFIG, 2024, lambda: body)

    assert memory_archive.objects[archive_key(2024)] == body
    assert result.row_count == 2
    manifest = conn.execute(
        "SELECT partition_key, source_version, bytes_processed FROM raw.load_manifest "
        "WHERE load_id = %s",
        (result.load_id,),
    ).fetchone()
    assert manifest == ("2024", "release v5_11_0", 10**9)


def test_parse_year_rejects_an_archive_without_port_coordinates() -> None:
    old = {k: v for k, v in voyage().items() if not k.startswith(("start_l", "end_l"))}
    body = parquet([old], 2024)

    with pytest.raises(ClimateTraceError, match="reload the year"):
        parse_year(body, 2024)
