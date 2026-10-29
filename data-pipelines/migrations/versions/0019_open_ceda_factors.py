"""raw table for the Open CEDA emission factors

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-29

The `GHG_t_Raw` sheet of the Open CEDA workbook, one row per country and industry. The factors
are in the sheet's own price year, price type and currency, which are kept on every row.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE raw.open_ceda_factors (
          load_id       uuid             NOT NULL REFERENCES raw.load_manifest (load_id),
          country_code  text             NOT NULL,
          country       text             NOT NULL,
          sector_code   text             NOT NULL,
          sector_name   text             NOT NULL,
          unit          text             NOT NULL,
          price_year    smallint         NOT NULL,
          price_type    text             NOT NULL,
          factor        double precision,
          PRIMARY KEY (load_id, country_code, sector_code)
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE raw.open_ceda_factors IS "
        "'Open CEDA total upstream emissions per unit of output, by country and industry'"
    )
    op.execute(
        "COMMENT ON COLUMN raw.open_ceda_factors.unit IS 'The sheet''s unit, e.g. kgCO2e/US Dollar'"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON raw.open_ceda_factors TO shockt_ingest")
    op.execute("GRANT SELECT ON raw.open_ceda_factors TO shockt_transform, shockt_analyst")


def downgrade() -> None:
    op.execute("DROP TABLE raw.open_ceda_factors")
