"""raw table for the OECD maritime transport CO2 emissions

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-29

Monthly CO2 emissions of large vessels by the country of the operating company, one SDMX-CSV
response per year. Columns keep the source's dimension names.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE raw.oecd_maritime_emissions (
          load_id       uuid             NOT NULL REFERENCES raw.load_manifest (load_id),
          time_period   text             NOT NULL,
          ref_area      text             NOT NULL,
          measure       text             NOT NULL,
          unit_measure  text             NOT NULL,
          adjustment    text             NOT NULL,
          pollutant     text             NOT NULL,
          source        text             NOT NULL,
          vessel        text             NOT NULL,
          obs_status    text,
          unit_mult     smallint         NOT NULL,
          obs_value     double precision,
          PRIMARY KEY (
            load_id, time_period, ref_area, measure, unit_measure,
            adjustment, pollutant, source, vessel
          )
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE raw.oecd_maritime_emissions IS "
        "'OECD maritime CO2 emissions by operator country; ref_area also holds the aggregates "
        "W and OECD, the only rows with a ship-type breakdown in vessel'"
    )
    op.execute(
        "COMMENT ON COLUMN raw.oecd_maritime_emissions.unit_mult IS "
        "'Power of ten by which obs_value is multiplied to give unit_measure'"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON raw.oecd_maritime_emissions TO shockt_ingest"
    )
    op.execute("GRANT SELECT ON raw.oecd_maritime_emissions TO shockt_transform, shockt_analyst")


def downgrade() -> None:
    op.execute("DROP TABLE raw.oecd_maritime_emissions")
