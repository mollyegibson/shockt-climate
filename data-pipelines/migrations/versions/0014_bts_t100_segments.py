"""raw table for BTS T-100 International Segment (All Carriers)

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-12

Columns keep the source names. The source repeats some rows exactly, so each row is keyed by its
line in the file.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE raw.bts_t100_segments (
          load_id               uuid              NOT NULL REFERENCES raw.load_manifest (load_id),
          line_number           integer           NOT NULL,
          year                  smallint          NOT NULL,
          month                 smallint          NOT NULL,
          unique_carrier        text              NOT NULL,
          origin_airport_id     integer           NOT NULL,
          origin                text              NOT NULL,
          origin_country        text              NOT NULL,
          origin_wac            integer           NOT NULL,
          dest_airport_id       integer           NOT NULL,
          dest                  text              NOT NULL,
          dest_country          text              NOT NULL,
          dest_wac              integer           NOT NULL,
          aircraft_group        smallint          NOT NULL,
          aircraft_type         smallint          NOT NULL,
          aircraft_config       smallint          NOT NULL,
          class                 text              NOT NULL,
          departures_performed  double precision  NOT NULL,
          freight               double precision  NOT NULL,
          mail                  double precision  NOT NULL,
          distance              double precision  NOT NULL,
          PRIMARY KEY (load_id, line_number)
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE raw.bts_t100_segments IS "
        "'T-100 International Segment (All Carriers): freight and mail in pounds, "
        "distance in miles'"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON raw.bts_t100_segments TO shockt_ingest")
    op.execute("GRANT SELECT ON raw.bts_t100_segments TO shockt_transform, shockt_analyst")


def downgrade() -> None:
    op.execute("DROP TABLE raw.bts_t100_segments")
