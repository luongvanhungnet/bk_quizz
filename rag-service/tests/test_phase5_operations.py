import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from app.core.exceptions import ServiceError
from app.models.document import DocumentChunk
from app.services.rate_limiter import RedisRateLimiter
from app.services.vector_store import VectorStore


def chunk(value: str) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=value, document_id="doc-1", document_type="USER_UPLOAD",
        filename="a.txt", relative_path="a.txt", file_hash="a" * 64,
        page_number=None, chunk_index=0, heading=None, text=value,
        created_at="2026-01-01T00:00:00Z", owner_id="user-a",
        source_type="USER_UPLOAD",
    )


def manifest() -> dict:
    return {"version": 1, "ownerId": "user-a", "embeddingModel": "test-model", "dimension": 2, "chunkCount": 1}


def test_versioned_index_pointer_and_failed_swap_keep_old_snapshot(tmp_path: Path) -> None:
    store = VectorStore(tmp_path, "test-model")
    first = store.commit(np.asarray([[1.0, 0.0]], dtype=np.float32), [chunk("first")], manifest())
    active = json.loads((tmp_path / "active.json").read_text())["versionId"]
    assert (tmp_path / "versions" / active / "manifest.json").is_file()

    original_replace = __import__("os").replace

    def fail_pointer(source, target):
        if str(target).endswith("active.json"):
            raise OSError("simulated pointer failure")
        return original_replace(source, target)

    with patch("app.services.vector_store.os.replace", side_effect=fail_pointer):
        with pytest.raises(OSError):
            store.commit(np.asarray([[0.0, 1.0]], dtype=np.float32), [chunk("second")], manifest())
    assert store.current is first
    assert json.loads((tmp_path / "active.json").read_text())["versionId"] == active


def test_redis_unavailable_has_retryable_stable_error() -> None:
    class BrokenRedis:
        def incr(self, _: str) -> int:
            raise ConnectionError("redis unavailable")

    with pytest.raises(ServiceError) as raised:
        RedisRateLimiter(BrokenRedis()).check("upload", "safe-user", 5)
    assert raised.value.code == "RATE_LIMIT_STORE_UNAVAILABLE"
    assert raised.value.retryable is True
    assert raised.value.retry_after_seconds == 5
