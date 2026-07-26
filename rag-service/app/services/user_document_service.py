import asyncio
import hashlib
import logging
import math
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ServiceError
from app.core.request_context import REQUEST_TRACE_ID
from app.db.models import ACTIVE_DOCUMENT_STATUSES, DocumentRecord
from app.models.document import DocumentChunk, utc_now_iso
from app.models.user_context import UserContext
from app.schemas.user_document import PaginationDto, UserDocumentDto, UserDocumentListResponse
from app.services.chunking_service import ChunkingService
from app.services.document_parser import DocumentParser
from app.services.upload_validation import UploadValidator, sanitize_filename

LOGGER = logging.getLogger("uvicorn.error")


class UserDocumentService:
    def __init__(
        self,
        *,
        database: Any,
        upload_root: Path,
        max_upload_bytes: int,
        max_documents: int,
        max_storage_bytes: int,
        parser: DocumentParser,
        chunker: ChunkingService,
        index_manager: Any,
        validator: UploadValidator | None = None,
    ) -> None:
        self._database = database
        self._upload_root = upload_root
        self._max_upload_bytes = max_upload_bytes
        self._max_documents = max_documents
        self._max_storage_bytes = max_storage_bytes
        self._parser = parser
        self._chunker = chunker
        self._indexes = index_manager
        self._validator = validator or UploadValidator()

    async def upload(self, context: UserContext, upload: UploadFile) -> UserDocumentDto:
        document_id = str(uuid.uuid4())
        filename = sanitize_filename(upload.filename)
        user_root = self._upload_root / context.safe_key
        staging = user_root / ".staging" / f"{document_id}.upload"
        staging.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        index_committed = False
        stage = "STREAMING"
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
            if size == 0:
                raise ServiceError(422, "EMPTY_FILE", "Tệp tải lên không được để trống.")
            stage = "VALIDATING"
            mime = await asyncio.to_thread(
                self._validator.validate, staging, filename, upload.content_type
            )
            file_hash = digest.hexdigest()
            stage = "RESERVING"
            await asyncio.to_thread(self._reserve, context, document_id, filename, mime, size, file_hash)
            document_dir = user_root / document_id
            document_dir.mkdir(parents=True, exist_ok=False)
            final_path = document_dir / "original-file"
            os.replace(staging, final_path)
            self._set_status(document_id, "PROCESSING")
            stage = "PARSING"
            sections = await asyncio.to_thread(self._parser.parse, final_path, filename)
            stage = "CHUNKING"
            drafts = await asyncio.to_thread(self._chunker.chunk_sections, sections)
            if not drafts:
                code = "SCANNED_PDF_REQUIRES_OCR" if filename.casefold().endswith(".pdf") else "DOCUMENT_HAS_NO_TEXT"
                raise ServiceError(422, code, "Tài liệu không có văn bản có thể lập chỉ mục.")
            chunks = self._to_chunks(document_id, context, filename, file_hash, drafts)
            page_values = {draft.page_number for draft in drafts if draft.page_number is not None}
            slide_values = {draft.slide_number for draft in drafts if draft.slide_number is not None}
            page_count = len(page_values or slide_values) or None
            stage = "INDEXING"
            record = await asyncio.to_thread(
                self._index_and_mark_ready,
                context.owner_id,
                document_id,
                chunks,
                page_count,
            )
            index_committed = True
            return self._dto(record)
        except IntegrityError as error:
            staging.unlink(missing_ok=True)
            raise ServiceError(409, "DUPLICATE_DOCUMENT", "Tài liệu này đã được tải lên.") from error
        except Exception as error:
            log_method = LOGGER.warning if isinstance(error, ServiceError) else LOGGER.exception
            log_method(
                "document_upload_failed trace_id=%s document_id=%s owner=%s stage=%s error_type=%s code=%s",
                REQUEST_TRACE_ID.get(),
                document_id,
                context.safe_key[:12],
                stage,
                type(error).__name__,
                getattr(error, "code", "DOCUMENT_PROCESSING_FAILED"),
            )
            staging.unlink(missing_ok=True)
            shutil.rmtree(user_root / document_id, ignore_errors=True)
            self._mark_failed_if_exists(document_id, self._safe_error_code(error))
            if index_committed:
                await asyncio.to_thread(self._indexes.remove_document, context.owner_id, document_id)
            if isinstance(error, ServiceError):
                raise
            if isinstance(error, ValueError):
                code = "SCANNED_PDF_REQUIRES_OCR" if filename.casefold().endswith(".pdf") else "DOCUMENT_PARSE_FAILED"
                message = "PDF scan cần OCR trước khi lập chỉ mục." if code.startswith("SCANNED") else "Không thể đọc nội dung tài liệu."
                raise ServiceError(422, code, message) from error
            raise ServiceError(500, "DOCUMENT_PROCESSING_FAILED", "Không thể xử lý tài liệu.") from error
        finally:
            await upload.close()

    def list_documents(self, owner_id: str, page: int, size: int, status: str | None) -> UserDocumentListResponse:
        with self._database.session() as session:
            conditions = [DocumentRecord.owner_id == owner_id]
            if status:
                conditions.append(DocumentRecord.status == status)
            else:
                conditions.append(DocumentRecord.status != "DELETED")
            total = session.scalar(select(func.count()).select_from(DocumentRecord).where(*conditions)) or 0
            records = session.scalars(
                select(DocumentRecord)
                .where(*conditions)
                .order_by(DocumentRecord.created_at.desc(), DocumentRecord.id.desc())
                .offset((page - 1) * size)
                .limit(size)
            ).all()
            return UserDocumentListResponse(
                items=[self._dto(record) for record in records],
                pagination=PaginationDto(
                    page=page,
                    size=size,
                    totalItems=total,
                    totalPages=math.ceil(total / size) if total else 0,
                ),
            )

    def get(self, owner_id: str, document_id: str, *, include_deleted: bool = False) -> UserDocumentDto:
        record = self._owned_record(owner_id, document_id)
        if record.status == "DELETED" and not include_deleted:
            raise self._not_found()
        return self._dto(record)

    def ready_ids(self, owner_id: str, requested: list[str] | None = None) -> set[str]:
        with self._database.session() as session:
            values = set(session.scalars(
                select(DocumentRecord.id).where(
                    DocumentRecord.owner_id == owner_id,
                    DocumentRecord.status == "READY",
                )
            ).all())
        if requested is None:
            return values
        selection = set(requested)
        if len(selection) != len(requested) or not selection.issubset(values):
            raise ServiceError(422, "INVALID_DOCUMENT_SELECTION", "Danh sách tài liệu không hợp lệ hoặc không thuộc người dùng.")
        return selection

    def rebuild_index(self, owner_id: str) -> None:
        with self._indexes.lock_for(owner_id):
            with self._database.session() as session:
                records = session.scalars(
                    select(DocumentRecord).where(
                        DocumentRecord.owner_id == owner_id,
                        DocumentRecord.status == "READY",
                    ).order_by(DocumentRecord.id)
                ).all()
            chunks: list[DocumentChunk] = []
            safe_key = context_safe_key(owner_id)
            for record in records:
                path = self._upload_root / safe_key / record.id / record.stored_filename
                if not path.is_file():
                    raise ServiceError(409, "USER_INDEX_REBUILD_REQUIRED", "Thiếu tệp nguồn để dựng lại chỉ mục người dùng.")
                try:
                    sections = self._parser.parse(path, record.original_filename)
                    drafts = self._chunker.chunk_sections(sections)
                except ValueError as error:
                    raise ServiceError(409, "USER_INDEX_REBUILD_REQUIRED", "Không thể dựng lại chỉ mục người dùng.") from error
                context = UserContext(owner_id, safe_key, record.classroom_id)
                chunks.extend(self._to_chunks(
                    record.id, context, record.original_filename, record.file_hash, drafts
                ))
            self._indexes.replace_all(owner_id, chunks)

    def delete(self, owner_id: str, document_id: str) -> None:
        record = self._owned_record(owner_id, document_id)
        if record.status == "DELETED":
            return
        with self._database.session() as session:
            current = session.get(DocumentRecord, document_id)
            assert current is not None
            current.status = "DELETED"
            current.updated_at = datetime.now(timezone.utc)
            session.commit()
        # Authorization filtering already excludes the record before index cleanup.
        try:
            self._indexes.remove_document(owner_id, document_id)
        except Exception:
            # DB authorization filter removes the document immediately; a later
            # search will detect the stale manifest and rebuild it.
            pass
        shutil.rmtree(self._upload_root / context_safe_key(owner_id) / document_id, ignore_errors=True)

    def _reserve(self, context: UserContext, document_id: str, filename: str, mime: str, size: int, file_hash: str) -> None:
        with self._indexes.lock_for(context.owner_id), self._database.session() as session:
            count, used = session.execute(
                select(func.count(), func.coalesce(func.sum(DocumentRecord.file_size), 0)).where(
                    DocumentRecord.owner_id == context.owner_id,
                    DocumentRecord.status.in_(ACTIVE_DOCUMENT_STATUSES),
                )
            ).one()
            if count >= self._max_documents:
                raise ServiceError(409, "DOCUMENT_QUOTA_EXCEEDED", "Đã đạt số tài liệu tối đa của tài khoản.")
            if used + size > self._max_storage_bytes:
                raise ServiceError(409, "STORAGE_QUOTA_EXCEEDED", "Đã vượt dung lượng lưu trữ của tài khoản.")
            session.add(DocumentRecord(
                id=document_id,
                owner_id=context.owner_id,
                classroom_id=context.classroom_id,
                source_type="USER_UPLOAD",
                original_filename=filename,
                stored_filename="original-file",
                mime_type=mime,
                file_size=size,
                file_hash=file_hash,
                status="UPLOADED",
            ))
            session.commit()

    def _set_status(self, document_id: str, status: str) -> None:
        with self._database.session() as session:
            record = session.get(DocumentRecord, document_id)
            if record is None:
                raise RuntimeError("document reservation missing")
            record.status = status
            record.updated_at = datetime.now(timezone.utc)
            session.commit()

    def _mark_ready(self, document_id: str, page_count: int | None, chunk_count: int) -> DocumentRecord:
        with self._database.session() as session:
            record = session.get(DocumentRecord, document_id)
            if record is None:
                raise RuntimeError("document reservation missing")
            now = datetime.now(timezone.utc)
            record.status = "READY"
            record.page_count = page_count
            record.chunk_count = chunk_count
            record.error_message = None
            record.indexed_at = now
            record.updated_at = now
            session.commit()
            return record

    def _index_and_mark_ready(
        self,
        owner_id: str,
        document_id: str,
        chunks: list[DocumentChunk],
        page_count: int | None,
    ) -> DocumentRecord:
        with self._indexes.lock_for(owner_id):
            self._indexes.replace_document(owner_id, document_id, chunks)
            try:
                return self._mark_ready(document_id, page_count, len(chunks))
            except Exception:
                self._indexes.remove_document(owner_id, document_id)
                raise

    def _mark_failed_if_exists(self, document_id: str, error_code: str) -> None:
        with self._database.session() as session:
            record = session.get(DocumentRecord, document_id)
            if record is not None and record.status != "READY":
                record.status = "FAILED"
                record.error_message = error_code
                record.updated_at = datetime.now(timezone.utc)
                session.commit()

    def _owned_record(self, owner_id: str, document_id: str) -> DocumentRecord:
        with self._database.session() as session:
            record = session.scalar(select(DocumentRecord).where(
                DocumentRecord.id == document_id,
                DocumentRecord.owner_id == owner_id,
            ))
            if record is None:
                raise self._not_found()
            session.expunge(record)
            return record

    @staticmethod
    def _not_found() -> ServiceError:
        return ServiceError(404, "DOCUMENT_NOT_FOUND", "Không tìm thấy tài liệu.")

    @staticmethod
    def _safe_error_code(error: Exception) -> str:
        return error.code if isinstance(error, ServiceError) else "DOCUMENT_PROCESSING_FAILED"

    @staticmethod
    def _to_chunks(document_id: str, context: UserContext, filename: str, file_hash: str, drafts: list[Any]) -> list[DocumentChunk]:
        namespace = uuid.UUID(document_id)
        created_at = utc_now_iso()
        return [DocumentChunk(
            chunk_id=str(uuid.uuid5(namespace, f"{file_hash}:{index}:{draft.page_number}:{draft.slide_number}")),
            document_id=document_id,
            document_type="USER_UPLOAD",
            filename=filename,
            relative_path=filename,
            file_hash=file_hash,
            page_number=draft.page_number,
            chunk_index=index,
            heading=draft.heading,
            text=draft.text,
            created_at=created_at,
            owner_id=context.owner_id,
            classroom_id=context.classroom_id,
            source_type="USER_UPLOAD",
            slide_number=draft.slide_number,
        ) for index, draft in enumerate(drafts)]

    @staticmethod
    def _dto(record: DocumentRecord) -> UserDocumentDto:
        return UserDocumentDto(
            id=record.id,
            classroomId=record.classroom_id,
            filename=record.original_filename,
            mimeType=record.mime_type,
            size=record.file_size,
            hash=record.file_hash,
            status=record.status,
            pageCount=record.page_count,
            chunkCount=record.chunk_count,
            error=record.error_message,
            createdAt=record.created_at,
            updatedAt=record.updated_at,
            indexedAt=record.indexed_at,
        )


def context_safe_key(owner_id: str) -> str:
    from app.models.user_context import safe_user_key
    return safe_user_key(owner_id)
