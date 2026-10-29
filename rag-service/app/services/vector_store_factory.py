from pathlib import Path
from typing import Any

from app.services.qdrant_vector_store import QdrantVectorStore
from app.services.vector_store import VectorStore


def create_vector_store(
    *,
    settings: Any,
    database: Any,
    embedding_service: Any,
    namespace: str,
    faiss_directory: Path,
    qdrant_client: Any | None,
) -> Any:
    if settings.vector_store_backend == "faiss":
        return VectorStore(faiss_directory, settings.embedding_model)
    if qdrant_client is None:
        raise RuntimeError("Qdrant client chưa được khởi tạo.")
    return QdrantVectorStore(
        database=database,
        client=qdrant_client,
        collection=settings.qdrant_collection,
        namespace=namespace,
        embedding_model=settings.embedding_model,
        dimension=embedding_service.dimension,
        upsert_batch_size=settings.qdrant_upsert_batch_size,
    )
