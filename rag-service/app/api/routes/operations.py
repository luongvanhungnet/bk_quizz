import shutil
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from prometheus_client import Gauge
from sqlalchemy import text

QUEUE_LENGTH = Gauge("rag_celery_queue_length", "Celery indexing queue length")
DOCUMENTS = Gauge("rag_documents", "Documents by status", ["status"])
CHUNKS = Gauge("rag_chunks", "Ready document chunks")

router = APIRouter(tags=["operations"])


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "UP"}


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
        checks["sqlite"] = "UP"
    except Exception:
        checks["sqlite"] = "DOWN"
    try:
        request.app.state.redis_client.ping()
        queue_length = int(request.app.state.redis_client.llen(request.app.state.settings.celery_queue))
        QUEUE_LENGTH.set(queue_length)
        checks["redis"] = "UP"
        checks["celeryWorker"] = (
            "UP"
            if request.app.state.redis_client.exists(
                request.app.state.settings.celery_worker_heartbeat_key
            )
            else "DOWN"
        )
    except Exception:
        checks["redis"] = "DOWN"
        checks["celeryWorker"] = "DOWN"
    settings = request.app.state.settings
    try:
        for path in (settings.user_upload_dir, settings.user_index_dir):
            path.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(path).free < settings.minimum_free_disk_mb * 1024 * 1024:
                raise OSError("low disk")
        checks["storage"] = "UP"
    except Exception:
        checks["storage"] = "DOWN"
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
        checks["sqlite"] = "DOWN"
    healthy = all(value == "UP" for value in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "UP" if healthy else "DOWN",
            "checks": checks,
            "queueLength": queue_length,
            "pendingJobs": pending_jobs,
            "runningJobs": running_jobs,
            "oldestPendingSeconds": oldest_pending_seconds,
        },
    )
