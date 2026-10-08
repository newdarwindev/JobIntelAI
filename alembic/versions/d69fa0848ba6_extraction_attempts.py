"""Record extraction outcomes without replacing successful immutable runs."""

import sqlalchemy as sa

from alembic import op

revision = "d69fa0848ba6"
down_revision = "c33b81ed4a05"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("acquisition_attempts", sa.Column("recorded_at", sa.String(40), nullable=True))
    op.create_table(
        "extraction_attempts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("jobs.job_id"), nullable=False),
        sa.Column(
            "snapshot_id", sa.String(32), sa.ForeignKey("posting_snapshots.id"), nullable=False
        ),
        sa.Column("run_id", sa.String(32), sa.ForeignKey("extraction_runs.id"), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("configuration", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_extraction_attempts_job_id", "extraction_attempts", ["job_id"])
    op.create_index("ix_extraction_attempts_snapshot_id", "extraction_attempts", ["snapshot_id"])


def downgrade():
    op.drop_table("extraction_attempts")
    op.drop_column("acquisition_attempts", "recorded_at")
