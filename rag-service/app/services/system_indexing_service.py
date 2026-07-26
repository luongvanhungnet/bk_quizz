from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np

from app.core.exceptions import ServiceError
from app.models.document import DocumentChunk, utc_now_iso
from app.services.document_parser import SUPPORTED_EXTENSIONS, DocumentParser
from app.utils.hashing import chunk_uuid, document_uuid, sha256_file


@dataclass(frozen=True)
class IndexingResult:
    new_files: int
    updated_files: int
    skipped_files: int
    deleted_files: int
    duplicate_files: int
    total_documents: int
    total_chunks: int
    index_version: int
    indexed_at: str


class SystemIndexingService:
    def __init__(
        self,
        *,
        documents_dir: Path,
        parser: DocumentParser,
        chunker: Any,
        embedding_service: Any,
        vector_store: Any,
    ) -> None:
        self._documents_dir = documents_dir
        self._parser = parser
        self._chunker = chunker
        self._embedding = embedding_service
        self._store = vector_store
        self._synchronize_lock = Lock()

    def synchronize(self, *, force: bool = False) -> IndexingResult:
        if not self._synchronize_lock.acquire(blocking=False):
            raise ServiceError(
                409,
                "SYSTEM_REINDEX_IN_PROGRESS",
                "Tài liệu hệ thống đang được lập chỉ mục.",
            )
        try:
            return self._synchronize(force=force)
        finally:
            self._synchronize_lock.release()

    def _synchronize(self, *, force: bool) -> IndexingResult:
        files = self._scan_files()
        hashes = {relative: sha256_file(path) for relative, path in files}
        canonical_by_hash: dict[str, str] = {}
        canonical_paths: list[str] = []
        duplicate_of: dict[str, str] = {}
        for relative, _ in files:
            file_hash = hashes[relative]
            if file_hash in canonical_by_hash:
                duplicate_of[relative] = canonical_by_hash[file_hash]
            else:
                canonical_by_hash[file_hash] = relative
                canonical_paths.append(relative)

        old_snapshot = self._store.current
        old_manifest = old_snapshot.manifest if old_snapshot else {}
        embedding_runtime = getattr(
            self._embedding, "runtime_fingerprint", "legacy"
        )
        can_reuse = (
            not force
            and old_snapshot is not None
            and old_manifest.get("embeddingModel") == self._embedding.model_name
            and old_manifest.get("embeddingRuntime", "legacy")
            == embedding_runtime
        )
        old_entries = {
            entry["relativePath"]: entry for entry in old_manifest.get("files", [])
        }
        old_chunk_positions: dict[str, list[int]] = {}
        if old_snapshot:
            for position, chunk in enumerate(old_snapshot.chunks):
                old_chunk_positions.setdefault(chunk.relative_path, []).append(position)

        new_files = updated_files = skipped_files = 0
        final_chunks: list[DocumentChunk] = []
        vector_blocks: list[np.ndarray] = []
        manifest_entries: list[dict[str, Any]] = []
        file_map = dict(files)
        indexed_at = utc_now_iso()

        for relative in canonical_paths:
            path = file_map[relative]
            file_hash = hashes[relative]
            old_entry = old_entries.get(relative)
            unchanged = bool(
                can_reuse
                and old_entry
                and old_entry.get("indexed")
                and old_entry.get("fileHash") == file_hash
                and relative in old_chunk_positions
            )
            if unchanged:
                assert old_entry is not None
                positions = old_chunk_positions[relative]
                chunks = [old_snapshot.chunks[position] for position in positions]
                vectors = np.stack(
                    [old_snapshot.index.reconstruct(position) for position in positions]
                ).astype(np.float32)
                skipped_files += 1
                page_count = old_entry.get("pageCount")
            else:
                try:
                    sections = self._parser.parse(path)
                    drafts = self._chunker.chunk_sections(sections)
                except (OSError, UnicodeError, ValueError) as error:
                    raise ServiceError(
                        422,
                        "SYSTEM_DOCUMENT_PARSE_FAILED",
                        f"Không thể xử lý tài liệu {path.name}.",
                    ) from error
                if not drafts:
                    raise ServiceError(
                        422,
                        "SYSTEM_DOCUMENT_EMPTY",
                        f"Tài liệu {path.name} không tạo được chunk.",
                    )
                document_id = document_uuid(relative)
                chunks = [
                    DocumentChunk(
                        chunk_id=chunk_uuid(
                            document_id, file_hash, draft.page_number, index
                        ),
                        document_id=document_id,
                        document_type="SYSTEM",
                        filename=path.name,
                        relative_path=relative,
                        file_hash=file_hash,
                        page_number=draft.page_number,
                        chunk_index=index,
                        heading=draft.heading,
                        text=draft.text,
                        created_at=indexed_at,
                    )
                    for index, draft in enumerate(drafts)
                ]
                vectors = self._embedding.encode_documents(
                    [chunk.text for chunk in chunks]
                )
                page_numbers = {
                    section.page_number
                    for section in sections
                    if section.page_number is not None
                }
                page_count = len(page_numbers) or None
                if old_entry is None:
                    new_files += 1
                else:
                    updated_files += 1
            final_chunks.extend(chunks)
            vector_blocks.append(vectors)
            manifest_entries.append(
                {
                    "relativePath": relative,
                    "filename": path.name,
                    "fileHash": file_hash,
                    "documentId": chunks[0].document_id,
                    "indexed": True,
                    "duplicateOf": None,
                    "pageCount": page_count,
                    "chunkCount": len(chunks),
                    "indexedAt": chunks[0].created_at,
                }
            )

        for relative in sorted(duplicate_of, key=str.casefold):
            path = file_map[relative]
            manifest_entries.append(
                {
                    "relativePath": relative,
                    "filename": path.name,
                    "fileHash": hashes[relative],
                    "documentId": document_uuid(relative),
                    "indexed": False,
                    "duplicateOf": duplicate_of[relative],
                    "pageCount": None,
                    "chunkCount": 0,
                    "indexedAt": indexed_at,
                }
            )

        dimension = self._embedding.dimension
        vectors = (
            np.vstack(vector_blocks).astype(np.float32)
            if vector_blocks
            else np.empty((0, dimension), dtype=np.float32)
        )
        if vectors.shape != (len(final_chunks), dimension):
            raise ValueError("Kích thước vector không khớp metadata chunk.")
        current_paths = {relative for relative, _ in files}
        deleted_files = len(set(old_entries) - current_paths)
        manifest_entries.sort(key=lambda entry: entry["relativePath"].casefold())
        manifest = {
            "indexVersion": 1,
            "embeddingModel": self._embedding.model_name,
            "embeddingRuntime": embedding_runtime,
            "embeddingDimension": dimension,
            "createdAt": indexed_at,
            "files": manifest_entries,
            "totalDocuments": len(canonical_paths),
            "totalChunks": len(final_chunks),
        }
        self._store.commit(vectors, final_chunks, manifest)
        return IndexingResult(
            new_files,
            updated_files,
            skipped_files,
            deleted_files,
            len(duplicate_of),
            len(canonical_paths),
            len(final_chunks),
            1,
            indexed_at,
        )

    def _scan_files(self) -> list[tuple[str, Path]]:
        self._documents_dir.mkdir(parents=True, exist_ok=True)
        root = self._documents_dir.resolve()
        files: list[tuple[str, Path]] = []
        for path in self._documents_dir.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            if path.suffix.casefold() not in SUPPORTED_EXTENSIONS:
                continue
            resolved = path.resolve()
            try:
                relative = resolved.relative_to(root).as_posix()
            except ValueError:
                continue
            files.append((relative, resolved))
        return sorted(files, key=lambda item: item[0].casefold())
