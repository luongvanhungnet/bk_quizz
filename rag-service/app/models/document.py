from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class DocumentSection:
    page_number: int | None
    heading: str | None
    text: str
    slide_number: int | None = None
    raw_text: str | None = None
    math_enhanced: bool = False
    math_formula_count: int = 0
    math_warning_count: int = 0


@dataclass(frozen=True)
class ChunkDraft:
    page_number: int | None
    heading: str | None
    text: str
    slide_number: int | None = None
    raw_text: str | None = None
    math_enhanced: bool = False


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    document_id: str
    document_type: str
    filename: str
    relative_path: str
    file_hash: str
    page_number: int | None
    chunk_index: int
    heading: str | None
    text: str
    created_at: str
    owner_id: str | None = None
    classroom_id: str | None = None
    source_type: str | None = None
    slide_number: int | None = None
    raw_content: str | None = None
    math_enhanced: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunkId": self.chunk_id,
            "documentId": self.document_id,
            "documentType": self.document_type,
            "filename": self.filename,
            "relativePath": self.relative_path,
            "fileHash": self.file_hash,
            "pageNumber": self.page_number,
            "chunkIndex": self.chunk_index,
            "heading": self.heading,
            "text": self.text,
            "createdAt": self.created_at,
            "ownerId": self.owner_id,
            "classroomId": self.classroom_id,
            "sourceType": self.source_type or self.document_type,
            "slideNumber": self.slide_number,
            "rawContent": self.raw_content,
            "mathEnhanced": self.math_enhanced,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DocumentChunk":
        return cls(
            chunk_id=value["chunkId"],
            document_id=value["documentId"],
            document_type=value["documentType"],
            filename=value["filename"],
            relative_path=value.get("relativePath", value["filename"]),
            file_hash=value["fileHash"],
            page_number=value.get("pageNumber"),
            chunk_index=value["chunkIndex"],
            heading=value.get("heading"),
            text=value["text"],
            created_at=value["createdAt"],
            owner_id=value.get("ownerId"),
            classroom_id=value.get("classroomId"),
            source_type=value.get("sourceType", value.get("documentType")),
            slide_number=value.get("slideNumber"),
            raw_content=value.get("rawContent"),
            math_enhanced=bool(value.get("mathEnhanced", False)),
        )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
