"""raw table for the EU CBAM default values

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-29

The definitive-period default values of Annex I, one row per country and CN code, loaded whole.
Columns keep the source names; a cell the source fills with "-", "N/A" or "see below" is null
with the source's text in the matching note column.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE raw.cbam_default_values (
          load_id                  uuid             NOT NULL REFERENCES raw.load_manifest (load_id),
          country                  text             NOT NULL,
          sector                   text             NOT NULL,
          cn_code                  text             NOT NULL,
          description              text,
          direct_emissions         double precision,
          direct_emissions_note    text,
          indirect_emissions       double precision,
          indirect_emissions_note  text,
          total_emissions          double precision,
          total_emissions_note     text,
          production_route         text,
          PRIMARY KEY (load_id, country, cn_code)
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE raw.cbam_default_values IS "
        "'CBAM default values in tCO2eq per tonne of good, by exporting country and CN code'"
    )
    op.execute(
        "COMMENT ON COLUMN raw.cbam_default_values.production_route IS "
        "'The route code determining the CBAM benchmark, e.g. (A); blank cells are null'"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON raw.cbam_default_values TO shockt_ingest")
    op.execute("GRANT SELECT ON raw.cbam_default_values TO shockt_transform, shockt_analyst")


def downgrade() -> None:
    op.execute("DROP TABLE raw.cbam_default_values")
