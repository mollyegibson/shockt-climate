import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import cache
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from shockt.settings import PROJECT_ROOT


@dataclass(frozen=True)
class LoadResult:
    load_id: UUID
    row_count: int
    superseded_load_id: UUID | None


@dataclass(frozen=True)
class LoadSource:
    """What a load was built from: its request parameters, vintage and archived file."""

    params: Mapping[str, object]
    source_vintage: str | None
    object_key: str | None
    object_sha256: str | None
    bytes_processed: int | None = None
    """BigQuery bytes scanned to produce the source, when it came from a query."""


@cache
def code_version() -> str:
    """The current git commit, suffixed with `-dirty` when the working tree has changes."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return f"{commit}-dirty" if dirty else commit


def succeeded_partitions(conn: psycopg.Connection, dataset: str) -> set[str]:
    rows = conn.execute(
        "SELECT partition_key FROM raw.load_manifest WHERE dataset = %s AND status = 'succeeded'",
        (dataset,),
    ).fetchall()
    return {row[0] for row in rows}


def archived_partitions(conn: psycopg.Connection, dataset: str) -> set[str]:
    """Partitions with a file in the archive, from any load that got as far as archiving it."""
    rows = conn.execute(
        "SELECT DISTINCT partition_key FROM raw.load_manifest "
        "WHERE dataset = %s AND object_key IS NOT NULL",
        (dataset,),
    ).fetchall()
    return {row[0] for row in rows}


def run_load(
    conn: psycopg.Connection,
    *,
    dataset: str,
    partition_key: str,
    table: str,
    source: LoadSource,
    write_rows: Callable[[psycopg.Connection, UUID], int],
) -> LoadResult:
    """Write one partition and its manifest row in a single transaction.

    `write_rows` inserts the partition's rows tagged with the new load_id. If the partition
    already has a succeeded load, that load is marked superseded and its rows are deleted.
    """
    with conn.transaction():
        load_id = _insert_manifest(conn, dataset, partition_key, source, status="running")
        row_count = write_rows(conn, load_id)
        previous = conn.execute(
            "SELECT load_id FROM raw.load_manifest "
            "WHERE dataset = %s AND partition_key = %s AND status = 'succeeded' FOR UPDATE",
            (dataset, partition_key),
        ).fetchone()
        previous_id: UUID | None = previous[0] if previous else None
        if previous_id is not None:
            conn.execute(
                sql.SQL("DELETE FROM {} WHERE load_id = %s").format(sql.Identifier("raw", table)),
                (previous_id,),
            )
            conn.execute(
                "UPDATE raw.load_manifest SET status = 'superseded', superseded_by = %s "
                "WHERE load_id = %s",
                (load_id, previous_id),
            )
        conn.execute(
            "UPDATE raw.load_manifest "
            "SET status = 'succeeded', row_count = %s, finished_at = now() WHERE load_id = %s",
            (row_count, load_id),
        )
    return LoadResult(load_id=load_id, row_count=row_count, superseded_load_id=previous_id)


def record_failure(
    conn: psycopg.Connection,
    *,
    dataset: str,
    partition_key: str,
    source: LoadSource,
    error: str,
) -> UUID:
    """Record a failed load in its own transaction, after the load's transaction rolled back."""
    with conn.transaction():
        load_id = _insert_manifest(conn, dataset, partition_key, source, status="failed")
        conn.execute(
            "UPDATE raw.load_manifest SET error = %s, finished_at = now() WHERE load_id = %s",
            (error, load_id),
        )
    return load_id


def _insert_manifest(
    conn: psycopg.Connection,
    dataset: str,
    partition_key: str,
    source: LoadSource,
    *,
    status: str,
) -> UUID:
    row = conn.execute(
        "INSERT INTO raw.load_manifest "
        "(dataset, partition_key, params, source_vintage, status, object_key, object_sha256, "
        "bytes_processed, code_version) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING load_id",
        (
            dataset,
            partition_key,
            Jsonb(dict(source.params)),
            source.source_vintage,
            status,
            source.object_key,
            source.object_sha256,
            source.bytes_processed,
            code_version(),
        ),
    ).fetchone()
    if row is None:
        raise RuntimeError("INSERT ... RETURNING returned no row")
    return row[0]
