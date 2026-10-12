"""raw tables for the UK GHG conversion factors and the EPA GHG Emission Factors Hub

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-12

Both workbooks are loaded whole (plan section 6.1). Columns keep the source names.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("uk_ghg_conversion_factors", "epa_ghg_transport_factors", "epa_ghg_gwp")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE raw.uk_ghg_conversion_factors (
          load_id      uuid             NOT NULL REFERENCES raw.load_manifest (load_id),
          id           text             NOT NULL,
          scope        text,
          level_1      text             NOT NULL,
          level_2      text,
          level_3      text,
          level_4      text,
          column_text  text,
          uom          text,
          ghg_unit     text,
          factor       double precision,
          PRIMARY KEY (load_id, id)
        )
        """
    )
    op.execute(
        "COMMENT ON COLUMN raw.uk_ghg_conversion_factors.factor IS "
        "'The \"GHG Conversion Factor <year>\" column; blank cells are null'"
    )
    op.execute(
        """
        CREATE TABLE raw.epa_ghg_transport_factors (
          load_id       uuid     NOT NULL REFERENCES raw.load_manifest (load_id),
          vehicle_type  text     NOT NULL,
          co2_factor    numeric,
          ch4_factor    numeric,
          n2o_factor    numeric,
          units         text     NOT NULL,
          PRIMARY KEY (load_id, vehicle_type, units)
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE raw.epa_ghg_transport_factors IS "
        "'EPA Hub Table 8: kg CO2, g CH4 and g N2O per unit, combustion only'"
    )
    op.execute(
        """
        CREATE TABLE raw.epa_ghg_gwp (
          load_id           uuid     NOT NULL REFERENCES raw.load_manifest (load_id),
          common_name       text,
          chemical_formula  text     NOT NULL,
          gwp_100yr         numeric,
          PRIMARY KEY (load_id, chemical_formula)
        )
        """
    )
    op.execute("COMMENT ON TABLE raw.epa_ghg_gwp IS 'EPA Hub Table 11: 100-year GWPs'")
    for table in TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON raw.{table} TO shockt_ingest")
        op.execute(f"GRANT SELECT ON raw.{table} TO shockt_transform, shockt_analyst")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE raw.{table}")
