import json

import pytest

from shockt.config import origins_config, transforms_config
from shockt.dbt import connection_env, vars_args
from shockt.settings import Settings


def settings_with(dbt_url: str | None) -> Settings:
    return Settings(database_url="postgresql://unused@localhost/unused", dbt_database_url=dbt_url)


def test_connection_env_splits_a_neon_url() -> None:
    env = connection_env(
        settings_with(
            "postgresql://shockt_transform:p%40ss@ep-x.us-east-2.aws.neon.tech/neondb?sslmode=require"
        )
    )

    assert env == {
        "DBT_HOST": "ep-x.us-east-2.aws.neon.tech",
        "DBT_PORT": "5432",
        "DBT_USER": "shockt_transform",
        "DBT_PASSWORD": "p@ss",
        "DBT_DBNAME": "neondb",
        "DBT_SSLMODE": "require",
    }


def test_connection_env_defaults_sslmode_and_keeps_an_explicit_port() -> None:
    env = connection_env(settings_with("postgresql://shockt:shockt@localhost:6543/shockt"))

    assert env["DBT_PORT"] == "6543"
    assert env["DBT_SSLMODE"] == "prefer"


def test_connection_env_requires_the_url() -> None:
    with pytest.raises(ValueError, match="DBT_DATABASE_URL"):
        connection_env(settings_with(None))


def test_vars_args_pass_transforms_and_origins_as_dbt_vars() -> None:
    args = vars_args(["build"])

    assert args[0] == "--vars"
    assert json.loads(args[1]) == {
        **transforms_config().model_dump(),
        "origins": origins_config().model_dump(),
    }


def test_vars_args_refuse_vars_from_the_command_line() -> None:
    with pytest.raises(ValueError, match="config/"):
        vars_args(["build", "--vars", "{}"])
