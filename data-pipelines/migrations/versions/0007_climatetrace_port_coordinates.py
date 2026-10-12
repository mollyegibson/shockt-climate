"""climatetrace_voyages: start and end port coordinates

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-12

The source `location` column is a two-point line from the start port to the end port; the
loader extracts its end points so ports can be placed and classified without a geometry type.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = ("start_lon", "start_lat", "end_lon", "end_lat")


def upgrade() -> None:
    for column in COLUMNS:
        op.execute(f"ALTER TABLE raw.climatetrace_voyages ADD COLUMN {column} double precision")
    op.execute(
        "COMMENT ON COLUMN raw.climatetrace_voyages.start_lon IS "
        "'Start port longitude: ST_X(ST_STARTPOINT(location)) in the source'"
    )
    op.execute(
        "COMMENT ON COLUMN raw.climatetrace_voyages.end_lon IS "
        "'End port longitude: ST_X(ST_ENDPOINT(location)) in the source'"
    )


def downgrade() -> None:
    for column in COLUMNS:
        op.execute(f"ALTER TABLE raw.climatetrace_voyages DROP COLUMN {column}")
