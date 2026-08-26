import random

from celery import Task
from redis import Redis

from app.core.exceptions import ServiceError
from app.worker.celery_app import celery_app
from app.worker.runtime import (
    cancel_worker_model_release,
    schedule_worker_model_release,
    worker_runtime,
)


@celery_app.task(bind=True, name="rag.process_indexing_job", max_retries=3)
def process_indexing_job(self: Task, job_id: str) -> None:
    processor, jobs, settings = worker_runtime()
    cancel_worker_model_release()
    try:
        processor.process(job_id)
    except ServiceError as error:
        if not error.retryable and error.status_code < 500:
            return
        raw = jobs.raw(job_id)
        if raw is None or self.request.retries >= self.max_retries:
            return
        owner_id, _, _ = raw
        jobs.retry(owner_id, job_id)
        countdown = min(60, (2 ** self.request.retries) + random.uniform(0, 1))
        raise self.retry(exc=error, countdown=countdown)
    finally:
        if settings.rag_low_memory_mode:
            schedule_worker_model_release(settings.worker_model_idle_seconds)


@celery_app.task(name="rag.recover_stale_jobs")
def recover_stale_jobs() -> int:
    _, jobs, settings = worker_runtime()
    recovered = jobs.recover_stale(settings.indexing_job_stale_seconds)
    for job_id in recovered:
        process_indexing_job.delay(job_id)
    return len(recovered)


@celery_app.task(name="rag.reconcile_pending_jobs")
def reconcile_pending_jobs() -> int:
    _, jobs, settings = worker_runtime()
    redis_client = Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=settings.redis_connect_timeout_seconds,
        socket_timeout=settings.redis_socket_timeout_seconds,
        decode_responses=True,
    )
    try:
        if not redis_client.exists(settings.celery_worker_heartbeat_key):
            return 0
        dispatched = 0
        for job_id in jobs.pending_for_reconciliation(settings.pending_job_reconcile_seconds):
            marker = f"rag:reconcile:{job_id}"
            if redis_client.set(marker, "1", nx=True, ex=max(60, settings.pending_job_reconcile_seconds * 4)):
                process_indexing_job.delay(job_id)
                dispatched += 1
        return dispatched
    finally:
        redis_client.close()
