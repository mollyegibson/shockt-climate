"""Climate TRACE ship voyages, queried from the public BigQuery dataset.

One partition is one calendar year of voyage start dates, matching the table's partitioning.
Every query runs as a free dry run first and is refused if it would scan more than the
configured byte cap; the real query runs with the same cap as `maximum_bytes_billed`. Each
year's result is archived as Parquet, with the query, release and bytes scanned in the file
metadata, then parsed from the archived copy.
"""

import io
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import psycopg
import pyarrow as pa
import pyarrow.parquet as pq
from google.cloud import bigquery

from shockt.archive import Archive, object_key
from shockt.config import ClimateTraceConfig
from shockt.loading import ParsedSource, Target, load_partition
from shockt.manifest import LoadResult

DATASET = "climatetrace_voyages"
METADATA_KEY = b"shockt"

SOURCE_COLUMNS = (
    "start_date",
    "end_date",
    "asset_identifier",
    "model_number",
    "asset_name",
    "iso3_country",
    "type",
    "capacity",
    "capacity_factor",
    "activity",
    "CO2_emissions_factor",
    "CO2_emissions",
    "total_CO2e_100yrGWP",
    "other1",
    "other2",
    "other3",
    "other4",
    "other5",
    "other6",
    "other7",
    "other8",
    "other11",
    "other12",
    "original_inventory_sector",
)
TARGET = Target(
    dataset=DATASET,
    table="climatetrace_voyages",
    columns=("load_id", *(c.lower() for c in SOURCE_COLUMNS)),
)


class ClimateTraceError(Exception):
    """A query would exceed the byte cap, or an archived result doesn't match its partition."""


class QueryJob(Protocol):
    @property
    def total_bytes_processed(self) -> int | None: ...

    def to_arrow(self) -> pa.Table: ...


class BigQueryRunner(Protocol):
    """The parts of a BigQuery client the loader uses, so tests can substitute a fake."""

    def dry_run(self, sql: str, params: Sequence[tuple[str, str, object]]) -> int: ...

    def run(
        self, sql: str, params: Sequence[tuple[str, str, object]], max_bytes: int
    ) -> QueryJob: ...

    def table_release(self, table: str) -> str: ...


@dataclass(frozen=True)
class YearQuery:
    sql: str
    params: tuple[tuple[str, str, object], ...]
    """(name, BigQuery type, value); array parameters use type `ARRAY<STRING>`."""


def year_query(config: ClimateTraceConfig, year: int) -> YearQuery:
    """Voyages starting in `year` from a configured origin country to a destination country."""
    columns = ",\n  ".join(SOURCE_COLUMNS)
    sql = (
        f"SELECT\n  {columns}\nFROM `{config.table}`\n"
        "WHERE start_date >= @start AND start_date < @end\n"
        "  AND other4 IN UNNEST(@origins)\n"
        "  AND other5 IN UNNEST(@destinations)"
    )
    return YearQuery(
        sql=sql,
        params=(
            ("start", "TIMESTAMP", datetime(year, 1, 1, tzinfo=UTC)),
            ("end", "TIMESTAMP", datetime(year + 1, 1, 1, tzinfo=UTC)),
            ("origins", "ARRAY<STRING>", list(config.origin_iso3)),
            ("destinations", "ARRAY<STRING>", list(config.destination_iso3)),
        ),
    )


def estimate_bytes(runner: BigQueryRunner, config: ClimateTraceConfig, year: int) -> int:
    query = year_query(config, year)
    return runner.dry_run(query.sql, query.params)


def fetch_year(
    runner: BigQueryRunner, config: ClimateTraceConfig, year: int, max_bytes: int
) -> bytes:
    """Run one year's query under the byte cap and return the result as Parquet."""
    query = year_query(config, year)
    estimate = runner.dry_run(query.sql, query.params)
    if estimate > max_bytes:
        raise ClimateTraceError(
            f"{year}: query would scan {estimate / 1e9:.1f} GB, over BQ_MAX_BYTES "
            f"({max_bytes / 1e9:.1f} GB)"
        )
    release = runner.table_release(config.table)
    job = runner.run(query.sql, query.params, max_bytes)
    table = job.to_arrow()
    metadata = {
        "year": year,
        "table": config.table,
        "release": release,
        "query": query.sql,
        "parameters": {name: str(value) for name, _, value in query.params},
        "bytes_processed": job.total_bytes_processed,
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    table = table.replace_schema_metadata(
        {**(table.schema.metadata or {}), METADATA_KEY: json.dumps(metadata).encode()}
    )
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="zstd")
    return buffer.getvalue()


