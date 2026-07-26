import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, RLock
from time import monotonic
from typing import Any

import numpy as np
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.exceptions import ServiceError
from app.models.document import DocumentChunk
from app.models.user_context import safe_user_key
from app.services.retrieval_service import RetrievalResult
from app.services.vector_store import VectorStore

LOGGER = logging.getLogger("uvicorn.error")


class UserIndexManager:
    def __init__(
        self,
        root: Path,
        embedding_service: Any,
        model_name: str,
        min_score: float,
        on_index_change: Any | None = None,
        redis_url: str | None = None,
        *,
        app_env: str = "test",
        lock_mode: str = "auto",
        redis_connect_timeout_seconds: float = 1,
        redis_socket_timeout_seconds: float = 2,
        redis_fallback_cooldown_seconds: int = 30,
        redis_client: Any | None = None,
    ) -> None:
        self._root = root
        self._embedding = embedding_service
        self._model_name = model_name
        self._min_score = min_score
        self._stores: dict[str, VectorStore] = {}
        self._user_locks: dict[str, RLock] = {}
        self._registry_lock = Lock()
        self._on_index_change = on_index_change
        self._allow_local_fallback = lock_mode == "auto" and app_env == "development"
        use_redis = lock_mode == "redis" or (lock_mode == "auto" and app_env != "test")
        self._redis_fallback_cooldown_seconds = redis_fallback_cooldown_seconds
        self._redis_unavailable_until = 0.0
        self._redis = redis_client if use_redis else None
        if self._redis is None and redis_url and use_redis:
            self._redis = Redis.from_url(
                redis_url,
                socket_connect_timeout=redis_connect_timeout_seconds,
                socket_timeout=redis_socket_timeout_seconds,
                health_check_interval=30,
            )

    def lock_for(self, owner_id: str) -> RLock:
        with self._registry_lock:
            return self._user_locks.setdefault(owner_id, RLock())

    def _store(self, owner_id: str) -> VectorStore:
        with self._registry_lock:
            return self._stores.setdefault(
                owner_id,
                VectorStore(self._root / safe_user_key(owner_id), self._model_name),
            )

    def snapshot_for(self, owner_id: str) -> Any | None:
        with self.lock_for(owner_id):
            return self._store(owner_id).current

    def replace_document(self, owner_id: str, document_id: str, chunks: list[DocumentChunk]) -> None:
        with self.lock_for(owner_id):
            store = self._store(owner_id)
            current = store.current
            existing = [] if current is None else [
                chunk for chunk in current.chunks
                if chunk.document_id != document_id and chunk.owner_id == owner_id
            ]
            self._commit(owner_id, store, existing + chunks)

    def replace_all(self, owner_id: str, chunks: list[DocumentChunk]) -> None:
        with self.lock_for(owner_id):
            self._commit(owner_id, self._store(owner_id), chunks)

    def is_consistent(self, owner_id: str, ready_document_ids: set[str]) -> bool:
        with self.lock_for(owner_id):
            current = self._store(owner_id).current
            if current is None:
                return not ready_document_ids
            indexed_ids = {
                chunk.document_id
                for chunk in current.chunks
                if chunk.owner_id == owner_id
            }
            return (
                indexed_ids == ready_document_ids
                and all(chunk.owner_id == owner_id for chunk in current.chunks)
                and current.manifest.get("ownerId") == owner_id
                and current.manifest.get("embeddingRuntime", "legacy")
                == getattr(self._embedding, "runtime_fingerprint", "legacy")
            )

    def remove_document(self, owner_id: str, document_id: str) -> None:
        with self.lock_for(owner_id):
            store = self._store(owner_id)
            current = store.current
            if current is None:
                return
            chunks = [
                chunk for chunk in current.chunks
                if chunk.document_id != document_id and chunk.owner_id == owner_id
            ]
            self._commit(owner_id, store, chunks)

    def search(
        self,
        owner_id: str,
        question: str,
        top_k: int,
        allowed_document_ids: set[str],
    ) -> list[RetrievalResult]:
        with self.lock_for(owner_id):
            current = self._store(owner_id).current
            if current is None or not current.chunks or not allowed_document_ids:
                return []
            query = self._embedding.encode_query(question)
            # Exact IndexFlat search over every candidate, then authorization filter.
            scores, positions = current.index.search(query, len(current.chunks))
            results: list[RetrievalResult] = []
            for score, position in zip(scores[0], positions[0]):
                if position < 0 or float(score) < self._min_score:
                    continue
                chunk = current.chunks[int(position)]
                if chunk.owner_id != owner_id or chunk.document_id not in allowed_document_ids:
                    continue
                results.append(RetrievalResult(chunk, float(score)))
                if len(results) == top_k:
                    break
            return results

    def _commit(self, owner_id: str, store: VectorStore, chunks: list[DocumentChunk]) -> None:
        if self._redis is None or (self._allow_local_fallback and monotonic() < self._redis_unavailable_until):
            self._commit_unlocked(owner_id, store, chunks)
            return
        try:
            distributed_lock = self._redis.lock(
                f"rag:index-lock:{safe_user_key(owner_id)}", timeout=600, blocking_timeout=30
            )
            acquired = distributed_lock.acquire(blocking=True)
        except (RedisConnectionError, RedisTimeoutError, OSError) as error:
            if self._allow_local_fallback:
                self._redis_unavailable_until = monotonic() + self._redis_fallback_cooldown_seconds
                LOGGER.warning(
                    "index_lock_fallback code=INDEX_LOCK_REDIS_UNAVAILABLE_FALLBACK owner=%s cooldown_seconds=%d",
                    safe_user_key(owner_id)[:12],
                    self._redis_fallback_cooldown_seconds,
                )
                self._commit_unlocked(owner_id, store, chunks)
                return
            raise ServiceError(
                503,
                "INDEX_LOCK_UNAVAILABLE",
                "Dịch vụ khóa chỉ mục tạm thời không khả dụng.",
                retryable=True,
                retry_after_seconds=5,
            ) from error
        if not acquired:
            raise ServiceError(
                409,
                "INDEX_MUTATION_IN_PROGRESS",
                "Chỉ mục đang được cập nhật bởi yêu cầu khác.",
                retryable=True,
                retry_after_seconds=1,
            )
        try:
            self._commit_unlocked(owner_id, store, chunks)
        finally:
            try:
                if distributed_lock.owned():
                    distributed_lock.release()
            except (RedisConnectionError, RedisTimeoutError, OSError):
                LOGGER.warning(
                    "index_lock_release_failed code=INDEX_LOCK_RELEASE_FAILED owner=%s",
                    safe_user_key(owner_id)[:12],
                )

    def _commit_unlocked(self, owner_id: str, store: VectorStore, chunks: list[DocumentChunk]) -> None:
        chunks = sorted(chunks, key=lambda item: (item.document_id, item.chunk_index))
        vectors = self._embedding.encode_documents([chunk.text for chunk in chunks])
        if not chunks:
            vectors = np.empty((0, self._embedding.dimension), dtype=np.float32)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        store.commit(
            vectors,
            chunks,
            {
                "version": 1,
                "ownerId": owner_id,
                "embeddingModel": self._model_name,
                "embeddingRuntime": getattr(
                    self._embedding, "runtime_fingerprint", "legacy"
                ),
                "dimension": int(vectors.shape[1]),
                "indexedAt": now,
                "documentCount": len({chunk.document_id for chunk in chunks}),
                "documentIds": sorted({chunk.document_id for chunk in chunks}),
                "chunkCount": len(chunks),
            },
        )
        if self._on_index_change is not None:
            self._on_index_change()
