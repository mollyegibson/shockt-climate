import json
import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from shockt.archive import sha256_hex

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests" / "fixtures"


def census_fixture(endpoint: str) -> list[list[str]]:
    return json.loads((FIXTURES / f"census_{endpoint}_2024-12.json").read_text())


class MemoryArchive:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, body: bytes, content_type: str) -> str:
        self.objects[key] = body
        return sha256_hex(body)

    def get(self, key: str) -> bytes:
        return self.objects[key]


@pytest.fixture
def memory_archive() -> MemoryArchive:
    return MemoryArchive()


@pytest.fixture(scope="session")
def migrated_database_url() -> str:
    """A database with all migrations applied. Integration tests need TEST_DATABASE_URL, a
    superuser URL for a throwaway database; they're skipped without it."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.attributes["sqlalchemy_url"] = url.replace("postgresql://", "postgresql+psycopg://", 1)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    return url


@pytest.fixture
def conn(migrated_database_url: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(migrated_database_url) as connection:
        connection.execute("TRUNCATE raw.load_manifest CASCADE")
        connection.commit()
        yield connection
