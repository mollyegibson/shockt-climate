"""raw.load_manifest: a `retired` status for loads whose partition left the config

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE raw.load_manifest DROP CONSTRAINT load_manifest_status_check")
    op.execute(
        "ALTER TABLE raw.load_manifest ADD CONSTRAINT load_manifest_status_check "
        "CHECK (status IN ('running', 'succeeded', 'failed', 'superseded', 'retired'))"
    )
    op.execute(
        "COMMENT ON COLUMN raw.load_manifest.status IS "
        "'retired: the partition left the config; its data rows were deleted and its archived "
        "file kept'"
    )


def downgrade() -> None:
    op.execute("COMMENT ON COLUMN raw.load_manifest.status IS NULL")
    op.execute("ALTER TABLE raw.load_manifest DROP CONSTRAINT load_manifest_status_check")
    op.execute(
        "ALTER TABLE raw.load_manifest ADD CONSTRAINT load_manifest_status_check "
        "CHECK (status IN ('running', 'succeeded', 'failed', 'superseded'))"
    )
