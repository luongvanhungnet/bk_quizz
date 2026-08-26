import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from prometheus_client import Counter, Gauge
from sqlalchemy import select, update

from app.core.exceptions import ServiceError
from app.db.models import AuditEvent, DocumentRecord, IndexingJob
from app.schemas.indexing_job import IndexingJobDto

JOB_TRANSITIONS = Counter("rag_indexing_job_transitions_total", "Indexing job transitions", ["status"])
ACTIVE_JOBS = Gauge("rag_indexing_active_jobs", "Currently running indexing jobs")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class IndexingJobService:
    def __init__(self, database: Any, *, max_attempts: int = 3) -> None:
        self._database = database
        self._max_attempts = max_attempts

    def create_in_session(
        self,
        session: Any,
        *,
        owner_id: str,
        document_id: str,
        idempotency_key: str | None,
        operation: str = "UPLOAD",
    ) -> IndexingJob:
        if idempotency_key:
            existing = session.scalar(select(IndexingJob).where(
                IndexingJob.owner_id == owner_id,
                IndexingJob.idempotency_key == idempotency_key,
            ))
            if existing is not None:
                return existing
        job = IndexingJob(
            id=str(uuid.uuid4()), document_id=document_id, owner_id=owner_id,
            max_attempts=self._max_attempts, idempotency_key=idempotency_key,
            operation=operation,
        )
        session.add(job)
        JOB_TRANSITIONS.labels("PENDING").inc()
        self.audit_in_session(session, owner_id, "DOCUMENT_UPLOAD", "INDEXING_JOB", job.id)
        return job

    @staticmethod
    def audit_in_session(
        session: Any, owner_id: str, action: str, target_type: str,
        target_id: str, metadata: dict[str, Any] | None = None,
    ) -> None:
        session.add(AuditEvent(
            id=str(uuid.uuid4()), owner_id=owner_id, action=action,
            target_type=target_type, target_id=target_id,
            metadata_json=json.dumps(metadata, separators=(",", ":")) if metadata else None,
        ))

    def get(self, owner_id: str, job_id: str) -> IndexingJobDto:
        with self._database.session() as session:
            job = session.scalar(select(IndexingJob).where(
                IndexingJob.id == job_id, IndexingJob.owner_id == owner_id,
            ))
            if job is None:
                raise self._not_found()
            return self._dto(job)

    def claim(self, job_id: str) -> bool:
        now = now_utc()
        with self._database.session() as session:
            result = session.execute(update(IndexingJob).where(
                IndexingJob.id == job_id, IndexingJob.status == "PENDING",
            ).values(
                status="RUNNING", current_step="VALIDATING", progress_percent=10,
                attempt_count=IndexingJob.attempt_count + 1,
                started_at=now, heartbeat_at=now, updated_at=now,
                error_code=None, error_message=None, finished_at=None,
            ))
            session.commit()
            if result.rowcount == 1:
                JOB_TRANSITIONS.labels("RUNNING").inc()
                ACTIVE_JOBS.inc()
            return result.rowcount == 1

    def progress(self, job_id: str, step: str, percent: int) -> bool:
        now = now_utc()
        with self._database.session() as session:
            result = session.execute(update(IndexingJob).where(
                IndexingJob.id == job_id, IndexingJob.status == "RUNNING",
            ).values(current_step=step, progress_percent=percent, heartbeat_at=now, updated_at=now))
            session.commit()
            return result.rowcount == 1

    def is_cancelled(self, job_id: str) -> bool:
        with self._database.session() as session:
            return session.scalar(select(IndexingJob.status).where(IndexingJob.id == job_id)) == "CANCELLED"

    def succeed(self, job_id: str) -> None:
        now = now_utc()
        with self._database.session() as session:
            job = session.get(IndexingJob, job_id)
            if job is None or job.status in {"CANCELLED", "SUCCEEDED"}:
                return
            was_running = job.status == "RUNNING"
            job.status, job.current_step, job.progress_percent = "SUCCEEDED", "SUCCEEDED", 100
            job.heartbeat_at = job.updated_at = job.finished_at = now
            self.audit_in_session(session, job.owner_id, "INDEXING_SUCCEEDED", "INDEXING_JOB", job.id)
            session.commit()
            JOB_TRANSITIONS.labels("SUCCEEDED").inc()
            if was_running:
                ACTIVE_JOBS.dec()

    def fail(self, job_id: str, code: str, message: str) -> None:
        now = now_utc()
        with self._database.session() as session:
            job = session.get(IndexingJob, job_id)
            if job is None or job.status in {"CANCELLED", "FAILED"}:
                return
            was_running = job.status == "RUNNING"
            job.status, job.current_step = "FAILED", "FAILED"
            job.error_code, job.error_message = code[:80], message[:500]
            job.heartbeat_at = job.updated_at = job.finished_at = now
            document = session.get(DocumentRecord, job.document_id)
            if (document is not None and document.status != "DELETED"
                    and job.operation != "REINDEX"):
                document.status, document.error_message = "FAILED", code[:500]
                document.updated_at = now
            self.audit_in_session(session, job.owner_id, "INDEXING_FAILED", "INDEXING_JOB", job.id, {"code": code})
            session.commit()
            JOB_TRANSITIONS.labels("FAILED").inc()
            if was_running:
                ACTIVE_JOBS.dec()

    def cancel(self, owner_id: str, job_id: str) -> IndexingJobDto:
        now = now_utc()
        with self._database.session() as session:
            job = session.scalar(select(IndexingJob).where(IndexingJob.id == job_id, IndexingJob.owner_id == owner_id))
            if job is None:
                raise self._not_found()
            if job.status not in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                was_running = job.status == "RUNNING"
                job.status, job.current_step, job.finished_at = "CANCELLED", "CANCELLED", now
                job.updated_at = now
                document = session.get(DocumentRecord, job.document_id)
                if (document is not None and document.status != "DELETED"
                        and job.operation != "REINDEX"):
                    document.status = "FAILED"
                    document.error_message = "INDEXING_CANCELLED"
                    document.updated_at = now
                self.audit_in_session(session, owner_id, "INDEXING_CANCELLED", "INDEXING_JOB", job.id)
                session.commit()
                JOB_TRANSITIONS.labels("CANCELLED").inc()
                if was_running:
                    ACTIVE_JOBS.dec()
            return self._dto(job)

    def retry(self, owner_id: str, job_id: str, *, reset_attempts: bool = False) -> IndexingJobDto:
        now = now_utc()
        with self._database.session() as session:
            job = session.scalar(select(IndexingJob).where(IndexingJob.id == job_id, IndexingJob.owner_id == owner_id))
            if job is None:
                raise self._not_found()
            if job.status not in {"FAILED", "CANCELLED"}:
                raise ServiceError(409, "JOB_NOT_RETRYABLE", "Chỉ có thể thử lại job thất bại hoặc đã hủy.")
            if not reset_attempts and job.attempt_count >= job.max_attempts:
                raise ServiceError(409, "JOB_MAX_ATTEMPTS_EXCEEDED", "Job đã dùng hết số lần thử tự động.")
            if reset_attempts:
                job.attempt_count = 0
            job.status, job.current_step, job.progress_percent = "PENDING", "PENDING", 0
            job.error_code = job.error_message = job.finished_at = None
            job.updated_at = now
            document = session.get(DocumentRecord, job.document_id)
            if (document is not None and document.status != "DELETED"
                    and job.operation != "REINDEX"):
                document.status, document.error_message = "PROCESSING", None
                document.updated_at = now
            self.audit_in_session(session, owner_id, "INDEXING_RETRIED", "INDEXING_JOB", job.id)
            session.commit()
            return self._dto(job)

    def audit(self, owner_id: str, action: str, target_type: str, target_id: str) -> None:
        with self._database.session() as session:
            self.audit_in_session(session, owner_id, action, target_type, target_id)
            session.commit()

    def recover_stale(self, stale_seconds: int) -> list[str]:
        cutoff, now = now_utc() - timedelta(seconds=stale_seconds), now_utc()
        recovered: list[str] = []
        with self._database.session() as session:
            jobs = session.scalars(select(IndexingJob).where(
                IndexingJob.status == "RUNNING", IndexingJob.heartbeat_at < cutoff,
                IndexingJob.attempt_count < IndexingJob.max_attempts,
            )).all()
            for job in jobs:
                job.status, job.current_step, job.progress_percent = "PENDING", "PENDING", 0
                job.updated_at = now
                recovered.append(job.id)
            session.commit()
        return recovered

    def pending_for_reconciliation(self, pending_seconds: int) -> list[str]:
        cutoff = now_utc() - timedelta(seconds=pending_seconds)
        with self._database.session() as session:
            return list(session.scalars(
                select(IndexingJob.id).where(
                    IndexingJob.status == "PENDING",
                    IndexingJob.updated_at < cutoff,
                )
            ).all())

    def raw(self, job_id: str) -> tuple[str, str, str] | None:
        with self._database.session() as session:
            row = session.execute(select(
                IndexingJob.owner_id, IndexingJob.document_id,
                IndexingJob.operation,
            ).where(IndexingJob.id == job_id)).one_or_none()
            return tuple(row) if row else None

    def cancel_for_document(self, owner_id: str, document_id: str) -> None:
        with self._database.session() as session:
            ids = session.scalars(select(IndexingJob.id).where(
                IndexingJob.owner_id == owner_id,
                IndexingJob.document_id == document_id,
                IndexingJob.status.in_(["PENDING", "RUNNING"]),
            )).all()
        for job_id in ids:
            self.cancel(owner_id, job_id)

    @staticmethod
    def _dto(job: IndexingJob) -> IndexingJobDto:
        return IndexingJobDto(
            id=job.id, documentId=job.document_id, status=job.status,
            progress=job.progress_percent, step=job.current_step,
            attempts=job.attempt_count, maxAttempts=job.max_attempts,
            errorCode=job.error_code, errorMessage=job.error_message,
            createdAt=job.created_at, updatedAt=job.updated_at,
            startedAt=job.started_at, heartbeatAt=job.heartbeat_at, finishedAt=job.finished_at,
        )

    @staticmethod
    def _not_found() -> ServiceError:
        return ServiceError(404, "INDEXING_JOB_NOT_FOUND", "Không tìm thấy job lập chỉ mục.")
