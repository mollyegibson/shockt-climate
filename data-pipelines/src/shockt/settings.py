from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime settings from `data-pipelines/.env`, falling back to environment variables.

    `.env` takes priority so that variables a developer's shell exports for other work
    (e.g. `DATABASE_URL`) don't silently point this project at the wrong database.
    """

    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return init_settings, dotenv_settings, env_settings, file_secret_settings

    database_url: SecretStr
    migrations_database_url: SecretStr | None = None
    dbt_database_url: SecretStr | None = None
    neon_s3_endpoint_url: str | None = None
    neon_s3_access_key_id: str | None = None
    neon_s3_secret_access_key: SecretStr | None = None
    neon_s3_region: str = "us-east-2"
    archive_bucket: str = "shockt-raw-archive"
    census_api_key: SecretStr | None = None
    ors_api_key: SecretStr | None = None
    gcp_project_id: str | None = None
    bq_max_bytes: int = Field(default=100_000_000_000, gt=0)

    def migrations_sqlalchemy_url(self) -> str:
        """The migrations URL with the psycopg 3 driver named, as SQLAlchemy and Alembic expect."""
        if self.migrations_database_url is None:
            raise ValueError("MIGRATIONS_DATABASE_URL is not set; migrations run as the owner.")
        url = self.migrations_database_url.get_secret_value()
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url


def get_settings() -> Settings:
    return Settings.model_validate({})
