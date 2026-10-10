"""bts_transborder: freight_charges column named as in the source files

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-09

The TransBorder raw data files name the column FREIGHT_CHARGES.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE raw.bts_transborder RENAME COLUMN freightcharges TO freight_charges")


def downgrade() -> None:
    op.execute("ALTER TABLE raw.bts_transborder RENAME COLUMN freight_charges TO freightcharges")
