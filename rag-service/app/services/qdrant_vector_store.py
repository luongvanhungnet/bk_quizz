import json
import logging
import math
import uuid
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable

import numpy as np
from qdrant_client import QdrantClient, models
from sqlalchemy import select

from app.core.exceptions import ServiceError
from app.db.models import VectorIndexSnapshotRecord
from app.models.document import DocumentChunk
from app.services.vector_store import VectorSnapshot

LOGGER = logging.getLogger("uvicorn.error")


def _unavailable(error: Exception) -> ServiceError:
    return ServiceError(
        503,
        "QDRANT_UNAVAILABLE",
        "Vector database tạm thời không khả dụng.",
        retryable=True,
        retry_after_seconds=5,
    )


def build_qdrant_client(settings: Any) -> QdrantClient:
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=math.ceil(settings.qdrant_timeout_seconds),
        prefer_grpc=False,
    )


class QdrantIndexProxy:
    def __init__(
        self,
        client: QdrantClient,
        collection: str,
        namespace: str,
        version: str,
        chunks: list[DocumentChunk],
        vectors: np.ndarray,
    ) -> None:
        self._client = client
        self._collection = collection
        self._namespace = namespace
        self._version = version
        self._chunks = chunks
        self._vectors = vectors
        self._positions = {chunk.chunk_id: index for index, chunk in enumerate(chunks)}

    @property
    def ntotal(self) -> int:
        return len(self._chunks)

    def search(self, query: Any, limit: int) -> tuple[np.ndarray, np.ndarray]:
        return self.search_filtered(query, limit, None, None)

    def search_filtered(
        self,
        query: Any,
        limit: int,
        allowed_document_ids: set[str] | frozenset[str] | None,
        owner_id: str | None,
    ) -> tuple[np.ndarray, np.ndarray]:
        if limit <= 0 or not self._chunks:
            return self._empty_result()
        conditions: list[Any] = [
            models.FieldCondition(key="_namespace", match=models.MatchValue(value=self._namespace)),
            models.FieldCondition(key="_version", match=models.MatchValue(value=self._version)),
        ]
        if allowed_document_ids is not None:
            if not allowed_document_ids:
                return self._empty_result()
            conditions.append(
                models.FieldCondition(
                    key="documentId",
                    match=models.MatchAny(any=sorted(allowed_document_ids)),
                )
            )
        if owner_id is not None:
            conditions.append(
                models.FieldCondition(key="ownerId", match=models.MatchValue(value=owner_id))
            )
        try:
            response = self._client.query_points(
                collection_name=self._collection,
                query=np.asarray(query[0], dtype=np.float32).tolist(),
                query_filter=models.Filter(must=conditions),
                limit=min(limit, len(self._chunks)),
                with_payload=["chunkId"],
                with_vectors=False,
            )
        except Exception as error:
            raise _unavailable(error) from error
        scores: list[float] = []
        positions: list[int] = []
        for point in response.points:
            payload = point.payload or {}
            position = self._positions.get(str(payload.get("chunkId", "")))
            if position is not None:
                scores.append(float(point.score))
                positions.append(position)
        return (
            np.asarray(scores, dtype=np.float32).reshape(1, -1),
            np.asarray(positions, dtype=np.int64).reshape(1, -1),
        )

    def reconstruct(self, position: int) -> np.ndarray:
        return self._vectors[position].copy()

    def reconstruct_batch(self, positions: Any) -> np.ndarray:
        return self._vectors[np.asarray(positions, dtype=np.int64)].copy()

    @staticmethod
    def _empty_result() -> tuple[np.ndarray, np.ndarray]:
        return (
            np.empty((1, 0), dtype=np.float32),
            np.empty((1, 0), dtype=np.int64),
        )


