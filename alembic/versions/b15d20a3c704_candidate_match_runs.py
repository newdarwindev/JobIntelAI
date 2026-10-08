"""Reuse immutable candidate snapshots and persist coherent match runs."""

import sqlalchemy as sa

from alembic import op

revision = "b15d20a3c704"
down_revision = "a01c4e72b903"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "match_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "extraction_run_id", sa.String(32), sa.ForeignKey("extraction_runs.id"), nullable=False
        ),
        sa.Column(
            "snapshot_id", sa.String(32), sa.ForeignKey("posting_snapshots.id"), nullable=False
        ),
        sa.Column(
            "profile_revision_id",
            sa.String(32),
            sa.ForeignKey("candidate_evidence.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_match_runs_extraction_run_id", "match_runs", ["extraction_run_id"])
    op.create_index("ix_match_runs_profile_revision_id", "match_runs", ["profile_revision_id"])
    with op.batch_alter_table("matches") as batch:
        batch.add_column(sa.Column("match_run_id", sa.String(32), nullable=True))
        batch.create_foreign_key("fk_matches_match_run", "match_runs", ["match_run_id"], ["id"])
        batch.create_index("ix_matches_match_run_id", ["match_run_id"])


def downgrade():
    with op.batch_alter_table("matches") as batch:
        batch.drop_index("ix_matches_match_run_id")
        batch.drop_constraint("fk_matches_match_run", type_="foreignkey")
        batch.drop_column("match_run_id")
    op.drop_table("match_runs")
