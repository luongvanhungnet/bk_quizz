from pathlib import Path

from app.utils.hashing import document_uuid, sha256_file


def test_hash_and_document_uuid_are_stable(tmp_path: Path) -> None:
    file_path = tmp_path / "a.txt"
    file_path.write_text("same", encoding="utf-8")

    assert sha256_file(file_path) == sha256_file(file_path)
    assert document_uuid("Folder/A.txt") == document_uuid("folder\\a.txt")
