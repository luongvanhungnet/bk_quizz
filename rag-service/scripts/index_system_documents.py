import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.services.chunking_service import ChunkingService
from app.services.document_parser import DocumentParser
from app.services.embedding_service import EmbeddingService
from app.services.system_indexing_service import SystemIndexingService
from app.services.vector_store import VectorStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Lập chỉ mục tài liệu hệ thống BKQuiz.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bỏ qua vector cũ và lập lại toàn bộ chỉ mục.",
    )
    arguments = parser.parse_args()
    try:
        settings = Settings()
        embedding = EmbeddingService(settings.embedding_model)
        store = VectorStore(settings.system_index_dir, settings.embedding_model)
        service = SystemIndexingService(
            documents_dir=settings.system_documents_dir,
            parser=DocumentParser(),
            chunker=ChunkingService(
                settings.chunk_size_chars, settings.chunk_overlap_chars
            ),
            embedding_service=embedding,
            vector_store=store,
        )
        result = service.synchronize(force=arguments.force)
        print(
            json.dumps(
                {
                    "newFiles": result.new_files,
                    "updatedFiles": result.updated_files,
                    "skippedFiles": result.skipped_files,
                    "deletedFiles": result.deleted_files,
                    "duplicateFiles": result.duplicate_files,
                    "totalDocuments": result.total_documents,
                    "totalChunks": result.total_chunks,
                    "indexVersion": result.index_version,
                    "indexedAt": result.indexed_at,
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (ServiceError, ValueError, OSError) as error:
        code = error.code if isinstance(error, ServiceError) else "INDEXING_FAILED"
        print(
            json.dumps(
                {"status": "error", "code": code, "message": str(error)},
                ensure_ascii=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
