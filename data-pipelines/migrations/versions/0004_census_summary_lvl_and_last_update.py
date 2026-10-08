"""census: summary_lvl on port and state tables, last_update as text

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-08

The Census API returns SUMMARY_LVL on the port and state endpoints too, and returns
LAST_UPDATE as "0" rather than a date.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CENSUS_TABLES = ("census_hs", "census_porths", "census_statehs")


def upgrade() -> None:
    for table in ("census_porths", "census_statehs"):
        op.execute(f"ALTER TABLE raw.{table} ADD COLUMN summary_lvl text")
    for table in CENSUS_TABLES:
        op.execute(f"ALTER TABLE raw.{table} ALTER COLUMN last_update TYPE text")


def downgrade() -> None:
    for table in CENSUS_TABLES:
        op.execute(
            f"ALTER TABLE raw.{table} ALTER COLUMN last_update TYPE date "
            "USING NULLIF(last_update, '0')::date"
        )
    for table in ("census_porths", "census_statehs"):
        op.execute(f"ALTER TABLE raw.{table} DROP COLUMN summary_lvl")
