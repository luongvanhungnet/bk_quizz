from fastapi.testclient import TestClient

from app.main import create_app
from app.services.embedding_service import EmbeddingService
from app.worker.celery_app import celery_app
from app.worker.heartbeat import WorkerHeartbeat


def test_worker_uses_single_process_solo_pool() -> None:
    assert celery_app.conf.worker_pool == "solo"
    assert celery_app.conf.worker_concurrency == 1


def test_worker_heartbeat_expires_after_ttl() -> None:
    class Redis:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}

        def set(self, key: str, value: str, *, ex: int) -> None:
            self.values[key] = f"{value}:{ex}"

        def exists(self, key: str) -> int:
            return int(key in self.values)

        def delete(self, key: str) -> None:
            self.values.pop(key, None)

    redis = Redis()
    heartbeat = WorkerHeartbeat(redis, "rag:worker:heartbeat", ttl_seconds=30)
    heartbeat.touch("worker-a")
    assert heartbeat.is_alive() is True
    heartbeat.clear()
    assert heartbeat.is_alive() is False


def test_readiness_reports_celery_worker_down(settings) -> None:
    class Redis:
        def ping(self) -> bool:
            return True

        def llen(self, _: str) -> int:
            return 3

        def exists(self, _: str) -> int:
            return 0

    with TestClient(create_app(settings=settings)) as client:
        client.app.state.redis_client = Redis()
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["celeryWorker"] == "DOWN"


def test_embedding_model_can_be_released_when_worker_becomes_idle() -> None:
    embedding = EmbeddingService("test-model")
    embedding._model = object()

    embedding.unload()

    assert embedding.is_loaded is False
