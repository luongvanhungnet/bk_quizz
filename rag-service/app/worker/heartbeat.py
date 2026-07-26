import logging
import threading
from typing import Any

from celery.signals import worker_ready, worker_shutdown
from redis import Redis

from app.core.config import Settings

logger = logging.getLogger(__name__)
_stop = threading.Event()
_thread: threading.Thread | None = None
_heartbeat: "WorkerHeartbeat | None" = None


class WorkerHeartbeat:
    def __init__(self, redis_client: Any, key: str, *, ttl_seconds: int) -> None:
        self._redis = redis_client
        self._key = key
        self._ttl_seconds = ttl_seconds

    def touch(self, worker_id: str) -> None:
        self._redis.set(self._key, worker_id, ex=self._ttl_seconds)

    def is_alive(self) -> bool:
        return bool(self._redis.exists(self._key))

    def clear(self) -> None:
        self._redis.delete(self._key)


def _heartbeat_loop(heartbeat: WorkerHeartbeat, worker_id: str, interval_seconds: int) -> None:
    while not _stop.is_set():
        try:
            heartbeat.touch(worker_id)
        except Exception as error:
            logger.warning("RAG worker heartbeat failed error=%s", type(error).__name__)
        _stop.wait(interval_seconds)


@worker_ready.connect
def start_worker_heartbeat(sender: Any = None, **_: object) -> None:
    global _heartbeat, _thread
    settings = Settings()
    redis_client = Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=settings.redis_connect_timeout_seconds,
        socket_timeout=settings.redis_socket_timeout_seconds,
        decode_responses=True,
    )
    _heartbeat = WorkerHeartbeat(
        redis_client,
        settings.celery_worker_heartbeat_key,
        ttl_seconds=settings.celery_worker_heartbeat_ttl_seconds,
    )
    worker_id = getattr(sender, "hostname", None) or "rag-worker"
    _stop.clear()
    _heartbeat.touch(worker_id)
    _thread = threading.Thread(
        target=_heartbeat_loop,
        args=(_heartbeat, worker_id, settings.celery_worker_heartbeat_interval_seconds),
        name="rag-worker-heartbeat",
        daemon=True,
    )
    _thread.start()
    logger.info(
        "RAG worker ready pool=%s concurrency=%s hostname=%s queue=%s heartbeatTtl=%ss",
        settings.celery_worker_pool,
        settings.celery_worker_concurrency,
        worker_id,
        settings.celery_queue,
        settings.celery_worker_heartbeat_ttl_seconds,
    )


@worker_shutdown.connect
def stop_worker_heartbeat(**_: object) -> None:
    _stop.set()
    if _heartbeat is not None:
        try:
            _heartbeat.clear()
        except Exception as error:
            logger.warning("RAG worker heartbeat cleanup failed error=%s", type(error).__name__)
