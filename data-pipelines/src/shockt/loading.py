from collections.abc import Callable, Sequence
from dataclasses import dataclass
from uuid import UUID

import psycopg

from shockt.archive import Archive, sha256_hex
from shockt.db import copy_rows
from shockt.manifest import LoadResult, LoadSource, record_failure, run_load


@dataclass(frozen=True)
class ParsedSource:
    rows: Sequence[tuple[object, ...]]
    """Rows kept after filtering, in the target table's column order without load_id."""
    rows_received: int
    source_vintage: str | None
    bytes_processed: int | None = None


@dataclass(frozen=True)
class Target:
    dataset: str
    table: str
    columns: Sequence[str]
    """Target columns, starting with load_id."""


def load_partition(
    conn: psycopg.Connection,
    archive: Archive,
    target: Target,
    partition_key: str,
    *,
    key: str,
    content_type: str,
    params: dict[str, object],
    obtain: Callable[[], bytes] | None,
    parse: Callable[[bytes], ParsedSource],
) -> LoadResult:
    """Archive a source file, parse the archived bytes and load them as one partition.

    `obtain` returns the file to archive; with `obtain=None` the file is read back from the
    archive at `key` instead. A failure is recorded in the manifest and re-raised.
    """
    source = LoadSource(params=params, source_vintage=None, object_key=None, object_sha256=None)
    try:
        if obtain is None:
            body = archive.get(key)
            digest = sha256_hex(body)
            params["from_archive"] = True
        else:
            body = obtain()
            digest = archive.put(key, body, content_type)
        parsed = parse(body)
        params["rows_received"] = parsed.rows_received
        source = LoadSource(
            params=params,
            source_vintage=parsed.source_vintage,
            object_key=key,
            object_sha256=digest,
            bytes_processed=parsed.bytes_processed,
        )

        def write_rows(c: psycopg.Connection, load_id: UUID) -> int:
            return copy_rows(
                c, target.table, target.columns, ((load_id, *row) for row in parsed.rows)
            )

        return run_load(
            conn,
            dataset=target.dataset,
            partition_key=partition_key,
            table=target.table,
            source=source,
            write_rows=write_rows,
        )
    except Exception as exc:
        if conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
            conn.rollback()
        record_failure(
            conn,
            dataset=target.dataset,
            partition_key=partition_key,
            source=source,
            error=f"{type(exc).__name__}: {exc}",
        )
        raise
