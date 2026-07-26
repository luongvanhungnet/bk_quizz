from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ACTIVE_DOCUMENT_STATUSES = ("UPLOADED", "PROCESSING", "READY")


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DocumentRecord(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('USER_UPLOAD','SYSTEM')",
            name="ck_documents_source_type",
        ),
        CheckConstraint(
            "status IN ('UPLOADED','PROCESSING','READY','FAILED','DELETED')",
            name="ck_documents_status",
        ),
        CheckConstraint("file_size >= 0", name="ck_documents_file_size"),
        Index("idx_documents_owner_status_created", "owner_id", "status", "created_at"),
        Index("idx_documents_classroom", "classroom_id"),
        Index(
            "uq_documents_owner_hash_active",
            "owner_id",
            "file_hash",
            unique=True,
            sqlite_where=text("status IN ('UPLOADED','PROCESSING','READY')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False)
    classroom_id: Mapped[str | None] = mapped_column(String(128))
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="USER_UPLOAD")
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(64), nullable=False, default="original-file")
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="UPLOADED")
    page_count: Mapped[int | None] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IndexingJob(Base):
    __tablename__ = "indexing_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','CANCELLED')", name="ck_indexing_jobs_status"),
        CheckConstraint("progress_percent BETWEEN 0 AND 100", name="ck_indexing_jobs_progress"),
        Index("idx_indexing_jobs_owner_created", "owner_id", "created_at"),
        Index("idx_indexing_jobs_status_heartbeat", "status", "heartbeat_at"),
        Index(
            "idx_indexing_jobs_pending_updated",
            "updated_at",
            sqlite_where=text("status = 'PENDING'"),
        ),
        Index(
            "idx_indexing_jobs_running_heartbeat",
            "heartbeat_at",
            sqlite_where=text("status = 'RUNNING'"),
        ),
        Index("uq_indexing_jobs_owner_idempotency", "owner_id", "idempotency_key", unique=True, sqlite_where=text("idempotency_key IS NOT NULL")),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_step: Mapped[str] = mapped_column(String(64), nullable=False, default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("idx_audit_events_owner_created", "owner_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
