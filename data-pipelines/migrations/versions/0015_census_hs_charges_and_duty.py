"""census_hs: import charges by mode and duty

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-13

The `hs` endpoint reports charges (freight, insurance and other costs to the first US port) by
mode, and the dutiable value and calculated duty of imports for consumption. Rows loaded before
these fields were requested keep nulls until their partition is fetched again.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = ("gen_cha_mo", "air_cha_mo", "ves_cha_mo", "cnt_cha_mo", "dut_val_mo", "cal_dut_mo")


def upgrade() -> None:
    op.execute(
        "ALTER TABLE raw.census_hs "
        + ", ".join(f"ADD COLUMN {column} bigint" for column in COLUMNS)
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE raw.census_hs " + ", ".join(f"DROP COLUMN {column}" for column in COLUMNS)
    )
