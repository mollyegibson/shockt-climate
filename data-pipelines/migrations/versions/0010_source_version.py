"""rename raw.load_manifest.source_vintage to source_version

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE raw.load_manifest RENAME COLUMN source_vintage TO source_version")
    op.execute(
        "COMMENT ON COLUMN raw.load_manifest.source_version IS "
        "'Which edition of the source the load came from, as the source exposes it: a release, "
        "Last-Modified header, last-edited date or fetch time'"
    )


def downgrade() -> None:
    op.execute("COMMENT ON COLUMN raw.load_manifest.source_version IS NULL")
    op.execute("ALTER TABLE raw.load_manifest RENAME COLUMN source_version TO source_vintage")
