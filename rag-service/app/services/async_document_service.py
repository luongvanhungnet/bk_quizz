import asyncio
import hashlib
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ServiceError
from app.db.models import ACTIVE_DOCUMENT_STATUSES, DocumentRecord, IndexingJob
from app.models.user_context import UserContext
from app.schemas.indexing_job import AsyncUploadResponse
from app.services.indexing_job_service import IndexingJobService
from app.services.upload_validation import UploadValidator, sanitize_filename
from app.services.user_document_service import UserDocumentService


class AsyncDocumentService:
    def __init__(
        self, *, database: Any, documents: UserDocumentService,
        jobs: IndexingJobService, upload_root: Path, max_upload_bytes: int,
        max_documents: int, max_storage_bytes: int,
        validator: UploadValidator | None = None,
    ) -> None:
        self._database = database
        self._documents = documents
        self._jobs = jobs
        self._upload_root = upload_root
        self._max_upload_bytes = max_upload_bytes
        self._max_documents = max_documents
        self._max_storage_bytes = max_storage_bytes
        self._validator = validator or UploadValidator()

    async def upload(
        self, context: UserContext, upload: UploadFile,
        idempotency_key: str | None,
    ) -> AsyncUploadResponse:
        if idempotency_key:
            existing = self._find_idempotent(context.owner_id, idempotency_key)
            if existing:
                await upload.close()
                return existing
        document_id = str(uuid.uuid4())
        filename = sanitize_filename(upload.filename)
        user_root = self._upload_root / context.safe_key
        staging = user_root / ".staging" / f"{document_id}.upload"
        staging.parent.mkdir(parents=True, exist_ok=True)
        digest, size = hashlib.sha256(), 0
        final_dir = user_root / document_id
        try:
            with staging.open("xb") as stream:
                while content := await upload.read(1024 * 1024):
                    size += len(content)
                    if size > self._max_upload_bytes:
                        raise ServiceError(413, "FILE_TOO_LARGE", "Tệp vượt quá giới hạn dung lượng cho phép.")
                    digest.update(content)
                    stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if not size:
                raise ServiceError(422, "EMPTY_FILE", "Tệp tải lên không được để trống.")
            mime = await asyncio.to_thread(self._validator.validate, staging, filename, upload.content_type)
            final_dir.mkdir(parents=True, exist_ok=False)
            os.replace(staging, final_dir / "original-file")
            try:
                document, job = self._reserve(
                    context, document_id, filename, mime, size, digest.hexdigest(), idempotency_key
                )
                if document.id != document_id:
                    shutil.rmtree(final_dir, ignore_errors=True)
            except Exception:
                shutil.rmtree(final_dir, ignore_errors=True)
                raise
            return AsyncUploadResponse(
                documentId=document.id, jobId=job.id,
                documentStatus=document.status, jobStatus=job.status,
            )
        finally:
            staging.unlink(missing_ok=True)
            await upload.close()

    def reindex(self, context: UserContext, document_id: str) -> AsyncUploadResponse:
        with self._database.session() as session:
            document = session.scalar(select(DocumentRecord).where(
                DocumentRecord.id == document_id,
                DocumentRecord.owner_id == context.owner_id,
                DocumentRecord.status == "READY",
            ))
            if document is None:
                raise ServiceError(404, "DOCUMENT_NOT_FOUND", "Không tìm thấy tài liệu.")
            source = self._upload_root / context.safe_key / document.id / document.stored_filename
            if not source.is_file():
                raise ServiceError(
                    409, "DOCUMENT_SOURCE_FILE_MISSING",
                    "Không tìm thấy tệp nguồn để xử lý lại.",
                )
            active = session.scalar(select(IndexingJob).where(
                IndexingJob.document_id == document.id,
                IndexingJob.status.in_(["PENDING", "RUNNING"]),
            ).order_by(IndexingJob.created_at.desc()))
            if active is None:
                try:
                    active = self._jobs.create_in_session(
                        session,
                        owner_id=context.owner_id,
                        document_id=document.id,
                        idempotency_key=None,
                        operation="REINDEX",
                    )
                    self._jobs.audit_in_session(
                        session, context.owner_id, "DOCUMENT_REINDEX_REQUESTED",
                        "DOCUMENT", document.id,
                    )
                    session.commit()
                except IntegrityError:
                    session.rollback()
                    active = session.scalar(select(IndexingJob).where(
                        IndexingJob.document_id == document.id,
                        IndexingJob.status.in_(["PENDING", "RUNNING"]),
                    ).order_by(IndexingJob.created_at.desc()))
                    if active is None:
                        raise
            return AsyncUploadResponse(
                documentId=document.id,
                jobId=active.id,
                documentStatus=document.status,
                jobStatus=active.status,
            )

    def resolve_by_hash(self, owner_id: str, file_hash: str):
        normalized = file_hash.strip().casefold()
        if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
            raise ServiceError(422, "VALIDATION_ERROR", "SHA-256 không hợp lệ.")
        with self._database.session() as session:
            document = session.scalar(select(DocumentRecord).where(
                DocumentRecord.owner_id == owner_id,
                DocumentRecord.file_hash == normalized,
                DocumentRecord.status == "READY",
            ).order_by(DocumentRecord.created_at.desc()))
            if document is None:
                raise ServiceError(404, "DOCUMENT_NOT_FOUND", "Không tìm thấy tài liệu.")
            return self._documents._dto(document)

    def _reserve(self, context: UserContext, document_id: str, filename: str,
                 mime: str, size: int, file_hash: str,
                 idempotency_key: str | None) -> tuple[DocumentRecord, IndexingJob]:
        try:
            with self._documents._indexes.lock_for(context.owner_id), self._database.session() as session:
                if idempotency_key:
                    existing_job = session.scalar(
                        select(IndexingJob).where(
                            IndexingJob.owner_id == context.owner_id,
                            IndexingJob.idempotency_key == idempotency_key,
                        )
                    )
                    if existing_job is not None:
                        existing_document = session.get(DocumentRecord, existing_job.document_id)
                        if existing_document is not None:
                            return existing_document, existing_job
                count, used = session.execute(select(
                    func.count(), func.coalesce(func.sum(DocumentRecord.file_size), 0)
                ).where(
                    DocumentRecord.owner_id == context.owner_id,
                    DocumentRecord.status.in_(ACTIVE_DOCUMENT_STATUSES),
                )).one()
                if count >= self._max_documents:
                    raise ServiceError(409, "DOCUMENT_QUOTA_EXCEEDED", "Đã đạt số tài liệu tối đa của tài khoản.")
                if used + size > self._max_storage_bytes:
                    raise ServiceError(409, "STORAGE_QUOTA_EXCEEDED", "Đã vượt dung lượng lưu trữ của tài khoản.")
                document = DocumentRecord(
                    id=document_id, owner_id=context.owner_id, classroom_id=context.classroom_id,
                    source_type="USER_UPLOAD", original_filename=filename,
                    stored_filename="original-file", mime_type=mime, file_size=size,
                    file_hash=file_hash, status="PROCESSING",
                )
                session.add(document)
                job = self._jobs.create_in_session(
                    session, owner_id=context.owner_id, document_id=document_id,
                    idempotency_key=idempotency_key,
                )
                session.commit()
                return document, job
        except IntegrityError as error:
            raise ServiceError(409, "DUPLICATE_DOCUMENT", "Tài liệu này đã được tải lên.") from error

    def _find_idempotent(self, owner_id: str, key: str) -> AsyncUploadResponse | None:
        with self._database.session() as session:
            job = session.scalar(select(IndexingJob).where(
                IndexingJob.owner_id == owner_id, IndexingJob.idempotency_key == key,
            ))
            if job is None:
                return None
            document = session.get(DocumentRecord, job.document_id)
            if document is None:
                return None
            return AsyncUploadResponse(
                documentId=document.id, jobId=job.id,
                documentStatus=document.status, jobStatus=job.status,
            )

    def delete_user_data(self, owner_id: str, safe_key: str) -> None:
        from app.db.models import AuditEvent

        with self._database.session() as session:
            documents = session.scalars(select(DocumentRecord).where(DocumentRecord.owner_id == owner_id)).all()
            for document in documents:
                try:
                    self._documents._indexes.remove_document(owner_id, document.id)
                except Exception:
                    pass
                session.delete(document)
            session.query(AuditEvent).filter(AuditEvent.owner_id == owner_id).delete()
            session.commit()
        shutil.rmtree(self._upload_root / safe_key, ignore_errors=True)
        try:
            shutil.rmtree(self._documents._indexes._root / safe_key, ignore_errors=True)
        except AttributeError:
            pass


