"""Add in-place document reindex jobs."""

from alembic import op
import sqlalchemy as sa

revision = "0005_document_reindex"
down_revision = "0004_pdf_math_extraction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "indexing_jobs",
        sa.Column("operation", sa.String(20), nullable=False, server_default="UPLOAD"),
    )
    with op.batch_alter_table("indexing_jobs") as batch:
        batch.create_check_constraint(
            "ck_indexing_jobs_operation", "operation IN ('UPLOAD','REINDEX')"
        )
    op.execute(sa.text("""
        UPDATE indexing_jobs
           SET status = 'CANCELLED', current_step = 'CANCELLED',
               updated_at = CURRENT_TIMESTAMP, finished_at = CURRENT_TIMESTAMP
         WHERE status IN ('PENDING','RUNNING')
           AND EXISTS (
               SELECT 1 FROM indexing_jobs newer
                WHERE newer.document_id = indexing_jobs.document_id
                  AND newer.status IN ('PENDING','RUNNING')
                  AND (newer.created_at > indexing_jobs.created_at
                       OR (newer.created_at = indexing_jobs.created_at
                           AND newer.id > indexing_jobs.id))
           )
    """))
    op.create_index(
        "uq_indexing_jobs_document_active", "indexing_jobs", ["document_id"],
        unique=True, sqlite_where=sa.text("status IN ('PENDING','RUNNING')"),
    )


def downgrade() -> None:
    op.drop_index("uq_indexing_jobs_document_active", table_name="indexing_jobs")
    with op.batch_alter_table("indexing_jobs") as batch:
        batch.drop_constraint("ck_indexing_jobs_operation", type_="check")
        batch.drop_column("operation")
