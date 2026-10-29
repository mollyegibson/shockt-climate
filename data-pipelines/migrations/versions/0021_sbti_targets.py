"""raw tables for the SBTi Target Dashboard downloads

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-29

The by-company and by-target workbooks, loaded whole. Columns keep the workbook's field names.
Year and scope columns are text because the source mixes numbers with labels such as "FY2030"
and "NA"; empty cells are null, and "NA" is kept as the source's own label.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("sbti_companies", "sbti_targets")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE raw.sbti_companies (
          load_id                          uuid    NOT NULL REFERENCES raw.load_manifest (load_id),
          sbti_id                          bigint     NOT NULL,
          company_name                     text       NOT NULL,
          isin                             text,
          lei                              text,
          organization_type                text,
          location                         text,
          region                           text,
          sector                           text,
          near_term_status                 text,
          near_term_target_classification  text,
          near_term_target_year            text,
          long_term_status                 text,
          long_term_target_classification  text,
          long_term_target_year            text,
          net_zero_status                  text,
          net_zero_year                    text,
          full_target_language             text,
          ba15_status                      text,
          ba15_date                        timestamp,
          target_classification_long       text,
          status_reason                    text,
          date_updated                     timestamp,
          PRIMARY KEY (load_id, sbti_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE raw.sbti_targets (
          load_id                        uuid    NOT NULL REFERENCES raw.load_manifest (load_id),
          row_entry_id                   text       NOT NULL,
          sbti_id                        bigint     NOT NULL,
          company_name                   text       NOT NULL,
          isin                           text,
          lei                            text,
          location                       text,
          region                         text,
          sector                         text,
          organization_type              text,
          validation_route               text,
          action                         text,
          commitment_type                text,
          commitment_deadline            text,
          status                         text,
          status_reason                  text,
          full_target_language           text,
          company_temperature_alignment  text,
          target                         text,
          target_wording                 text,
          scope                          text,
          target_value                   text,
          type                           text,
          sub_type                       text,
          target_classification_short    text,
          base_year                      text,
          target_year                    text,
          year_type                      text,
          date_published                 timestamp,
          PRIMARY KEY (load_id, row_entry_id)
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE raw.sbti_targets IS "
        "'One row per company target or commitment; sbti_id repeats across a company''s rows'"
    )
    op.execute(
        "COMMENT ON COLUMN raw.sbti_targets.commitment_deadline IS "
        "'ISO timestamp as read from the workbook, or the source''s text such as NA'"
    )
    for table in TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON raw.{table} TO shockt_ingest")
        op.execute(f"GRANT SELECT ON raw.{table} TO shockt_transform, shockt_analyst")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE raw.{table}")
