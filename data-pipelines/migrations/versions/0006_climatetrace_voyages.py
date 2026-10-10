"""raw table for Climate TRACE ship voyages

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-09

Columns keep the BigQuery source names, including the generic other* fields; their meanings
were established from sample voyages (plan section 5.7) and are applied in staging.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE raw.climatetrace_voyages (
          load_id                    uuid        NOT NULL REFERENCES raw.load_manifest (load_id),
          start_date                 timestamptz NOT NULL,
          end_date                   timestamptz,
          asset_identifier           text        NOT NULL,
          model_number               text,
          asset_name                 text,
          iso3_country               text,
          type                       text,
          capacity                   double precision,
          capacity_factor            double precision,
          activity                   double precision,
          co2_emissions_factor       double precision,
          co2_emissions              double precision,
          total_co2e_100yrgwp        double precision,
          other1                     text,
          other2                     text,
          other3                     text,
          other4                     text,
          other5                     text,
          other6                     text,
          other7                     text,
          other8                     boolean,
          other11                    double precision,
          other12                    double precision,
          original_inventory_sector  text,
          PRIMARY KEY (load_id, asset_identifier, start_date)
        )
        """
    )
    for column, comment in (
        ("activity", "Distance sailed, nautical miles"),
        ("co2_emissions_factor", "t CO2 per nautical mile"),
        ("other1", "Voyage duration, d.hh:mm:ss"),
        ("other2", "Start port name"),
        ("other3", "End port name"),
        ("other4", "Start port country, ISO3"),
        ("other5", "End port country, ISO3"),
        ("other6", "Start port ID"),
        ("other7", "End port ID"),
        ("other8", "International voyage flag (inferred)"),
        ("other11", "Deadweight tonnage (inferred, unconfirmed)"),
    ):
        op.execute(f"COMMENT ON COLUMN raw.climatetrace_voyages.{column} IS '{comment}'")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON raw.climatetrace_voyages TO shockt_ingest")
    op.execute("GRANT SELECT ON raw.climatetrace_voyages TO shockt_transform, shockt_analyst")


def downgrade() -> None:
    op.execute("DROP TABLE raw.climatetrace_voyages")
