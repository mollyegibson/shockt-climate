"""Eurostat Comext DS-059334: extra-EU trade by mode of transport

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-23

Monthly EU imports from extra-EU partners by HS-6 product code and mode of transport. Each
partition is one month × HS-6 code, with all reporters, partners and transport modes in one
SDMX-CSV request.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE raw.comext_trade (
            load_id         uuid    NOT NULL REFERENCES raw.load_manifest(load_id),
            time_period     text    NOT NULL,
            reporter        text    NOT NULL,
            partner         text    NOT NULL,
            product         text    NOT NULL,
            flow            text    NOT NULL,
            transport_mode  text    NOT NULL,
            indicator       text    NOT NULL,
            obs_value       numeric,
            PRIMARY KEY (
                load_id, time_period, reporter, partner,
                product, flow, transport_mode, indicator
            )
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE raw.comext_trade")
