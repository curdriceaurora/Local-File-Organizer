"""Add canonical organization job lifecycle fields.

Revision ID: 20260721_0002
Revises: 20260216_0001
Create Date: 2026-07-21
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260721_0002"
down_revision = "20260216_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Persist canonical scheduling, recovery, and concurrency metadata."""
    with op.batch_alter_table("organization_jobs") as batch_op:
        batch_op.add_column(sa.Column("error_code", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column("error_retryable", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("error_details_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("idempotency_key", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("transaction_id", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column("recovery_action", sa.String(), nullable=False, server_default="none")
        )
        batch_op.create_unique_constraint(
            "uq_organization_jobs_type_idempotency",
            ["job_type", "idempotency_key"],
        )


def downgrade() -> None:
    """Remove canonical organization job lifecycle fields."""
    with op.batch_alter_table("organization_jobs") as batch_op:
        batch_op.drop_constraint("uq_organization_jobs_type_idempotency", type_="unique")
        batch_op.drop_column("recovery_action")
        batch_op.drop_column("transaction_id")
        batch_op.drop_column("scheduled_for")
        batch_op.drop_column("idempotency_key")
        batch_op.drop_column("revision")
        batch_op.drop_column("error_details_json")
        batch_op.drop_column("error_retryable")
        batch_op.drop_column("error_code")
