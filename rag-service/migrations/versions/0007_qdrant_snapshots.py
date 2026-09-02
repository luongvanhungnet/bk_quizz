"""Store atomic active-version pointers for Qdrant namespaces."""

from alembic import op
import sqlalchemy as sa

revision = "0007_qdrant_snapshots"
down_revision = "0006_neon_postgresql"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vector_index_snapshots",
        sa.Column("namespace", sa.String(160), primary_key=True),
        sa.Column("active_version", sa.String(36), nullable=False),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("vector_index_snapshots")
