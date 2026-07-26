import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import (
    get_system_indexing_service,
    get_vector_store,
    require_internal_api_key,
)
from app.schemas.document import (
    ReindexResponse,
    SystemDocumentItem,
    SystemDocumentListResponse,
)

router = APIRouter(
    prefix="/system-documents",
    tags=["system-documents"],
    dependencies=[Depends(require_internal_api_key)],
)


@router.post("/reindex", response_model=ReindexResponse)
async def reindex_system_documents(
    service: Annotated[Any, Depends(get_system_indexing_service)],
    force: bool = Query(default=False),
) -> ReindexResponse:
    result = await asyncio.to_thread(service.synchronize, force=force)
    return ReindexResponse(**result.__dict__)


@router.get("", response_model=SystemDocumentListResponse)
async def list_system_documents(
    store: Annotated[Any, Depends(get_vector_store)],
) -> SystemDocumentListResponse:
    snapshot = store.require_snapshot()
    entries = [entry for entry in snapshot.manifest.get("files", []) if entry["indexed"]]
    items = [
        SystemDocumentItem(
            document_id=entry["documentId"],
            filename=entry["filename"],
            relative_path=entry["relativePath"],
            file_hash=entry["fileHash"],
            page_count=entry.get("pageCount"),
            chunk_count=entry["chunkCount"],
            indexed_at=entry["indexedAt"],
        )
        for entry in entries
    ]
    return SystemDocumentListResponse(
        items=items,
        total=len(items),
        index_version=snapshot.manifest["indexVersion"],
    )
