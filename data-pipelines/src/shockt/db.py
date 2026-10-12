from collections.abc import Iterable, Sequence

import psycopg
from psycopg import sql

from shockt.settings import Settings


def connect(settings: Settings) -> psycopg.Connection:
    """Connect as the ingest login (`DATABASE_URL`), in autocommit mode so each load's
    transaction block commits on its own."""
    return psycopg.connect(settings.database_url.get_secret_value(), autocommit=True)


def copy_rows(
    conn: psycopg.Connection,
    table: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[object]],
) -> int:
    """Bulk-insert `rows` into `raw.<table>` with COPY and return the number of rows written."""
    statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier("raw", table),
        sql.SQL(", ").join(sql.Identifier(c) for c in columns),
    )
    count = 0
    with conn.cursor() as cur, cur.copy(statement) as copy:
        for row in rows:
            copy.write_row(row)
            count += 1
    return count
