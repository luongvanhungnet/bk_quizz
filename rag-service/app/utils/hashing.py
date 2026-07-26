import hashlib
import uuid
from pathlib import Path

DOCUMENT_NAMESPACE = uuid.UUID("77b16b5b-bdd6-4b9a-8eb1-f03adf992f48")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalize_relative_path(value: str) -> str:
    return value.replace("\\", "/").strip("/").casefold()


def document_uuid(relative_path: str) -> str:
    return str(uuid.uuid5(DOCUMENT_NAMESPACE, normalize_relative_path(relative_path)))


def chunk_uuid(
    document_id: str,
    file_hash: str,
    page_number: int | None,
    chunk_index: int,
) -> str:
    namespace = uuid.UUID(document_id)
    return str(uuid.uuid5(namespace, f"{file_hash}:{page_number}:{chunk_index}"))