class AsyncDocumentProcessor:
    def __init__(self, documents: UserDocumentService, jobs: IndexingJobService) -> None:
        self._documents = documents
        self._jobs = jobs

    def process(self, job_id: str) -> None:
        if not self._jobs.claim(job_id):
            return
        raw = self._jobs.raw(job_id)
        if raw is None:
            return
        owner_id, document_id, _operation = raw
        try:
            record = self._documents._owned_record(owner_id, document_id)
            if record.status == "DELETED" or self._jobs.is_cancelled(job_id):
                self._jobs.cancel(owner_id, job_id)
                return
            safe_key = __import__("app.models.user_context", fromlist=["safe_user_key"]).safe_user_key(owner_id)
            path = self._documents._upload_root / safe_key / document_id / record.stored_filename
            self._step(job_id, "PARSING", 30)
            sections = self._documents._parser.parse(path, record.original_filename, document_id)
            self._step(job_id, "CHUNKING", 50)
            drafts = self._documents._chunker.chunk_sections(sections)
            if not drafts:
                code = "SCANNED_PDF_REQUIRES_OCR" if record.original_filename.casefold().endswith(".pdf") else "DOCUMENT_HAS_NO_TEXT"
                raise ServiceError(422, code, "Tài liệu không có văn bản có thể lập chỉ mục.")
            context = UserContext(owner_id, safe_key, record.classroom_id)
            chunks = self._documents._to_chunks(
                document_id, context, record.original_filename, record.file_hash, drafts
            )
            self._step(job_id, "EMBEDDING", 70)
            if self._jobs.is_cancelled(job_id):
                return
            self._step(job_id, "COMMITTING", 90)
            pages = {d.page_number for d in drafts if d.page_number is not None}
            slides = {d.slide_number for d in drafts if d.slide_number is not None}
            math_formula_count = sum(section.math_formula_count for section in sections)
            math_warning_count = sum(section.math_warning_count for section in sections)
            self._commit_if_running(
                job_id, owner_id, document_id, chunks, len(pages or slides) or None,
                math_formula_count, math_warning_count,
            )
            self._jobs.succeed(job_id)
        except ServiceError as error:
            self._jobs.fail(job_id, error.code, error.message)
            raise
        except ValueError as error:
            self._jobs.fail(job_id, "DOCUMENT_PARSE_FAILED", "Không thể đọc nội dung tài liệu.")
            raise ServiceError(422, "DOCUMENT_PARSE_FAILED", "Không thể đọc nội dung tài liệu.") from error
        except Exception as error:
            self._jobs.fail(job_id, "DOCUMENT_PROCESSING_FAILED", "Không thể xử lý tài liệu.")
            raise ServiceError(500, "DOCUMENT_PROCESSING_FAILED", "Không thể xử lý tài liệu.") from error

    def _step(self, job_id: str, step: str, progress: int) -> None:
        if self._jobs.is_cancelled(job_id):
            raise ServiceError(409, "INDEXING_CANCELLED", "Job lập chỉ mục đã được hủy.")
        if not self._jobs.progress(job_id, step, progress):
            raise ServiceError(409, "INDEXING_NOT_RUNNING", "Job lập chỉ mục không còn chạy.")

    def _commit_if_running(
        self, job_id: str, owner_id: str, document_id: str,
        chunks: list[Any], page_count: int | None,
        math_formula_count: int = 0, math_warning_count: int = 0,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self._documents._indexes.lock_for(owner_id), self._documents._database.session() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            job = session.get(IndexingJob, job_id)
            if job is None or job.status != "RUNNING":
                session.rollback()
                raise ServiceError(409, "INDEXING_CANCELLED", "Job lập chỉ mục đã được hủy.")
            snapshot = self._documents._indexes.snapshot_for(owner_id)
            previous_chunks = [] if snapshot is None else [
                chunk for chunk in snapshot.chunks
                if chunk.document_id == document_id and chunk.owner_id == owner_id
            ]
            self._documents._indexes.replace_document(owner_id, document_id, chunks)
            try:
                document = session.get(DocumentRecord, document_id)
                if document is None or document.status == "DELETED":
                    raise ServiceError(404, "DOCUMENT_NOT_FOUND", "Không tìm thấy tài liệu.")
                document.status = "READY"
                document.page_count = page_count
                document.chunk_count = len(chunks)
                document.math_formula_count = math_formula_count
                document.math_warning_count = math_warning_count
                document.math_extraction_status = (
                    "FAILED" if math_warning_count and not math_formula_count
                    else "PARTIAL" if math_warning_count
                    else "ENHANCED" if math_formula_count else "NOT_DETECTED"
                )
                document.error_message = None
                document.indexed_at = document.updated_at = now
                session.commit()
            except Exception:
                session.rollback()
                self._documents._indexes.replace_document(
                    owner_id, document_id, previous_chunks
                )
                raise
