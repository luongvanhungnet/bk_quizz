"""Add durable indexing jobs and audit events."""
from alembic import op
import sqlalchemy as sa

revision = "0002_async_indexing_jobs"
down_revision = "0001_user_documents"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("indexing_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_step", sa.String(64), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("idempotency_key", sa.String(128)),
        sa.Column("error_code", sa.String(80)), sa.Column("error_message", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], name="fk_indexing_jobs_document"),
        sa.CheckConstraint("status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','CANCELLED')", name="ck_indexing_jobs_status"),
        sa.CheckConstraint("progress_percent BETWEEN 0 AND 100", name="ck_indexing_jobs_progress"),
    )
    op.create_index("idx_indexing_jobs_owner_created", "indexing_jobs", ["owner_id", "created_at"])
    op.create_index("idx_indexing_jobs_status_heartbeat", "indexing_jobs", ["status", "heartbeat_at"])
    op.create_index("uq_indexing_jobs_owner_idempotency", "indexing_jobs", ["owner_id", "idempotency_key"], unique=True, sqlite_where=sa.text("idempotency_key IS NOT NULL"))
    op.create_table("audit_events",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("owner_id", sa.String(128), nullable=False),
        sa.Column("action", sa.String(64), nullable=False), sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(128), nullable=False), sa.Column("metadata_json", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_audit_events_owner_created", "audit_events", ["owner_id", "created_at"])

def downgrade() -> None:
    op.drop_index("idx_audit_events_owner_created", table_name="audit_events"); op.drop_table("audit_events")
    op.drop_index("uq_indexing_jobs_owner_idempotency", table_name="indexing_jobs")
    op.drop_index("idx_indexing_jobs_status_heartbeat", table_name="indexing_jobs")
    op.drop_index("idx_indexing_jobs_owner_created", table_name="indexing_jobs"); op.drop_table("indexing_jobs")
