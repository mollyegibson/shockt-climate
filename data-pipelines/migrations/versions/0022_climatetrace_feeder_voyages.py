"""raw table for Climate TRACE feeder voyages

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-04

Voyages from the feeder origins (origins whose US-bound cargo transships at a hub) to other
countries: the first leg of a two-part sea route. Same columns, keys and comments as
`raw.climatetrace_voyages`.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE raw.climatetrace_feeder_voyages (LIKE raw.climatetrace_voyages INCLUDING ALL)"
    )
    op.execute(
        "ALTER TABLE raw.climatetrace_feeder_voyages ADD FOREIGN KEY (load_id) "
        "REFERENCES raw.load_manifest (load_id)"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON raw.climatetrace_feeder_voyages TO shockt_ingest"
    )
    op.execute(
        "GRANT SELECT ON raw.climatetrace_feeder_voyages TO shockt_transform, shockt_analyst"
    )


def downgrade() -> None:
    op.execute("DROP TABLE raw.climatetrace_feeder_voyages")
