"""Store PDF math extraction status and reusable region results."""

from alembic import op
import sqlalchemy as sa

revision = "0004_pdf_math_extraction"
down_revision = "0003_performance_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("math_extraction_status", sa.String(20), nullable=False, server_default="NOT_DETECTED"))
    op.add_column("documents", sa.Column("math_formula_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("documents", sa.Column("math_warning_count", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "math_extractions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("bbox_json", sa.Text(), nullable=False),
        sa.Column("crop_sha256", sa.String(64), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("latex", sa.Text()),
        sa.Column("provider", sa.String(32)),
        sa.Column("model", sa.String(128)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("extraction_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("document_id", "crop_sha256", "model", "extraction_version", name="uq_math_extraction_cache"),
    )
    op.create_index("idx_math_extractions_document_page", "math_extractions", ["document_id", "page_number"])


def downgrade() -> None:
    op.drop_index("idx_math_extractions_document_page", table_name="math_extractions")
    op.drop_table("math_extractions")
    op.drop_column("documents", "math_warning_count")
    op.drop_column("documents", "math_formula_count")
    op.drop_column("documents", "math_extraction_status")
