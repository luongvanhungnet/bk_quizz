"""Create isolated user document metadata."""
from alembic import op
import sqlalchemy as sa


revision = "0001_user_documents"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(128), nullable=False),
        sa.Column("classroom_id", sa.String(128)),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("stored_filename", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("page_count", sa.Integer()),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("source_type IN ('USER_UPLOAD','SYSTEM')", name="ck_documents_source_type"),
        sa.CheckConstraint("status IN ('UPLOADED','PROCESSING','READY','FAILED','DELETED')", name="ck_documents_status"),
        sa.CheckConstraint("file_size >= 0", name="ck_documents_file_size"),
    )
    op.create_index("idx_documents_owner_status_created", "documents", ["owner_id", "status", "created_at"])
    op.create_index("idx_documents_classroom", "documents", ["classroom_id"])
    op.create_index(
        "uq_documents_owner_hash_active",
        "documents",
        ["owner_id", "file_hash"],
        unique=True,
        sqlite_where=sa.text("status IN ('UPLOADED','PROCESSING','READY')"),
    )


def downgrade() -> None:
    op.drop_index("uq_documents_owner_hash_active", table_name="documents")
    op.drop_index("idx_documents_classroom", table_name="documents")
    op.drop_index("idx_documents_owner_status_created", table_name="documents")
    op.drop_table("documents")
