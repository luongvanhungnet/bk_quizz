from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from prometheus_client import Gauge
from sqlalchemy import text

QUEUE_LENGTH = Gauge("rag_job_queue_length", "Indexing queue length when available")
DOCUMENTS = Gauge("rag_documents", "Documents by status", ["status"])
CHUNKS = Gauge("rag_chunks", "Ready document chunks")

router = APIRouter(tags=["operations"])


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "UP"}


@router.get("/health/startup")
def startup(request: Request) -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        with request.app.state.database.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = "UP"
    except Exception:
        checks["database"] = "DOWN"
    try:
        request.app.state.document_object_storage.ping()
        checks["storage"] = "UP"
    except Exception:
        checks["storage"] = "DOWN"
    try:
        if request.app.state.settings.vector_store_backend == "qdrant":
            request.app.state.vector_store.ping()
        checks["vectorStore"] = "UP"
    except Exception:
        checks["vectorStore"] = "DOWN"
    checks["embedding"] = (
        "UP" if request.app.state.embedding_service is not None else "DOWN"
    )
    healthy = all(value == "UP" for value in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "UP" if healthy else "DOWN", "checks": checks},
    )


@router.get("/health/ready")
def ready(request: Request) -> JSONResponse:
    checks: dict[str, str] = {}
    queue_length = 0
    pending_jobs = 0
    running_jobs = 0
    oldest_pending_seconds = 0
    try:
        with request.app.state.database.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            job_stats = connection.execute(text(
                "SELECT "
                "COALESCE(SUM(CASE WHEN status='PENDING' THEN 1 ELSE 0 END), 0), "
                "COALESCE(SUM(CASE WHEN status='RUNNING' THEN 1 ELSE 0 END), 0), "
                "MIN(CASE WHEN status='PENDING' THEN created_at END) "
                "FROM indexing_jobs"
            )).one()
            pending_jobs = int(job_stats[0])
            running_jobs = int(job_stats[1])
            oldest_pending = job_stats[2]
            if oldest_pending is not None:
                if isinstance(oldest_pending, str):
                    oldest_pending = datetime.fromisoformat(oldest_pending)
                if oldest_pending.tzinfo is None:
                    oldest_pending = oldest_pending.replace(tzinfo=timezone.utc)
                oldest_pending_seconds = max(
                    0, int((datetime.now(timezone.utc) - oldest_pending).total_seconds())
                )
        checks["database"] = "UP"
    except Exception:
        checks["database"] = "DOWN"
    settings = request.app.state.settings
    try:
        request.app.state.redis_client.ping()
        checks["cacheRedis"] = "UP"
        if settings.job_dispatch_backend == "celery":
            queue_length = int(request.app.state.redis_client.llen(settings.celery_queue))
            checks["celeryWorker"] = (
                "UP"
                if request.app.state.redis_client.exists(settings.celery_worker_heartbeat_key)
                else "DOWN"
            )
    except Exception:
        checks["cacheRedis"] = "DOWN"
        if settings.job_dispatch_backend == "celery":
            checks["celeryWorker"] = "DOWN"
    if settings.job_dispatch_backend == "gcp":
        checks["pubsub"] = "UP" if request.app.state.job_dispatcher is not None else "DOWN"
        checks["cloudTasks"] = "UP" if request.app.state.cloud_tasks_enqueuer is not None else "DOWN"
        checks["cloudScheduler"] = "UP"
    QUEUE_LENGTH.set(queue_length)
    try:
        request.app.state.document_object_storage.ping()
        checks["storage"] = "UP"
    except Exception:
        checks["storage"] = "DOWN"
    try:
        if settings.vector_store_backend == "qdrant":
            request.app.state.vector_store.ping()
        checks["vectorStore"] = "UP"
    except Exception:
        checks["vectorStore"] = "DOWN"
    embedding = request.app.state.embedding_service
    checks["embedding"] = "UP" if embedding is not None else "DOWN"
    checks["gemini"] = "UP" if settings.gemini_api_key else "DOWN"
    try:
        with request.app.state.database.session() as session:
            counts = session.execute(text("SELECT status, COUNT(*) FROM documents GROUP BY status")).all()
            for document_status, count in counts:
                DOCUMENTS.labels(str(document_status)).set(count)
            chunk_count = session.execute(text("SELECT COALESCE(SUM(chunk_count), 0) FROM documents WHERE status='READY'"))
            CHUNKS.set(chunk_count.scalar_one())
    except Exception:
        checks["database"] = "DOWN"
    healthy = all(value == "UP" for value in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "UP" if healthy else "DOWN",
            "checks": checks,
            "databaseBackend": request.app.state.database.backend,
            "vectorStoreBackend": settings.vector_store_backend,
            "queueLength": queue_length,
            "pendingJobs": pending_jobs,
            "runningJobs": running_jobs,
            "oldestPendingSeconds": oldest_pending_seconds,
            "cacheRedisProvider": settings.cache_redis_provider,
        },
    )
