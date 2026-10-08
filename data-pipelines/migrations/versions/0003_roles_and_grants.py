"""group roles, core schemas and grants

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-08

Creates NOLOGIN group roles. Login users are created separately (Neon console or
CREATE ROLE ... LOGIN) and granted membership, e.g. `GRANT shockt_analyst TO alice`.

Tables that dbt creates in `core`, `core_staging` and as `raw.seed_*` are owned by the
user dbt runs as, so their SELECT grants come from dbt's `grants` config, not from here.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = ("shockt_ingest", "shockt_transform", "shockt_analyst", "shockt_app")


def upgrade() -> None:
    for role in ROLES:
        op.execute(
            f"""
            DO $$
            BEGIN
              IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} NOLOGIN;
              END IF;
            END
            $$
            """
        )

    op.execute("CREATE SCHEMA IF NOT EXISTS core")
    op.execute("CREATE SCHEMA IF NOT EXISTS core_staging")

    op.execute("GRANT USAGE ON SCHEMA raw TO shockt_ingest, shockt_transform, shockt_analyst")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA raw TO shockt_ingest")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA raw TO shockt_transform, shockt_analyst")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA raw "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO shockt_ingest"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA raw "
        "GRANT SELECT ON TABLES TO shockt_transform, shockt_analyst"
    )
    # dbt seeds load into raw as raw.seed_*.
    op.execute("GRANT CREATE ON SCHEMA raw TO shockt_transform")

    op.execute("GRANT USAGE, CREATE ON SCHEMA core, core_staging TO shockt_transform")
    op.execute("GRANT USAGE ON SCHEMA core TO shockt_analyst, shockt_app")
    op.execute("GRANT USAGE ON SCHEMA core_staging TO shockt_analyst")


def downgrade() -> None:
    for role in ROLES:
        op.execute(
            f"""
            DO $$
            BEGIN
              IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                EXECUTE 'DROP OWNED BY {role}';
                EXECUTE 'DROP ROLE {role}';
              END IF;
            END
            $$
            """
        )
    op.execute("DROP SCHEMA IF EXISTS core_staging")
    op.execute("DROP SCHEMA IF EXISTS core")
