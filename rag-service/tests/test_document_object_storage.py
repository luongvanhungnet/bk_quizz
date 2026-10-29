from pathlib import Path

import pytest

from app.core.exceptions import ServiceError
from app.services.document_object_storage import (
    LocalDocumentObjectStorage,
    R2DocumentObjectStorage,
)


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def upload_file(self, source: str, bucket: str, key: str) -> None:
        self.objects[(bucket, key)] = Path(source).read_bytes()

    def download_file(self, bucket: str, key: str, target: str) -> None:
        Path(target).write_bytes(self.objects[(bucket, key)])

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        if (Bucket, Key) not in self.objects:
            raise RuntimeError("missing")
        return {}

    def head_bucket(self, *, Bucket: str) -> dict[str, object]:
        assert Bucket == "bucket"
        return {}

    def list_objects_v2(self, **request):
        prefix = request["Prefix"]
        return {
            "Contents": [
                {"Key": key}
                for bucket, key in self.objects
                if bucket == request["Bucket"] and key.startswith(prefix)
            ],
            "IsTruncated": False,
        }

    def delete_objects(self, *, Bucket: str, Delete: dict[str, object]) -> None:
        for item in Delete["Objects"]:  # type: ignore[index]
            self.objects.pop((Bucket, item["Key"]), None)


def test_local_document_storage_round_trip(tmp_path: Path) -> None:
    storage = LocalDocumentObjectStorage(tmp_path / "uploads")
    source = tmp_path / "source.txt"
    source.write_text("BKQuiz", encoding="utf-8")

    storage.store(source, "owner", "document", "original-file")

    assert not source.exists()
    assert storage.exists("owner", "document", "original-file")
    with storage.materialize("owner", "document", "original-file") as path:
        assert path.read_text(encoding="utf-8") == "BKQuiz"
    storage.delete_document("owner", "document")
    assert not storage.exists("owner", "document", "original-file")


def test_r2_document_storage_round_trip_and_temporary_cleanup(tmp_path: Path) -> None:
    client = FakeS3Client()
    storage = R2DocumentObjectStorage(
        client=client,
        bucket="bucket",
        prefix="rag-documents",
        staging_root=tmp_path / "staging",
    )
    source = tmp_path / "source.txt"
    source.write_text("Nội dung", encoding="utf-8")

    storage.store(source, "owner", "document", "original-file")

    assert not source.exists()
    assert storage.exists("owner", "document", "original-file")
    with storage.materialize("owner", "document", "original-file") as path:
        materialized = path
        assert path.read_text(encoding="utf-8") == "Nội dung"
    assert not materialized.exists()
    storage.delete_owner("owner")
    assert not client.objects


def test_r2_storage_wraps_upload_failure(tmp_path: Path) -> None:
    class FailingClient(FakeS3Client):
        def upload_file(self, source: str, bucket: str, key: str) -> None:
            raise OSError("network")

    storage = R2DocumentObjectStorage(
        client=FailingClient(),
        bucket="bucket",
        prefix="rag-documents",
        staging_root=tmp_path / "staging",
    )
    source = tmp_path / "source.txt"
    source.write_text("data", encoding="utf-8")

    with pytest.raises(ServiceError) as raised:
        storage.store(source, "owner", "document", "original-file")

    assert raised.value.code == "DOCUMENT_STORAGE_UNAVAILABLE"
    assert raised.value.retryable is True
