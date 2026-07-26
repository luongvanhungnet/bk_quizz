from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.main import create_app
from app.models.document import DocumentChunk
from app.services.rate_limiter import RedisRateLimiter
from app.services.user_index_manager import UserIndexManager


class Embedding:
    model_name = "test-model"
    dimension = 2

    def encode_documents(self, values: list[str]) -> np.ndarray:
        return np.asarray([[1.0, 0.0] for _ in values], dtype=np.float32)

    def encode_query(self, value: str) -> np.ndarray:
        return self.encode_documents([value])


class BrokenAcquireLock:
    def acquire(self, blocking: bool = True) -> bool:
        raise RedisConnectionError("redis offline")


class BusyLock:
    def acquire(self, blocking: bool = True) -> bool:
        return False


class ReleaseFailureLock:
    def acquire(self, blocking: bool = True) -> bool:
        return True

    def owned(self) -> bool:
        return True

    def release(self) -> None:
        raise RedisConnectionError("lost redis after commit")


class FakeRedis:
    def __init__(self, lock: object) -> None:
        self.value = lock
        self.calls = 0

    def lock(self, *_: object, **__: object) -> object:
        self.calls += 1
        return self.value


class UnavailableRedis:
    def incr(self, _: str) -> int:
        raise RedisConnectionError("redis offline")

    def ping(self) -> bool:
        raise RedisConnectionError("redis offline")


def chunk() -> DocumentChunk:
    return DocumentChunk(
        chunk_id="chunk-1", document_id="doc-1", document_type="USER_UPLOAD",
        filename="test.txt", relative_path="test.txt", file_hash="a" * 64,
        page_number=None, chunk_index=0, heading=None, text="BKQuiz RAG",
        created_at="2026-07-19T00:00:00Z", owner_id="user-a",
        source_type="USER_UPLOAD",
    )


def manager(tmp_path: Path, redis: FakeRedis, *, env: str, mode: str = "auto") -> UserIndexManager:
    return UserIndexManager(
        tmp_path, Embedding(), "test-model", -1,
        redis_url="redis://unused", app_env=env, lock_mode=mode,
        redis_client=redis, redis_fallback_cooldown_seconds=30,
    )


def test_development_falls_back_to_local_lock_and_uses_cooldown(tmp_path: Path) -> None:
    redis = FakeRedis(BrokenAcquireLock())
    indexes = manager(tmp_path, redis, env="development")

    indexes.replace_document("user-a", "doc-1", [chunk()])
    indexes.replace_document("user-a", "doc-1", [chunk()])

    assert indexes.snapshot_for("user-a") is not None
    assert redis.calls == 1


def test_production_returns_specific_retryable_error_when_redis_is_down(tmp_path: Path) -> None:
    indexes = manager(tmp_path, FakeRedis(BrokenAcquireLock()), env="production")

    with pytest.raises(ServiceError) as raised:
        indexes.replace_document("user-a", "doc-1", [chunk()])

    assert raised.value.status_code == 503
    assert raised.value.code == "INDEX_LOCK_UNAVAILABLE"
    assert raised.value.retryable is True


def test_busy_distributed_lock_never_falls_back(tmp_path: Path) -> None:
    indexes = manager(tmp_path, FakeRedis(BusyLock()), env="development")

    with pytest.raises(ServiceError) as raised:
        indexes.replace_document("user-a", "doc-1", [chunk()])

    assert raised.value.status_code == 409
    assert raised.value.code == "INDEX_MUTATION_IN_PROGRESS"


def test_release_failure_does_not_undo_committed_snapshot(tmp_path: Path) -> None:
    indexes = manager(tmp_path, FakeRedis(ReleaseFailureLock()), env="production")

    indexes.replace_document("user-a", "doc-1", [chunk()])

    assert indexes.snapshot_for("user-a") is not None


def test_production_rejects_explicit_local_lock(settings: Settings) -> None:
    with pytest.raises(ValidationError):
        settings.model_copy(update={"app_env": "production", "index_lock_mode": "local"}).model_validate(
            {**settings.model_dump(), "app_env": "production", "index_lock_mode": "local"}
        )


def test_v1_upload_succeeds_with_development_fallback(settings: Settings, tmp_path: Path) -> None:
    embedding = Embedding()
    indexes = manager(tmp_path / "indexes", FakeRedis(BrokenAcquireLock()), env="development")
    app = create_app(
        settings=settings,
        embedding_service=embedding,
        user_index_manager=indexes,
    )
    headers = {"X-Internal-API-Key": "test-internal-key", "X-User-Id": "user-a"}

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/user-documents",
            headers=headers,
            files={"file": ("rag-test.txt", "RAG kết hợp retrieval và Gemini.", "text/plain")},
        )

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "READY"
    assert response.json()["chunkCount"] == 1


def test_v1_upload_preserves_production_index_lock_error(settings: Settings, tmp_path: Path) -> None:
    embedding = Embedding()
    indexes = manager(tmp_path / "indexes", FakeRedis(BrokenAcquireLock()), env="production")
    app = create_app(settings=settings, embedding_service=embedding, user_index_manager=indexes)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/user-documents",
            headers={"X-Internal-API-Key": "test-internal-key", "X-User-Id": "user-a"},
            files={"file": ("rag-test.txt", "RAG kết hợp retrieval và Gemini.", "text/plain")},
        )

    assert response.status_code == 503
    assert response.json()["code"] == "INDEX_LOCK_UNAVAILABLE"


def test_v2_redis_failure_is_specific_and_creates_no_document(settings: Settings) -> None:
    app = create_app(settings=settings, embedding_service=Embedding())
    headers = {"X-Internal-API-Key": "test-internal-key", "X-User-Id": "user-a"}

    with TestClient(app) as client:
        client.app.state.rate_limiter = RedisRateLimiter(UnavailableRedis())
        response = client.post(
            "/api/v2/user-documents",
            headers=headers,
            files={"file": ("rag-test.txt", "RAG test", "text/plain")},
        )
        documents = client.get("/api/v1/user-documents", headers=headers)

    assert response.status_code == 503
    assert response.json()["code"] == "RATE_LIMIT_STORE_UNAVAILABLE"
    assert documents.json()["items"] == []


def test_readiness_reports_redis_down(settings: Settings) -> None:
    with TestClient(create_app(settings=settings, embedding_service=Embedding())) as client:
        client.app.state.redis_client = UnavailableRedis()
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["redis"] == "DOWN"
