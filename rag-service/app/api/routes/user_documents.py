from typing import Literal

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status

from app.api.dependencies import get_user_document_service, require_user_context
from app.models.user_context import UserContext
from app.schemas.user_document import UserDocumentDto, UserDocumentListResponse

router = APIRouter(tags=["user-documents"])


@router.post("/user-documents", response_model=UserDocumentDto, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    context: UserContext = Depends(require_user_context),
    service=Depends(get_user_document_service),
) -> UserDocumentDto:
    return await service.upload(context, file)


@router.get("/user-documents", response_model=UserDocumentListResponse)
def list_documents(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    status_filter: Literal["UPLOADED", "PROCESSING", "READY", "FAILED", "DELETED"] | None = Query(default=None, alias="status"),
    context: UserContext = Depends(require_user_context),
    service=Depends(get_user_document_service),
) -> UserDocumentListResponse:
    return service.list_documents(context.owner_id, page, size, status_filter)


@router.get("/user-documents/{document_id}", response_model=UserDocumentDto)
def get_document(
    document_id: str,
    context: UserContext = Depends(require_user_context),
    service=Depends(get_user_document_service),
) -> UserDocumentDto:
    return service.get(context.owner_id, document_id)


@router.delete("/user-documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    context: UserContext = Depends(require_user_context),
    service=Depends(get_user_document_service),
) -> Response:
    service.delete(context.owner_id, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
