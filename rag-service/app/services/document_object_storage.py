import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.exceptions import ServiceError


class LocalDocumentObjectStorage:
    backend = "local"

    def __init__(self, root: Path) -> None:
        self._root = root

    def store(self, source: Path, owner_key: str, document_id: str, filename: str) -> None:
        target = self._path(owner_key, document_id, filename)
        target.parent.mkdir(parents=True, exist_ok=False)
        shutil.move(str(source), str(target))

    @contextmanager
    def materialize(
        self, owner_key: str, document_id: str, filename: str
    ) -> Iterator[Path]:
        path = self._path(owner_key, document_id, filename)
        if not path.is_file():
            raise ServiceError(
                409,
                "DOCUMENT_SOURCE_FILE_MISSING",
                "Không tìm thấy tệp nguồn để xử lý.",
            )
        yield path

    def exists(self, owner_key: str, document_id: str, filename: str) -> bool:
        return self._path(owner_key, document_id, filename).is_file()

    def delete_document(self, owner_key: str, document_id: str) -> None:
        shutil.rmtree(self._root / owner_key / document_id, ignore_errors=True)

    def delete_owner(self, owner_key: str) -> None:
        shutil.rmtree(self._root / owner_key, ignore_errors=True)

    def ping(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        if not os.access(self._root, os.W_OK):
            raise OSError("document storage is not writable")

    def _path(self, owner_key: str, document_id: str, filename: str) -> Path:
        return self._root / owner_key / document_id / filename


class R2DocumentObjectStorage:
    backend = "r2"

    def __init__(
        self,
        *,
        client: Any,
        bucket: str,
        prefix: str,
        staging_root: Path,
    ) -> None:
        self._client = client
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._staging_root = staging_root

    def store(self, source: Path, owner_key: str, document_id: str, filename: str) -> None:
        try:
            self._client.upload_file(
                str(source),
                self._bucket,
                self._key(owner_key, document_id, filename),
            )
        except Exception as error:
            raise self._unavailable(error) from error
        finally:
            source.unlink(missing_ok=True)

    @contextmanager
    def materialize(
        self, owner_key: str, document_id: str, filename: str
    ) -> Iterator[Path]:
        self._staging_root.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f"{document_id}-", suffix=".source", dir=self._staging_root
        )
        os.close(descriptor)
        path = Path(temporary_name)
        try:
            self._client.download_file(
                self._bucket,
                self._key(owner_key, document_id, filename),
                str(path),
            )
            yield path
        except ClientError as error:
            status = int(error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
            if status == 404 or error.response.get("Error", {}).get("Code") in {
                "404",
                "NoSuchKey",
                "NotFound",
            }:
                raise ServiceError(
                    409,
                    "DOCUMENT_SOURCE_FILE_MISSING",
                    "Không tìm thấy tệp nguồn để xử lý.",
                ) from error
            raise self._unavailable(error) from error
        except ServiceError:
            raise
        except Exception as error:
            raise self._unavailable(error) from error
        finally:
            path.unlink(missing_ok=True)

    def exists(self, owner_key: str, document_id: str, filename: str) -> bool:
        try:
            self._client.head_object(
                Bucket=self._bucket,
                Key=self._key(owner_key, document_id, filename),
            )
            return True
        except ClientError as error:
            status = int(error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
            if status == 404 or error.response.get("Error", {}).get("Code") in {
                "404",
                "NoSuchKey",
                "NotFound",
            }:
                return False
            raise self._unavailable(error) from error
        except Exception as error:
            raise self._unavailable(error) from error

    def delete_document(self, owner_key: str, document_id: str) -> None:
        self._delete_prefix(self._key(owner_key, document_id, ""))

    def delete_owner(self, owner_key: str) -> None:
        self._delete_prefix(self._key(owner_key, "", ""))

    def ping(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception as error:
            raise self._unavailable(error) from error

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            close()

    def _delete_prefix(self, prefix: str) -> None:
        continuation: str | None = None
        try:
            while True:
                request: dict[str, Any] = {
                    "Bucket": self._bucket,
                    "Prefix": prefix,
                    "MaxKeys": 1000,
                }
                if continuation:
                    request["ContinuationToken"] = continuation
                response = self._client.list_objects_v2(**request)
                objects = [{"Key": item["Key"]} for item in response.get("Contents", [])]
                if objects:
                    self._client.delete_objects(
                        Bucket=self._bucket,
                        Delete={"Objects": objects, "Quiet": True},
                    )
                if not response.get("IsTruncated"):
                    return
                continuation = response.get("NextContinuationToken")
        except Exception as error:
            raise self._unavailable(error) from error

    def _key(self, owner_key: str, document_id: str, filename: str) -> str:
        values = [value.strip("/") for value in (self._prefix, owner_key, document_id, filename)]
        return "/".join(value for value in values if value)

    @staticmethod
    def _unavailable(error: Exception) -> ServiceError:
        return ServiceError(
            503,
            "DOCUMENT_STORAGE_UNAVAILABLE",
            "Kho lưu trữ tài liệu tạm thời không khả dụng.",
            retryable=True,
            retry_after_seconds=5,
        )


def create_document_object_storage(settings: Any) -> Any:
    if settings.document_storage_backend == "local":
        return LocalDocumentObjectStorage(settings.user_upload_dir)

    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=settings.document_storage_endpoint,
        aws_access_key_id=settings.document_storage_access_key,
        aws_secret_access_key=settings.document_storage_secret_key,
        region_name=settings.document_storage_region,
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
            s3={"addressing_style": "path", "payload_signing_enabled": False},
            connect_timeout=5,
            read_timeout=30,
        ),
    )
    return R2DocumentObjectStorage(
        client=client,
        bucket=settings.document_storage_bucket,
        prefix=settings.document_storage_prefix,
        staging_root=settings.document_staging_dir,
    )
