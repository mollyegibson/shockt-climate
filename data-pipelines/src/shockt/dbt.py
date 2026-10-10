import os
from urllib.parse import parse_qs, unquote, urlsplit

from dbt.cli.main import dbtRunner

from shockt.settings import PROJECT_ROOT, Settings

DBT_DIR = PROJECT_ROOT / "dbt"


def connection_env(settings: Settings) -> dict[str, str]:
    """`DBT_DATABASE_URL` split into the DBT_* variables `dbt/profiles.yml` reads."""
    if settings.dbt_database_url is None:
        raise ValueError("DBT_DATABASE_URL is not set")
    url = urlsplit(settings.dbt_database_url.get_secret_value())
    if url.hostname is None or url.username is None:
        raise ValueError("DBT_DATABASE_URL must include a host and a user")
    return {
        "DBT_HOST": url.hostname,
        "DBT_PORT": str(url.port or 5432),
        "DBT_USER": unquote(url.username),
        "DBT_PASSWORD": unquote(url.password or ""),
        "DBT_DBNAME": url.path.lstrip("/") or "postgres",
        "DBT_SSLMODE": parse_qs(url.query).get("sslmode", ["prefer"])[0],
    }


def run(settings: Settings, args: list[str]) -> bool:
    """Run one dbt command against this project as the shockt_transform login."""
    os.environ.update(connection_env(settings))
    result = dbtRunner().invoke(
        [*args, "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)]
    )
    return result.success
