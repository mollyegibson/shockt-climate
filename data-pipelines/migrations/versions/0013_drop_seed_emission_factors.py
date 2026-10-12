"""drop raw.seed_emission_factors, left behind when the emission factors moved to loaded workbooks

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-12

dbt doesn't drop a seed's table when the seed file is removed. The factors now come from
raw.uk_ghg_conversion_factors and the EPA tables (migration 0011), and nothing reads this table.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS raw.seed_emission_factors")


def downgrade() -> None:
    """Nothing to restore: the table was a dbt seed, and its seed file no longer exists."""
