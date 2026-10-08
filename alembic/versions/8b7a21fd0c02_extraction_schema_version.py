"""Version immutable extraction payloads without rewriting historical JSON."""

import sqlalchemy as sa

from alembic import op

revision = "8b7a21fd0c02"
down_revision = "e44d9dbe9d1d"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "extraction_runs",
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade():
    op.drop_column("extraction_runs", "schema_version")
