"""Add indexes matching job reconciliation and recovery queries."""

from alembic import op
import sqlalchemy as sa

revision = "0003_performance_indexes"
down_revision = "0002_async_indexing_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_indexing_jobs_pending_updated",
        "indexing_jobs",
        ["updated_at"],
        sqlite_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        "idx_indexing_jobs_running_heartbeat",
        "indexing_jobs",
        ["heartbeat_at"],
        sqlite_where=sa.text("status = 'RUNNING'"),
    )


def downgrade() -> None:
    op.drop_index("idx_indexing_jobs_running_heartbeat", table_name="indexing_jobs")
    op.drop_index("idx_indexing_jobs_pending_updated", table_name="indexing_jobs")
