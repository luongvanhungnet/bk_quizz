"""Make RAG metadata indexes correct on PostgreSQL/Neon."""

from alembic import op
import sqlalchemy as sa

revision = "0006_neon_postgresql"
down_revision = "0005_document_reindex"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgresql():
        return

    for name, table in (
        ("uq_documents_owner_hash_active", "documents"),
        ("idx_indexing_jobs_pending_updated", "indexing_jobs"),
        ("idx_indexing_jobs_running_heartbeat", "indexing_jobs"),
        ("uq_indexing_jobs_owner_idempotency", "indexing_jobs"),
        ("uq_indexing_jobs_document_active", "indexing_jobs"),
    ):
        op.drop_index(name, table_name=table, if_exists=True)

    op.create_index(
        "uq_documents_owner_hash_active",
        "documents",
        ["owner_id", "file_hash"],
        unique=True,
        postgresql_where=sa.text("status IN ('UPLOADED','PROCESSING','READY')"),
    )
    op.create_index(
        "idx_indexing_jobs_pending_updated",
        "indexing_jobs",
        ["updated_at"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        "idx_indexing_jobs_running_heartbeat",
        "indexing_jobs",
        ["heartbeat_at"],
        postgresql_where=sa.text("status = 'RUNNING'"),
    )
    op.create_index(
        "uq_indexing_jobs_owner_idempotency",
        "indexing_jobs",
        ["owner_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "uq_indexing_jobs_document_active",
        "indexing_jobs",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING','RUNNING')"),
    )


def downgrade() -> None:
    # The previous revision generated full indexes on PostgreSQL because it
    # only declared sqlite_where. Recreating that unsafe state is intentional
    # only when an operator explicitly downgrades.
    if not _is_postgresql():
        return
    for name, table in (
        ("uq_documents_owner_hash_active", "documents"),
        ("idx_indexing_jobs_pending_updated", "indexing_jobs"),
        ("idx_indexing_jobs_running_heartbeat", "indexing_jobs"),
        ("uq_indexing_jobs_owner_idempotency", "indexing_jobs"),
        ("uq_indexing_jobs_document_active", "indexing_jobs"),
    ):
        op.drop_index(name, table_name=table, if_exists=True)

    op.create_index(
        "uq_documents_owner_hash_active", "documents", ["owner_id", "file_hash"], unique=True
    )
    op.create_index("idx_indexing_jobs_pending_updated", "indexing_jobs", ["updated_at"])
    op.create_index("idx_indexing_jobs_running_heartbeat", "indexing_jobs", ["heartbeat_at"])
    op.create_index(
        "uq_indexing_jobs_owner_idempotency",
        "indexing_jobs",
        ["owner_id", "idempotency_key"],
        unique=True,
    )
    op.create_index(
        "uq_indexing_jobs_document_active", "indexing_jobs", ["document_id"], unique=True
    )
