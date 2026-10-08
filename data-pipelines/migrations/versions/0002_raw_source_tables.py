"""raw tables for Census, BTS TransBorder and PortWatch

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08

The Climate TRACE voyages table is added in its own migration once its BigQuery schema is
confirmed (plan spike 5).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "census_hs",
    "census_porths",
    "census_statehs",
    "census_state_port",
    "bts_transborder",
    "portwatch_chokepoints",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE raw.census_hs (
          load_id            uuid   NOT NULL REFERENCES raw.load_manifest (load_id),
          time               text   NOT NULL,
          i_commodity        text   NOT NULL,
          i_commodity_sdesc  text,
          cty_code           text   NOT NULL,
          cty_name           text,
          summary_lvl        text,
          gen_val_mo         bigint,
          con_val_mo         bigint,
          air_val_mo         bigint,
          air_wgt_mo         bigint,
          ves_val_mo         bigint,
          ves_wgt_mo         bigint,
          cnt_val_mo         bigint,
          cnt_wgt_mo         bigint,
          gen_qy1_mo         bigint,
          unit_qy1           text,
          gen_qy2_mo         bigint,
          unit_qy2           text,
          last_update        date,
          PRIMARY KEY (load_id, time, i_commodity, cty_code)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE raw.census_porths (
          load_id            uuid   NOT NULL REFERENCES raw.load_manifest (load_id),
          time               text   NOT NULL,
          comm_lvl           text   NOT NULL,
          i_commodity        text   NOT NULL,
          cty_code           text   NOT NULL,
          cty_name           text,
          port               text   NOT NULL,
          port_name          text,
          gen_val_mo         bigint,
          air_val_mo         bigint,
          air_wgt_mo         bigint,
          ves_val_mo         bigint,
          ves_wgt_mo         bigint,
          cnt_val_mo         bigint,
          cnt_wgt_mo         bigint,
          last_update        date,
          PRIMARY KEY (load_id, time, i_commodity, cty_code, port)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE raw.census_statehs (
          load_id            uuid   NOT NULL REFERENCES raw.load_manifest (load_id),
          time               text   NOT NULL,
          comm_lvl           text   NOT NULL,
          i_commodity        text   NOT NULL,
          cty_code           text   NOT NULL,
          cty_name           text,
          state              text   NOT NULL,
          gen_val_mo         bigint,
          con_val_mo         bigint,
          air_val_mo         bigint,
          air_wgt_mo         bigint,
          ves_val_mo         bigint,
          ves_wgt_mo         bigint,
          cnt_val_mo         bigint,
          cnt_wgt_mo         bigint,
          last_update        date,
          PRIMARY KEY (load_id, time, i_commodity, cty_code, state)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE raw.census_state_port (
          load_id            uuid     NOT NULL REFERENCES raw.load_manifest (load_id),
          stat_year          smallint NOT NULL,
          time_period        text     NOT NULL,
          state              text     NOT NULL,
          district_unlading  text     NOT NULL,
          port_unlading      text     NOT NULL,
          district_entry     text     NOT NULL,
          port_entry         text     NOT NULL,
          country            text     NOT NULL,
          value              bigint,
          air_val            bigint,
          air_swt            bigint,
          ves_val            bigint,
          cnt_val            bigint,
          ves_swt            bigint,
          cnt_swt            bigint,
          PRIMARY KEY (load_id, state, district_unlading, port_unlading,
                       district_entry, port_entry, country)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE raw.bts_transborder (
          load_id         uuid     NOT NULL REFERENCES raw.load_manifest (load_id),
          source_table    text     NOT NULL CHECK (source_table IN ('dot2', 'dot3')),
          year            smallint NOT NULL,
          month           smallint NOT NULL,
          trdtype         smallint NOT NULL,
          usastate        text,
          depe            text,
          commodity2      text     NOT NULL,
          disagmot        smallint NOT NULL,
          mexstate        text,
          country         text     NOT NULL,
          value           bigint,
          shipwt          bigint,
          freightcharges  bigint,
          df              smallint,
          contcode        text
        )
        """
    )
    op.execute("CREATE INDEX bts_transborder_load_id ON raw.bts_transborder (load_id)")
    op.execute(
        """
        CREATE TABLE raw.portwatch_chokepoints (
          load_id                 uuid   NOT NULL REFERENCES raw.load_manifest (load_id),
          object_id               bigint NOT NULL,
          date                    date   NOT NULL,
          portid                  text   NOT NULL,
          portname                text,
          n_container             integer,
          n_dry_bulk              integer,
          n_general_cargo         integer,
          n_roro                  integer,
          n_tanker                integer,
          n_cargo                 integer,
          n_total                 integer,
          capacity_container      bigint,
          capacity_dry_bulk       bigint,
          capacity_general_cargo  bigint,
          capacity_roro           bigint,
          capacity_tanker         bigint,
          capacity_cargo          bigint,
          capacity                bigint,
          PRIMARY KEY (load_id, portid, date)
        )
        """
    )
    op.execute("COMMENT ON COLUMN raw.census_hs.air_wgt_mo IS 'Air shipping weight, kg'")
    op.execute(
        "COMMENT ON COLUMN raw.census_hs.cnt_wgt_mo IS "
        "'Containerized vessel shipping weight, kg; a subset of ves_wgt_mo'"
    )
    op.execute(
        "COMMENT ON COLUMN raw.census_statehs.state IS "
        "'State of destination as known at entry filing; XX = unidentified'"
    )
    op.execute(
        "COMMENT ON COLUMN raw.bts_transborder.disagmot IS "
        "'1 vessel, 3 air, 4 mail, 5 truck, 6 rail, 7 pipeline, 8 other, 9 foreign trade zone'"
    )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE raw.{table}")
