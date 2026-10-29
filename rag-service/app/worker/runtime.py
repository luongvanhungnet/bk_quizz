from functools import lru_cache
from threading import Lock, Timer

from app.core.config import Settings
from app.db.database import Database
from app.models.user_context import safe_user_key
from app.services.async_document_service import AsyncDocumentProcessor
from app.services.cache_redis import create_cache_redis
from app.services.chunking_service import ChunkingService
from app.services.document_object_storage import create_document_object_storage
from app.services.document_parser import DocumentParser
from app.services.embedding_service import EmbeddingService
from app.services.gemini_math_vision import GeminiMathVisionService
from app.services.indexing_job_service import IndexingJobService
from app.services.qdrant_vector_store import build_qdrant_client
from app.services.upload_validation import UploadValidator
from app.services.user_document_service import UserDocumentService
from app.services.user_index_manager import UserIndexManager
from app.services.vector_store_factory import create_vector_store

_embedding: EmbeddingService | None = None
_release_timer: Timer | None = None
_release_lock = Lock()


@lru_cache
def worker_runtime() -> tuple[AsyncDocumentProcessor, IndexingJobService, Settings]:
    global _embedding
    settings = Settings()
    database = Database.from_settings(settings)
    database.validate_migrated()
    embedding = EmbeddingService(
        settings.embedding_model,
        settings.query_embedding_cache_size,
        backend=settings.embedding_backend,
        precision=settings.embedding_precision,
        onnx_model_path=settings.embedding_onnx_model_path,
    )
    _embedding = embedding
    qdrant_client = (
        build_qdrant_client(settings)
        if settings.vector_store_backend == "qdrant"
        else None
    )
    object_storage = create_document_object_storage(settings)
    cache_redis_client = create_cache_redis(settings)
    document_staging_root = (
        settings.document_staging_dir
        if settings.document_storage_backend == "r2"
        else settings.user_upload_dir
    )
    indexes = UserIndexManager(
        settings.user_index_dir, embedding, settings.embedding_model,
        settings.rag_min_score, lambda: None, settings.cache_redis_url,
        app_env=settings.app_env,
        lock_mode=settings.index_lock_mode,
        redis_connect_timeout_seconds=settings.redis_connect_timeout_seconds,
        redis_socket_timeout_seconds=settings.redis_socket_timeout_seconds,
        redis_fallback_cooldown_seconds=settings.index_lock_fallback_cooldown_seconds,
        redis_client=cache_redis_client,
        store_factory=(
            lambda owner_id: create_vector_store(
                settings=settings,
                database=database,
                embedding_service=embedding,
                namespace=f"user:{owner_id}",
                faiss_directory=settings.user_index_dir / safe_user_key(owner_id),
                qdrant_client=qdrant_client,
            )
        )
        if settings.vector_store_backend == "qdrant"
        else None,
    )
    documents = UserDocumentService(
        database=database, upload_root=settings.user_upload_dir,
        max_upload_bytes=settings.max_upload_size_mb * 1024 * 1024,
        max_documents=settings.max_documents_per_user,
        max_storage_bytes=settings.max_storage_mb_per_user * 1024 * 1024,
        parser=DocumentParser(math_vision=GeminiMathVisionService(settings, database) if settings.math_vision_enabled else None),
        chunker=ChunkingService(settings.chunk_size_chars, settings.chunk_overlap_chars),
        index_manager=indexes, validator=UploadValidator(),
        object_storage=object_storage, staging_root=document_staging_root,
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
