"""raw schema and load manifest

Revision ID: 0001
Revises:
Create Date: 2026-10-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS raw")
    op.execute(
        """
        CREATE TABLE raw.load_manifest (
          load_id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
          dataset         text        NOT NULL,
          partition_key   text        NOT NULL,
          params          jsonb       NOT NULL,
          source_vintage  text,
          status          text        NOT NULL
                          CHECK (status IN ('running', 'succeeded', 'failed', 'superseded')),
          row_count       integer,
          bytes_processed bigint,
          error           text,
          object_key      text,
          object_sha256   text,
          code_version    text        NOT NULL,
          started_at      timestamptz NOT NULL DEFAULT now(),
          finished_at     timestamptz,
          superseded_by   uuid        REFERENCES raw.load_manifest (load_id)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX load_manifest_one_live_partition
          ON raw.load_manifest (dataset, partition_key)
          WHERE status = 'succeeded'
        """
    )
    op.execute(
        "COMMENT ON TABLE raw.load_manifest IS "
        "'One row per load of one partition of one dataset; raw rows reference it by load_id.'"
    )
    op.execute(
        "COMMENT ON COLUMN raw.load_manifest.object_key IS "
        "'Key of the archived source file in the object storage bucket, "
        "raw/{dataset}/{partition}/{filename}'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE raw.load_manifest")
    op.execute("DROP SCHEMA raw")
