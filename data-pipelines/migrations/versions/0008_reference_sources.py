"""raw tables for OurAirports, GeoNames cities and BTS Border Crossing Entry Data

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-12

Reference datasets used to place nodes (plan section 6.2). Columns keep the source names.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("ourairports_airports", "geonames_cities", "bts_border_crossings")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE raw.ourairports_airports (
          load_id            uuid             NOT NULL REFERENCES raw.load_manifest (load_id),
          id                 bigint           NOT NULL,
          ident              text,
          type               text,
          name               text,
          latitude_deg       double precision,
          longitude_deg      double precision,
          elevation_ft       integer,
          continent          text,
          iso_country        text,
          iso_region         text,
          municipality       text,
          scheduled_service  text,
          icao_code          text,
          iata_code          text,
          gps_code           text,
          local_code         text,
          PRIMARY KEY (load_id, id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE raw.geonames_cities (
          load_id            uuid             NOT NULL REFERENCES raw.load_manifest (load_id),
          geonameid          bigint           NOT NULL,
          name               text,
          asciiname          text,
          latitude           double precision,
          longitude          double precision,
          feature_class      text,
          feature_code       text,
          country_code       text,
          admin1_code        text,
          admin2_code        text,
          population         bigint,
          timezone           text,
          modification_date  date,
          PRIMARY KEY (load_id, geonameid)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE raw.bts_border_crossings (
          load_id    uuid             NOT NULL REFERENCES raw.load_manifest (load_id),
          port_name  text,
          state      text,
          port_code  text             NOT NULL,
          border     text,
          date       date             NOT NULL,
          measure    text             NOT NULL,
          value      bigint,
          latitude   double precision,
          longitude  double precision,
          PRIMARY KEY (load_id, port_code, date, measure)
        )
        """
    )
    for table in TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON raw.{table} TO shockt_ingest")
        op.execute(f"GRANT SELECT ON raw.{table} TO shockt_transform, shockt_analyst")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE raw.{table}")
