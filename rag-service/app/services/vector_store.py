import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Callable

import faiss
import numpy as np

from app.core.exceptions import ServiceError
from app.models.document import DocumentChunk
from app.utils.hashing import sha256_file


@dataclass(frozen=True)
class VectorSnapshot:
    index: Any
    chunks: list[DocumentChunk]
    manifest: dict[str, Any]

    @property
    def fingerprint(self) -> str:
        value = ":".join(
            (
                str(self.manifest.get("vectorsSha256", "")),
                str(self.manifest.get("chunksSha256", "")),
                str(self.manifest.get("embeddingModel", "")),
                str(self.manifest.get("embeddingRuntime", "legacy")),
                str(self.manifest.get("ownerId", "SYSTEM")),
                str(self.manifest.get("vectorBackend", "faiss")),
                str(self.manifest.get("indexVersionId", "legacy")),
            )
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


class VectorStore:
    def __init__(self, index_dir: Path, embedding_model: str) -> None:
        self._index_dir = index_dir
        self._embedding_model = embedding_model
        self._lock = RLock()
        self._snapshot: VectorSnapshot | None = None
        self._load_error: ServiceError | None = None
        self._commit_listeners: list[Callable[[], None]] = []
        self.reload()

    def add_commit_listener(self, listener: Callable[[], None]) -> None:
        self._commit_listeners.append(listener)

    @property
    def current(self) -> VectorSnapshot | None:
        with self._lock:
            return self._snapshot

    def require_snapshot(self) -> VectorSnapshot:
        with self._lock:
            if self._snapshot is not None:
                return self._snapshot
            if self._load_error is not None:
                raise self._load_error
        raise ServiceError(
            409,
            "SYSTEM_INDEX_NOT_READY",
            "Chỉ mục tài liệu hệ thống chưa được tạo.",
        )

    def reload(self) -> None:
        active_path = self._index_dir / "active.json"
        base = self._index_dir
        if active_path.exists():
            try:
                version_id = json.loads(active_path.read_text(encoding="utf-8"))["versionId"]
                if not isinstance(version_id, str) or not version_id.replace("-", "").isalnum():
                    raise ValueError("invalid version id")
                base = self._index_dir / "versions" / version_id
            except Exception:
                self._load_error = ServiceError(409, "SYSTEM_INDEX_REBUILD_REQUIRED", "Con trỏ chỉ mục bị hỏng; cần lập lại chỉ mục.")
                return
        vectors_path = base / "vectors.faiss"
        chunks_path = base / "chunks.json"
        manifest_path = base / "manifest.json"
        if not all(path.exists() for path in (vectors_path, chunks_path, manifest_path)):
            return
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("embeddingModel") != self._embedding_model:
                raise ServiceError(
                    409,
                    "SYSTEM_INDEX_REBUILD_REQUIRED",
                    "Model embedding đã thay đổi; cần lập lại chỉ mục.",
                )
            if manifest.get("vectorsSha256") != sha256_file(vectors_path):
                raise ValueError("vector checksum mismatch")
            if manifest.get("chunksSha256") != sha256_file(chunks_path):
                raise ValueError("chunk checksum mismatch")
            index = faiss.read_index(str(vectors_path))
            raw_chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
            chunks = [DocumentChunk.from_dict(value) for value in raw_chunks]
            if index.ntotal != len(chunks):
                raise ValueError("vector and chunk count mismatch")
            snapshot = VectorSnapshot(index, chunks, manifest)
        except ServiceError as error:
            self._load_error = error
            self._snapshot = None
            return
        except Exception:
            self._load_error = ServiceError(
                409,
                "SYSTEM_INDEX_REBUILD_REQUIRED",
                "Chỉ mục tài liệu hệ thống bị hỏng; cần lập lại chỉ mục.",
            )
            self._snapshot = None
            return
        with self._lock:
            self._snapshot = snapshot
            self._load_error = None

    def commit(
        self,
        vectors: np.ndarray,
        chunks: list[DocumentChunk],
        manifest: dict[str, Any],
    ) -> VectorSnapshot:
        if vectors.ndim != 2 or vectors.shape[0] != len(chunks):
            raise ValueError("Số vector không khớp số chunk.")
        self._index_dir.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        version_dir = self._index_dir / "versions" / token
        version_dir.mkdir(parents=True, exist_ok=False)
        vector_tmp = version_dir / "vectors.faiss"
        chunks_tmp = version_dir / "chunks.json"
        manifest_tmp = version_dir / "manifest.json"
        index = faiss.IndexFlatIP(int(vectors.shape[1]))
        if len(chunks):
            index.add(np.ascontiguousarray(vectors, dtype=np.float32))
        try:
            faiss.write_index(index, str(vector_tmp))
            chunks_tmp.write_text(
                json.dumps(
                    [chunk.to_dict() for chunk in chunks],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            final_manifest = dict(manifest)
            final_manifest["indexVersionId"] = token
            final_manifest.setdefault("chunkingVersion", "chars-v1")
            final_manifest.setdefault("createdAt", datetime.now(timezone.utc).isoformat())
            final_manifest["vectorsSha256"] = sha256_file(vector_tmp)
            final_manifest["chunksSha256"] = sha256_file(chunks_tmp)
            manifest_tmp.write_text(
                json.dumps(final_manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            for path in (vector_tmp, chunks_tmp, manifest_tmp):
                with path.open("r+b") as stream:
                    stream.flush()
                    os.fsync(stream.fileno())
            # The pointer is the commit marker. Readers keep the old snapshot until this replace.
            pointer_tmp = self._index_dir / f"active.{token}.tmp"
            pointer_tmp.write_text(json.dumps({"versionId": token}), encoding="utf-8")
            with pointer_tmp.open("r+b") as stream:
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(pointer_tmp, self._index_dir / "active.json")
        except Exception:
            shutil.rmtree(version_dir, ignore_errors=True)
            raise
        # Best-effort compatibility copies are not part of the committed snapshot.
        try:
            for source, target in (
                (vector_tmp, self._index_dir / "vectors.faiss"),
                (chunks_tmp, self._index_dir / "chunks.json"),
                (manifest_tmp, self._index_dir / "manifest.json"),
            ):
                shutil.copy2(source, target)
        except OSError:
            pass
        snapshot = VectorSnapshot(index, chunks, final_manifest)
        with self._lock:
            self._snapshot = snapshot
            self._load_error = None
        for listener in self._commit_listeners:
            listener()
        return snapshot