def parse_year(body: bytes, year: int) -> ParsedSource:
    """Rows for `raw.climatetrace_voyages` from one archived year of Parquet."""
    table = pq.read_table(io.BytesIO(body))
    raw_metadata = (table.schema.metadata or {}).get(METADATA_KEY)
    if raw_metadata is None:
        raise ClimateTraceError("Parquet file has no shockt metadata")
    metadata = json.loads(raw_metadata)
    if metadata["year"] != year:
        raise ClimateTraceError(f"archived file is for {metadata['year']}, not {year}")
    missing = [c for c in SOURCE_COLUMNS if c not in table.column_names]
    if missing:
        raise ClimateTraceError(f"result is missing columns {missing}")
    rows: list[tuple[object, ...]] = []
    seen: set[tuple[object, object]] = set()
    records = table.select(list(SOURCE_COLUMNS)).to_pylist()
    for record in records:
        start = record["start_date"]
        if not isinstance(start, datetime) or start.year != year:
            raise ClimateTraceError(
                f"voyage {record['asset_identifier']} starts {start}, not in {year}"
            )
        key = (record["asset_identifier"], start)
        if key in seen:
            continue
        seen.add(key)
        rows.append(tuple(record[c] for c in SOURCE_COLUMNS))
    return ParsedSource(
        rows=rows,
        rows_received=len(records),
        source_vintage=f"release {metadata['release']}",
        bytes_processed=metadata.get("bytes_processed"),
    )


def archive_key(year: int) -> str:
    return object_key(DATASET, str(year), f"voyages_{year}.parquet")


def load_year(
    conn: psycopg.Connection,
    archive: Archive,
    config: ClimateTraceConfig,
    year: int,
    fetch: Callable[[], bytes] | None,
) -> LoadResult:
    """Archive one year's result (or reuse the archived copy when `fetch` is None); load it."""
    return load_partition(
        conn,
        archive,
        TARGET,
        str(year),
        key=archive_key(year),
        content_type="application/vnd.apache.parquet",
        params={
            "year": year,
            "origin_iso3": config.origin_iso3,
            "destination_iso3": config.destination_iso3,
        },
        obtain=fetch,
        parse=lambda body: parse_year(body, year),
    )


class GoogleBigQueryRunner:
    """`BigQueryRunner` over the google-cloud-bigquery client, billed to the caller's project."""

    def __init__(self, project: str) -> None:
        self._client = bigquery.Client(project=project)

    def dry_run(self, sql: str, params: Sequence[tuple[str, str, object]]) -> int:
        config = bigquery.QueryJobConfig(
            query_parameters=_query_parameters(params), dry_run=True, use_query_cache=False
        )
        return int(self._client.query(sql, job_config=config).total_bytes_processed or 0)

    def run(self, sql: str, params: Sequence[tuple[str, str, object]], max_bytes: int) -> QueryJob:
        config = bigquery.QueryJobConfig(
            query_parameters=_query_parameters(params), maximum_bytes_billed=max_bytes
        )
        job = self._client.query(sql, job_config=config)
        job.result()
        return _FinishedJob(job)

    def table_release(self, table: str) -> str:
        labels = self._client.get_table(table).labels or {}
        return labels.get("release", "unlabelled")


class _FinishedJob:
    def __init__(self, job: bigquery.QueryJob) -> None:
        self._job = job

    @property
    def total_bytes_processed(self) -> int | None:
        return self._job.total_bytes_processed

    def to_arrow(self) -> pa.Table:
        # The Storage Read API is billed separately; read results through the REST API instead.
        return self._job.to_arrow(create_bqstorage_client=False)


def _query_parameters(
    params: Sequence[tuple[str, str, object]],
) -> list[bigquery.ScalarQueryParameter | bigquery.ArrayQueryParameter]:
    result: list[bigquery.ScalarQueryParameter | bigquery.ArrayQueryParameter] = []
    for name, kind, value in params:
        if kind.startswith("ARRAY<"):
            result.append(bigquery.ArrayQueryParameter(name, kind[6:-1], value))
        else:
            result.append(bigquery.ScalarQueryParameter(name, kind, value))
    return result
