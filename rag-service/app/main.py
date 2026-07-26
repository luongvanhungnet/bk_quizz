import asyncio
import logging
import os
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any, AsyncIterator
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.responses import Response as FastApiResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from redis import Redis

from app.api.routes import chat, evaluation, health, operations, rag, system_documents, user_documents, user_rag, v2
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.db.database import Database
from app.services.async_document_service import AsyncDocumentProcessor, AsyncDocumentService
from app.services.chunking_service import ChunkingService
from app.services.context_builder import ContextBuilder
from app.services.document_parser import DocumentParser
from app.services.embedding_service import EmbeddingService
from app.services.evaluation_service import RetrievalEvaluationService
from app.services.gemini_service import GeminiService
from app.services.grounded_answer_service import GroundedAnswerService
from app.services.hybrid_retrieval import HybridRetrievalService
from app.services.indexing_job_service import IndexingJobService
from app.services.job_dispatcher import CeleryJobDispatcher
from app.services.query_rewrite_service import QueryRewriteService
from app.services.rag_pipeline_service import RagPipelineService
from app.services.rag_service import RagService
from app.services.rate_limiter import NoopRateLimiter, RedisRateLimiter
from app.services.reranker_service import RerankerService
from app.services.retrieval_service import RetrievalService
from app.services.system_indexing_service import SystemIndexingService
from app.services.upload_validation import UploadValidator
from app.services.user_document_service import UserDocumentService
from app.services.user_index_manager import UserIndexManager
from app.services.user_rag_service import UserRagService
from app.services.vector_store import VectorStore

HTTP_REQUESTS = Counter(
    "rag_http_requests_total", "HTTP requests", ["method", "path", "status"]
)
HTTP_LATENCY = Histogram(
    "rag_http_request_duration_seconds", "HTTP request latency", ["method", "path"]
)


