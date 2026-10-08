"""Keep extraction provenance separate from immutable schema payloads."""

import sqlalchemy as sa

from alembic import op

revision = "a01c4e72b903"
down_revision = "8b7a21fd0c02"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("extraction_runs", sa.Column("provenance", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("extraction_runs", "provenance")
