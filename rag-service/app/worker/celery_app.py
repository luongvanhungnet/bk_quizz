from celery import Celery

from app.core.config import Settings
from app.worker import heartbeat as _heartbeat  # noqa: F401
from app.worker import metrics as _metrics  # noqa: F401

settings = Settings()
celery_app = Celery("bkquiz-rag", broker=settings.redis_url)
celery_app.conf.update(
    task_default_queue=settings.celery_queue,
    worker_pool=settings.celery_worker_pool,
    worker_concurrency=settings.celery_worker_concurrency,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    beat_schedule={
        "recover-stale-indexing-jobs": {
            "task": "rag.recover_stale_jobs",
            "schedule": 60.0,
            "options": {"expires": 55},
        },
        "reconcile-pending-indexing-jobs": {
            "task": "rag.reconcile_pending_jobs",
            "schedule": 60.0,
            "options": {"expires": 55},
        },
    },
    imports=("app.worker.tasks",),
)
