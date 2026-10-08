"""Persist acquisition outcomes separately from immutable source snapshots."""

import sqlalchemy as sa

from alembic import op

revision = "c33b81ed4a05"
down_revision = "b15d20a3c704"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "acquisition_attempts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("jobs.job_id"), nullable=False),
        sa.Column(
            "snapshot_id", sa.String(32), sa.ForeignKey("posting_snapshots.id"), nullable=True
        ),
        sa.Column("fetch_id", sa.String(32), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column("requested_url", sa.Text(), nullable=False),
        sa.Column("final_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("fetch_id", "sequence", name="uq_acquisition_fetch_sequence"),
    )
    op.create_index("ix_acquisition_attempts_job_id", "acquisition_attempts", ["job_id"])
    op.create_index("ix_acquisition_attempts_fetch_id", "acquisition_attempts", ["fetch_id"])


def downgrade():
    op.drop_table("acquisition_attempts")
