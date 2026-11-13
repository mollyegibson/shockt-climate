"""Node search and country listing endpoints."""

import psycopg
from fastapi import APIRouter, Query
from psycopg.rows import tuple_row

from shockt_api.db import list_countries, search_nodes
from shockt_api.schemas import CountryResult, NodeResult

router = APIRouter()


def _get_conn() -> psycopg.Connection[tuple]:
    """Placeholder replaced by main.py lifespan."""
    raise RuntimeError("database connection not initialized")


def init_nodes(database_url: str) -> None:
    """Inject the database URL for per-request connections."""
    global _database_url
    _database_url = database_url

    global _get_conn

    def _get_conn() -> psycopg.Connection[tuple]:
        return psycopg.connect(_database_url, row_factory=tuple_row)


@router.get("/nodes/search")
def node_search(
    q: str,
    kind: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[NodeResult]:
    with _get_conn() as conn:
        rows = search_nodes(conn, q, kind=kind, limit=limit)
    return [NodeResult(**r) for r in rows]


@router.get("/countries")
def countries() -> list[CountryResult]:
    with _get_conn() as conn:
        rows = list_countries(conn)
    return [CountryResult(**r) for r in rows]