def create_app(
    *,
    settings: Settings | None = None,
    gemini_service: Any | None = None,
    embedding_service: Any | None = None,
    vector_store: Any | None = None,
    system_indexing_service: Any | None = None,
    retrieval_service: Any | None = None,
    rag_service: Any | None = None,
    database: Any | None = None,
    user_document_service: Any | None = None,
    user_index_manager: Any | None = None,
    user_rag_service: Any | None = None,
    reranker_service: Any | None = None,
    rag_pipeline_service: Any | None = None,
    job_dispatcher: Any | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    injected_service = gemini_service

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        owned_service: GeminiService | None = None
        if injected_service is not None:
            application.state.gemini_service = injected_service
        elif resolved_settings.gemini_api_key:
            owned_service = GeminiService(resolved_settings)
            application.state.gemini_service = owned_service
        else:
            application.state.gemini_service = None
        embedding = embedding_service or EmbeddingService(
            resolved_settings.embedding_model,
            resolved_settings.query_embedding_cache_size,
            backend=resolved_settings.embedding_backend,
            precision=resolved_settings.embedding_precision,
            onnx_model_path=resolved_settings.embedding_onnx_model_path,
        )
        os.environ.setdefault("OMP_NUM_THREADS", str(resolved_settings.rag_cpu_threads))
        os.environ.setdefault("MKL_NUM_THREADS", str(resolved_settings.rag_cpu_threads))
        try:
            import faiss

            faiss.omp_set_num_threads(resolved_settings.rag_cpu_threads)
        except (ImportError, AttributeError):
            pass
        if resolved_settings.app_env != "test" and resolved_settings.rag_preload_embedding:
            await asyncio.to_thread(lambda: embedding.dimension)
        store = vector_store or VectorStore(
            resolved_settings.system_index_dir,
            resolved_settings.embedding_model,
        )
        indexing = system_indexing_service or SystemIndexingService(
            documents_dir=resolved_settings.system_documents_dir,
            parser=DocumentParser(),
            chunker=ChunkingService(
                resolved_settings.chunk_size_chars,
                resolved_settings.chunk_overlap_chars,
            ),
            embedding_service=embedding,
            vector_store=store,
        )
        retrieval = retrieval_service or RetrievalService(
            embedding,
            store,
            resolved_settings.rag_min_score,
        )
        reranker = reranker_service or RerankerService(
            resolved_settings.reranker_model,
            resolved_settings.reranker_enabled,
        )
        if resolved_settings.app_env != "test" and not resolved_settings.rag_low_memory_mode:
            await asyncio.to_thread(reranker.warmup)
        hybrid = HybridRetrievalService(
            embedding_service=embedding,
            reranker=reranker,
            hybrid_enabled=resolved_settings.hybrid_enabled,
            vector_candidates=resolved_settings.hybrid_vector_candidates,
            bm25_candidates=resolved_settings.hybrid_bm25_candidates,
            rrf_k=resolved_settings.hybrid_rrf_k,
            rerank_candidates=resolved_settings.rerank_candidates,
            rerank_min_candidates=resolved_settings.rerank_min_candidates,
            min_vector_score=resolved_settings.rag_min_score,
            cache_size=resolved_settings.retrieval_cache_size,
            cache_ttl_seconds=resolved_settings.retrieval_cache_ttl_seconds,
        )
        pipeline = rag_pipeline_service or RagPipelineService(
            hybrid,
            QueryRewriteService(resolved_settings.query_rewrite_enabled),
            ContextBuilder(resolved_settings.rag_max_context_chars),
            GroundedAnswerService(),
        )
        store.add_commit_listener(hybrid.clear_cache)
        application.state.embedding_service = embedding
        application.state.vector_store = store
        application.state.system_indexing_service = indexing
        application.state.retrieval_service = retrieval
        application.state.rag_service = rag_service or RagService(retrieval)
        application.state.reranker_service = reranker
        application.state.hybrid_retrieval_service = hybrid
        application.state.rag_pipeline_service = pipeline
        owned_database = database is None
        db = database or Database(
            resolved_settings.database_url,
            create_for_tests=resolved_settings.app_env == "test",
        )
        if resolved_settings.app_env != "test":
            db.validate_migrated()
        indexes = user_index_manager or UserIndexManager(
            resolved_settings.user_index_dir,
            embedding,
            resolved_settings.embedding_model,
            resolved_settings.rag_min_score,
            hybrid.clear_cache,
            resolved_settings.redis_url,
            app_env=resolved_settings.app_env,
            lock_mode=resolved_settings.index_lock_mode,
            redis_connect_timeout_seconds=resolved_settings.redis_connect_timeout_seconds,
            redis_socket_timeout_seconds=resolved_settings.redis_socket_timeout_seconds,
            redis_fallback_cooldown_seconds=resolved_settings.index_lock_fallback_cooldown_seconds,
        )
        documents = user_document_service or UserDocumentService(
            database=db,
            upload_root=resolved_settings.user_upload_dir,
            max_upload_bytes=resolved_settings.max_upload_size_mb * 1024 * 1024,
            max_documents=resolved_settings.max_documents_per_user,
            max_storage_bytes=resolved_settings.max_storage_mb_per_user * 1024 * 1024,
            parser=DocumentParser(),
            chunker=ChunkingService(
                resolved_settings.chunk_size_chars,
                resolved_settings.chunk_overlap_chars,
            ),
            index_manager=indexes,
            validator=UploadValidator(),
        )
        application.state.database = db
        application.state.user_index_manager = indexes
        application.state.user_document_service = documents
        job_service = IndexingJobService(db, max_attempts=resolved_settings.indexing_job_max_attempts)
        processor = AsyncDocumentProcessor(documents, job_service)
        async_documents = AsyncDocumentService(
            database=db, documents=documents, jobs=job_service,
            upload_root=resolved_settings.user_upload_dir,
            max_upload_bytes=resolved_settings.max_upload_size_mb * 1024 * 1024,
            max_documents=resolved_settings.max_documents_per_user,
            max_storage_bytes=resolved_settings.max_storage_mb_per_user * 1024 * 1024,
            validator=UploadValidator(),
        )
        application.state.indexing_job_service = job_service
        application.state.async_document_processor = processor
        application.state.async_document_service = async_documents
        application.state.job_dispatcher = job_dispatcher or CeleryJobDispatcher()
        redis_client = Redis.from_url(
            resolved_settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=resolved_settings.redis_connect_timeout_seconds,
            socket_timeout=resolved_settings.redis_socket_timeout_seconds,
            health_check_interval=30,
        )
        application.state.redis_client = redis_client
        application.state.rate_limiter = (
            NoopRateLimiter() if resolved_settings.app_env == "test" else RedisRateLimiter(redis_client)
        )
        application.state.user_rag_service = user_rag_service or UserRagService(
            documents, indexes, store, pipeline
        )
        application.state.evaluation_service = RetrievalEvaluationService(
            application.state.user_rag_service, documents
        )
        try:
            yield
        finally:
            if owned_service is not None:
                await owned_service.close()
            if owned_database:
                db.dispose()
            redis_client.close()

    development = resolved_settings.app_env == "development"
    application = FastAPI(
        title=resolved_settings.app_name,
        version="2.0.0",
        docs_url="/docs" if development else None,
        redoc_url=None,
        openapi_url="/openapi.json" if development else None,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.gemini_service = injected_service
    application.state.embedding_service = embedding_service
    application.state.vector_store = vector_store
    application.state.system_indexing_service = system_indexing_service
    application.state.retrieval_service = retrieval_service
    application.state.rag_service = rag_service
    application.state.database = database
    application.state.user_index_manager = user_index_manager
    application.state.user_document_service = user_document_service
    application.state.user_rag_service = user_rag_service
    application.state.reranker_service = reranker_service
    application.state.rag_pipeline_service = rag_pipeline_service
    application.state.indexing_job_service = None
    application.state.async_document_processor = None
    application.state.async_document_service = None
    application.state.job_dispatcher = job_dispatcher
    application.state.redis_client = None
    application.state.rate_limiter = None
    application.state.logger = logging.getLogger("uvicorn.error")

    @application.middleware("http")
    async def request_trace_middleware(request: Request, call_next: Any) -> Response:
        request.state.trace_id = request.headers.get("X-Request-Id") or str(uuid4())
        from app.core.request_context import REQUEST_TRACE_ID
        from app.services.gemini_service import GEMINI_USER_CONTEXT

        trace_context_token = REQUEST_TRACE_ID.set(request.state.trace_id)
        gemini_context_token = GEMINI_USER_CONTEXT.set(request.headers.get("X-User-Id"))
        started = perf_counter()
        try:
            if request.url.path == "/api/v2/user-rag/ask":
                from app.models.user_context import normalize_identifier, safe_user_key

                raw_user = request.headers.get("X-User-Id")
                if raw_user:
                    owner = normalize_identifier(raw_user, field_name="user")
                    request.app.state.rate_limiter.check(
                        "ask", safe_user_key(owner), request.app.state.settings.ask_user_rpm
                    )
            response: Response = await call_next(request)
        finally:
            REQUEST_TRACE_ID.reset(trace_context_token)
            GEMINI_USER_CONTEXT.reset(gemini_context_token)
        response.headers["X-Request-Id"] = request.state.trace_id
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)
        HTTP_REQUESTS.labels(request.method, path, str(response.status_code)).inc()
        HTTP_LATENCY.labels(request.method, path).observe(perf_counter() - started)
        return response

    @application.get("/metrics", include_in_schema=False)
    def metrics() -> FastApiResponse:
        return FastApiResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    register_exception_handlers(application)
    application.include_router(health.router, prefix="/api/v1")
    application.include_router(chat.router, prefix="/api/v1")
    application.include_router(system_documents.router, prefix="/api/v1")
    application.include_router(rag.router, prefix="/api/v1")
    application.include_router(user_documents.router, prefix="/api/v1")
    application.include_router(user_rag.router, prefix="/api/v1")
    application.include_router(evaluation.router, prefix="/api/v1")
    application.include_router(v2.router, prefix="/api/v2")
    application.include_router(user_rag.router, prefix="/api/v2")
    application.include_router(operations.router)
    return application


app = create_app()
