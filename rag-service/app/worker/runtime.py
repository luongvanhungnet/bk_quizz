from functools import lru_cache
from threading import Lock, Timer

from app.core.config import Settings
from app.db.database import Database
from app.services.async_document_service import AsyncDocumentProcessor
from app.services.chunking_service import ChunkingService
from app.services.document_parser import DocumentParser
from app.services.embedding_service import EmbeddingService
from app.services.gemini_math_vision import GeminiMathVisionService
from app.services.indexing_job_service import IndexingJobService
from app.services.upload_validation import UploadValidator
from app.services.user_document_service import UserDocumentService
from app.services.user_index_manager import UserIndexManager

_embedding: EmbeddingService | None = None
_release_timer: Timer | None = None
_release_lock = Lock()


@lru_cache
def worker_runtime() -> tuple[AsyncDocumentProcessor, IndexingJobService, Settings]:
    global _embedding
    settings = Settings()
    database = Database(settings.database_url)
    database.validate_migrated()
    embedding = EmbeddingService(
        settings.embedding_model,
        settings.query_embedding_cache_size,
        backend=settings.embedding_backend,
        precision=settings.embedding_precision,
        onnx_model_path=settings.embedding_onnx_model_path,
    )
    _embedding = embedding
    indexes = UserIndexManager(
        settings.user_index_dir, embedding, settings.embedding_model,
        settings.rag_min_score, lambda: None, settings.redis_url,
        app_env=settings.app_env,
        lock_mode=settings.index_lock_mode,
        redis_connect_timeout_seconds=settings.redis_connect_timeout_seconds,
        redis_socket_timeout_seconds=settings.redis_socket_timeout_seconds,
        redis_fallback_cooldown_seconds=settings.index_lock_fallback_cooldown_seconds,
    )
    documents = UserDocumentService(
        database=database, upload_root=settings.user_upload_dir,
        max_upload_bytes=settings.max_upload_size_mb * 1024 * 1024,
        max_documents=settings.max_documents_per_user,
        max_storage_bytes=settings.max_storage_mb_per_user * 1024 * 1024,
        parser=DocumentParser(math_vision=GeminiMathVisionService(settings, database) if settings.math_vision_enabled else None),
        chunker=ChunkingService(settings.chunk_size_chars, settings.chunk_overlap_chars),
        index_manager=indexes, validator=UploadValidator(),
    )
    jobs = IndexingJobService(database, max_attempts=settings.indexing_job_max_attempts)
    return AsyncDocumentProcessor(documents, jobs), jobs, settings


def cancel_worker_model_release() -> None:
    global _release_timer
    with _release_lock:
        if _release_timer is not None:
            _release_timer.cancel()
            _release_timer = None


def schedule_worker_model_release(idle_seconds: int) -> None:
    global _release_timer

    def release() -> None:
        global _release_timer
        with _release_lock:
            if _embedding is not None:
                _embedding.unload()
            _release_timer = None

    with _release_lock:
        if _release_timer is not None:
            _release_timer.cancel()
        _release_timer = Timer(idle_seconds, release)
        _release_timer.daemon = True
        _release_timer.start()
