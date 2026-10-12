import json
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
import yaml
from alembic import command
from alembic.config import Config
from testcontainers.community.postgres import PostgresContainer

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


def postgres_image() -> str:
    """The Postgres image `compose.yaml` runs for development, so tests use the same version."""
    compose = yaml.safe_load((PROJECT_ROOT / "compose.yaml").read_text())
    return str(compose["services"]["postgres"]["image"])


@pytest.fixture(scope="session")
def migrated_database_url() -> Iterator[str]:
    """A throwaway Postgres container for the test session, with all migrations applied.
    Integration tests need Docker running; they fail without it rather than skip."""
    with PostgresContainer(postgres_image(), driver=None) as postgres:
        url = postgres.get_connection_url()
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        config.attributes["sqlalchemy_url"] = url.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
        command.upgrade(config, "head")
        yield url


@pytest.fixture
def conn(migrated_database_url: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(migrated_database_url, autocommit=True) as connection:
        connection.execute("TRUNCATE raw.load_manifest CASCADE")
        yield connection
