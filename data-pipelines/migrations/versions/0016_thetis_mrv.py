"""EMSA THETIS-MRV annual per-ship fuel and emissions

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-23

Per-ship fuel consumption and CO₂ emissions reported under EU MRV Regulation 2015/757. Each
reporting year is one `latest` partition. The 2024+ schema adds CH₄, N₂O and CO₂eq columns;
`total_co2eq_mt` is null for earlier years.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE raw.thetis_mrv (
            load_id         uuid    NOT NULL
                            REFERENCES raw.load_manifest(load_id),
            reporting_year               smallint         NOT NULL,
            report_type                  text             NOT NULL,
            imo_number                   text             NOT NULL,
            ship_name                    text,
            ship_type                    text,
            port_of_registry             text,
            home_port                    text,
            ice_class                    text,
            doc_issue_date               date,
            doc_expiry_date              date,
            total_fuel_consumption_mt    double precision,
            total_co2_mt                 double precision,
            total_co2eq_mt               double precision,
            time_at_sea_hours            double precision,
            fuel_per_distance_kg_nm      double precision,
            co2_per_distance_kg_nm       double precision,
            co2_per_transport_work_mass  double precision,
            PRIMARY KEY (load_id, reporting_year, imo_number, report_type)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE raw.thetis_mrv")
