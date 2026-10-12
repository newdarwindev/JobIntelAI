"""Durable request identities and atomic mutation response recovery."""

import sqlalchemy as sa

from alembic import op

revision = "f16a2c407b91"
down_revision = "d69fa0848ba6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mutation_operations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("request_sha256", sa.String(64), nullable=True),
        sa.Column("method", sa.String(10), nullable=True),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("completed_at", sa.String(40), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("execution_count", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "state IN ('uncertain', 'committed', 'rejected')", name="ck_mutation_operation_state"
        ),
    )


def downgrade():
    op.drop_table("mutation_operations")
