"""Add performance indexes to file_metadata table.

Revision ID: 20260324_0001
Revises: 20260216_0001
Create Date: 2026-03-24
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260324_0001"
down_revision = "20260216_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add indexes for common file_metadata query patterns."""
    # Single-column indexes for filtering
    op.create_index(op.f("ix_file_metadata_name"), "file_metadata", ["name"], unique=False)
    op.create_index(
        op.f("ix_file_metadata_mime_type"), "file_metadata", ["mime_type"], unique=False
    )
    op.create_index(
        op.f("ix_file_metadata_size_bytes"), "file_metadata", ["size_bytes"], unique=False
    )

    # Composite indexes for common query patterns
    op.create_index(
        op.f("ix_file_metadata_workspace_id_name"),
        "file_metadata",
        ["workspace_id", "name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_file_metadata_workspace_id_mime_type"),
        "file_metadata",
        ["workspace_id", "mime_type"],
        unique=False,
    )


def downgrade() -> None:
    """Remove file_metadata performance indexes."""
    # Drop composite indexes first
    op.drop_index(op.f("ix_file_metadata_workspace_id_mime_type"), table_name="file_metadata")
    op.drop_index(op.f("ix_file_metadata_workspace_id_name"), table_name="file_metadata")

    # Drop single-column indexes
    op.drop_index(op.f("ix_file_metadata_size_bytes"), table_name="file_metadata")
    op.drop_index(op.f("ix_file_metadata_mime_type"), table_name="file_metadata")
    op.drop_index(op.f("ix_file_metadata_name"), table_name="file_metadata")