class QdrantVectorStore:
    def __init__(
        self,
        *,
        database: Any,
        client: QdrantClient,
        collection: str,
        namespace: str,
        embedding_model: str,
        dimension: int,
        upsert_batch_size: int = 128,
    ) -> None:
        self._database = database
        self._client = client
        self._collection = collection
        self._namespace = namespace
        self._embedding_model = embedding_model
        self._dimension = dimension
        self._upsert_batch_size = upsert_batch_size
        self._lock = RLock()
        self._snapshot: VectorSnapshot | None = None
        self._active_version: str | None = None
        self._commit_listeners: list[Callable[[], None]] = []
        self._ensure_collection()
        self.reload()

    def add_commit_listener(self, listener: Callable[[], None]) -> None:
        self._commit_listeners.append(listener)

    @property
    def current(self) -> VectorSnapshot | None:
        active = self._read_active_version()
        with self._lock:
            needs_reload = active != self._active_version
        if needs_reload:
            self.reload()
        with self._lock:
            return self._snapshot

    def require_snapshot(self) -> VectorSnapshot:
        snapshot = self.current
        if snapshot is None:
            raise ServiceError(409, "SYSTEM_INDEX_NOT_READY", "Chỉ mục tài liệu hệ thống chưa được tạo.")
        return snapshot

    def reload(self) -> None:
        with self._database.session() as session:
            record = session.get(VectorIndexSnapshotRecord, self._namespace)
            if record is None:
                with self._lock:
                    self._snapshot = None
                    self._active_version = None
                return
            version = record.active_version
            manifest = json.loads(record.manifest_json)

        rows: list[tuple[DocumentChunk, np.ndarray]] = []
        offset: Any | None = None
        query_filter = self._version_filter(version)
        while True:
            try:
                points, offset = self._client.scroll(
                    collection_name=self._collection,
                    scroll_filter=query_filter,
                    limit=256,
                    offset=offset,
                    with_payload=True,
                    with_vectors=True,
                )
            except Exception as error:
                raise _unavailable(error) from error
            for point in points:
                payload = point.payload or {}
                chunk_value = payload.get("chunk")
                if not isinstance(chunk_value, dict) or point.vector is None:
                    raise ServiceError(
                        503,
                        "QDRANT_SNAPSHOT_INVALID",
                        "Snapshot Qdrant thiếu dữ liệu chunk hoặc vector.",
                    )
                rows.append(
                    (
                        DocumentChunk.from_dict(chunk_value),
                        np.asarray(point.vector, dtype=np.float32),
                    )
                )
            if offset is None:
                break
        rows.sort(key=lambda item: (item[0].document_id, item[0].chunk_index, item[0].chunk_id))
        chunks = [item[0] for item in rows]
        vectors = (
            np.stack([item[1] for item in rows]).astype(np.float32)
            if rows
            else np.empty((0, self._dimension), dtype=np.float32)
        )
        if vectors.shape != (len(chunks), self._dimension):
            raise ServiceError(503, "QDRANT_DIMENSION_MISMATCH", "Kích thước vector Qdrant không tương thích.")
        if int(manifest.get("chunkCount", manifest.get("totalChunks", len(chunks)))) != len(chunks):
            raise ServiceError(503, "QDRANT_SNAPSHOT_INCOMPLETE", "Snapshot Qdrant chưa đầy đủ.")
        proxy = QdrantIndexProxy(
            self._client, self._collection, self._namespace, version, chunks, vectors
        )
        with self._lock:
            self._snapshot = VectorSnapshot(proxy, chunks, manifest)
            self._active_version = version

    def commit(
        self,
        vectors: np.ndarray,
        chunks: list[DocumentChunk],
        manifest: dict[str, Any],
    ) -> VectorSnapshot:
        values = np.asarray(vectors, dtype=np.float32)
        if values.shape != (len(chunks), self._dimension):
            raise ValueError("Số vector hoặc dimension không khớp số chunk.")
        if not np.isfinite(values).all():
            raise ValueError("Vector chứa giá trị không hữu hạn.")
        version = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        previous_version = self._read_active_version()
        point_values = [
            models.PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self._namespace}:{version}:{chunk.chunk_id}")),
                vector=values[index].tolist(),
                payload={
                    "_namespace": self._namespace,
                    "_version": version,
                    "_createdAt": created_at,
                    "chunkId": chunk.chunk_id,
                    "documentId": chunk.document_id,
                    "ownerId": chunk.owner_id or "SYSTEM",
                    "sourceType": chunk.source_type or chunk.document_type,
                    "chunk": chunk.to_dict(),
                },
            )
            for index, chunk in enumerate(chunks)
        ]
        for start in range(0, len(point_values), self._upsert_batch_size):
            try:
                self._client.upsert(
                    collection_name=self._collection,
                    points=point_values[start : start + self._upsert_batch_size],
                    wait=True,
                )
            except Exception as error:
                raise _unavailable(error) from error
        final_manifest = dict(manifest)
        final_manifest.update(
            indexVersionId=version,
            vectorBackend="qdrant",
            qdrantCollection=self._collection,
            chunkCount=len(chunks),
            embeddingModel=self._embedding_model,
            createdAt=final_manifest.get("createdAt", datetime.now(timezone.utc).isoformat()),
        )
        now = datetime.now(timezone.utc)
        with self._database.session() as session:
            record = session.scalar(
                select(VectorIndexSnapshotRecord)
                .where(VectorIndexSnapshotRecord.namespace == self._namespace)
                .with_for_update()
            )
            if record is None:
                record = VectorIndexSnapshotRecord(namespace=self._namespace)
                session.add(record)
            record.active_version = version
            record.manifest_json = json.dumps(final_manifest, ensure_ascii=False, separators=(",", ":"))
            record.updated_at = now
            session.commit()
        proxy = QdrantIndexProxy(
            self._client, self._collection, self._namespace, version, chunks, values
        )
        snapshot = VectorSnapshot(proxy, chunks, final_manifest)
        with self._lock:
            self._snapshot = snapshot
            self._active_version = version
        for listener in self._commit_listeners:
            listener()
        self._cleanup_stale_versions(version, previous_version)
        return snapshot

    def ping(self) -> None:
        self._client.get_collection(self._collection)

    def _read_active_version(self) -> str | None:
        with self._database.session() as session:
            return session.scalar(
                select(VectorIndexSnapshotRecord.active_version).where(
                    VectorIndexSnapshotRecord.namespace == self._namespace
                )
            )

    def _version_filter(self, version: str) -> models.Filter:
        return models.Filter(
            must=[
                models.FieldCondition(
                    key="_namespace", match=models.MatchValue(value=self._namespace)
                ),
                models.FieldCondition(key="_version", match=models.MatchValue(value=version)),
            ]
        )

    def _ensure_collection(self) -> None:
        try:
            if not self._client.collection_exists(self._collection):
                try:
                    self._client.create_collection(
                        collection_name=self._collection,
                        vectors_config=models.VectorParams(
                            size=self._dimension,
                            distance=models.Distance.COSINE,
                        ),
                    )
                except Exception:
                    if not self._client.collection_exists(self._collection):
                        raise
            info = self._client.get_collection(self._collection)
        except Exception as error:
            raise _unavailable(error) from error
        vectors_config = info.config.params.vectors
        configured_size = getattr(vectors_config, "size", None)
        if configured_size is not None and int(configured_size) != self._dimension:
            raise ServiceError(
                503,
                "QDRANT_DIMENSION_MISMATCH",
                "Collection Qdrant dùng dimension khác model embedding.",
            )
        payload_schema = info.payload_schema or {}
        for field in ("_namespace", "_version", "documentId", "ownerId"):
            if field not in payload_schema:
                try:
                    self._client.create_payload_index(
                        collection_name=self._collection,
                        field_name=field,
                        field_schema=models.PayloadSchemaType.KEYWORD,
                        wait=True,
                    )
                except Exception as error:
                    raise _unavailable(error) from error

    def _cleanup_stale_versions(self, active: str, previous: str | None) -> None:
        keep = [active] + ([previous] if previous else [])
        try:
            self._client.delete(
                collection_name=self._collection,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="_namespace",
                                match=models.MatchValue(value=self._namespace),
                            )
                        ],
                        must_not=[
                            models.FieldCondition(
                                key="_version", match=models.MatchAny(any=keep)
                            )
                        ],
                    )
                ),
                wait=False,
            )
        except Exception as error:
            LOGGER.warning(
                "qdrant_stale_version_cleanup_failed namespace=%s type=%s",
                self._namespace[:32],
                type(error).__name__,
            )
