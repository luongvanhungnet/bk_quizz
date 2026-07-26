from pydantic import BaseModel, ConfigDict


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ReindexResponse(ApiModel):
    new_files: int
    updated_files: int
    skipped_files: int
    deleted_files: int
    duplicate_files: int
    total_documents: int
    total_chunks: int
    index_version: int
    indexed_at: str


class SystemDocumentItem(ApiModel):
    document_id: str
    document_type: str = "SYSTEM"
    filename: str
    relative_path: str
    file_hash: str
    page_count: int | None
    chunk_count: int
    indexed_at: str


class SystemDocumentListResponse(ApiModel):
    items: list[SystemDocumentItem]
    total: int
    index_version: int
