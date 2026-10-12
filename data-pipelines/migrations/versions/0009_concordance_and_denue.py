"""raw tables for the Census import concordance and INEGI DENUE establishments

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-12

The concordance maps HS-10 codes to NAICS industries; DENUE places Mexican manufacturing
establishments in those industries (plan section 6.2). Columns keep the source names.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("census_import_concordance", "denue_establishments")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE raw.census_import_concordance (
          load_id     uuid     NOT NULL REFERENCES raw.load_manifest (load_id),
          year        smallint NOT NULL,
          commodity   text     NOT NULL,
          descriptn   text,
          abbreviatn  text,
          unit_qy1    text,
          unit_qy2    text,
          sitc        text,
          end_use     text,
          naics       text,
          usda        text,
          hitech      text,
          PRIMARY KEY (load_id, commodity)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE raw.denue_establishments (
          load_id     uuid             NOT NULL REFERENCES raw.load_manifest (load_id),
          id          bigint           NOT NULL,
          clee        text,
          nom_estab   text,
          raz_social  text,
          codigo_act  text             NOT NULL,
          nombre_act  text,
          per_ocu     text,
          cve_ent     text,
          entidad     text,
          cve_mun     text,
          municipio   text,
          cve_loc     text,
          localidad   text,
          tipounieco  text,
          latitud     double precision,
          longitud    double precision,
          fecha_alta  text,
          PRIMARY KEY (load_id, id)
        )
        """
    )
    op.execute(
        "COMMENT ON COLUMN raw.denue_establishments.per_ocu IS "
        "'Employee-size band, e.g. 251 y más personas'"
    )
    for table in TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON raw.{table} TO shockt_ingest")
        op.execute(f"GRANT SELECT ON raw.{table} TO shockt_transform, shockt_analyst")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE raw.{table}")
