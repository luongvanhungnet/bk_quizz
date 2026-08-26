import hashlib

import numpy as np
from fastapi.testclient import TestClient

from app.main import create_app


class DeterministicEmbedding:
    model_name = "test-model"
    dimension = 4

    def encode_documents(self, values: list[str]) -> np.ndarray:
        if not values:
            return np.empty((0, 4), dtype=np.float32)
        rows = []
        for value in values:
            digest = hashlib.sha256(value.encode()).digest()
            row = np.asarray([digest[i] + 1 for i in range(4)], dtype=np.float32)
            rows.append(row / np.linalg.norm(row))
        return np.asarray(rows, dtype=np.float32)

    def encode_query(self, value: str) -> np.ndarray:
        return self.encode_documents([value])


class CapturingDispatcher:
    def __init__(self) -> None:
        self.ids: list[str] = []

    def dispatch(self, job_id: str) -> None:
        self.ids.append(job_id)


def headers(user: str, **extra: str) -> dict[str, str]:
    return {"X-Internal-API-Key": "test-internal-key", "X-User-Id": user, **extra}


def test_v2_upload_poll_process_and_tenant_isolation(settings) -> None:
    dispatcher = CapturingDispatcher()
    app = create_app(
        settings=settings, embedding_service=DeterministicEmbedding(),
        job_dispatcher=dispatcher,
    )
    with TestClient(app) as client:
        uploaded = client.post(
            "/api/v2/user-documents",
            headers=headers("user-a", **{"Idempotency-Key": "upload-1"}),
            files={"file": ("notes.txt", "Nội dung tài liệu thật", "text/plain")},
        )
        assert uploaded.status_code == 202, uploaded.text
        body = uploaded.json()
        assert body["documentStatus"] == "PROCESSING"
        assert body["jobStatus"] == "PENDING"
        assert dispatcher.ids == [body["jobId"]]

        hidden = client.get(f"/api/v2/indexing-jobs/{body['jobId']}", headers=headers("user-b"))
        assert hidden.status_code == 404
        client.app.state.async_document_processor.process(body["jobId"])
        completed = client.get(f"/api/v2/indexing-jobs/{body['jobId']}", headers=headers("user-a"))
        assert completed.json()["status"] == "SUCCEEDED"
        assert completed.json()["progress"] == 100

        repeated = client.post(
            "/api/v2/user-documents",
            headers=headers("user-a", **{"Idempotency-Key": "upload-1"}),
            files={"file": ("ignored.txt", "ignored body", "text/plain")},
        )
        assert repeated.status_code == 202
        assert repeated.json()["documentId"] == body["documentId"]


def test_v2_error_contract_and_key_rotation(settings) -> None:
    configured = settings.model_copy(update={"spring_boot_previous_internal_api_key": "old-key"})
    with TestClient(create_app(settings=configured, embedding_service=DeterministicEmbedding(), job_dispatcher=CapturingDispatcher())) as client:
        accepted = client.get("/api/v2/user-documents", headers={"X-Internal-API-Key": "old-key", "X-User-Id": "user-a"})
        assert accepted.status_code == 200
        rejected = client.get("/api/v2/user-documents", headers={"X-Internal-API-Key": "wrong", "X-User-Id": "user-a"})
        assert rejected.status_code == 401
        body = rejected.json()
        assert body["status"] == 401
        assert body["requestId"] == rejected.headers["X-Request-Id"]
        assert body["retryable"] is False
        assert "trace" not in rejected.text.casefold()


def test_live_and_metrics_are_public(settings) -> None:
    with TestClient(create_app(settings=settings)) as client:
        assert client.get("/health/live").json() == {"status": "UP"}
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "rag_http_requests_total" in metrics.text


def test_v2_reindex_reuses_ready_document_and_active_job(settings) -> None:
    dispatcher = CapturingDispatcher()
    app = create_app(
        settings=settings,
        embedding_service=DeterministicEmbedding(),
        job_dispatcher=dispatcher,
    )
    with TestClient(app) as client:
        uploaded = client.post(
            "/api/v2/user-documents",
            headers=headers("user-a"),
            files={"file": ("notes.txt", "Nội dung đủ để lập chỉ mục lại", "text/plain")},
        ).json()
        client.app.state.async_document_processor.process(uploaded["jobId"])

        first = client.post(
            f"/api/v2/user-documents/{uploaded['documentId']}/reindex",
            headers=headers("user-a"),
        )
        assert first.status_code == 202, first.text
        assert first.json()["documentId"] == uploaded["documentId"]
        assert first.json()["documentStatus"] == "READY"

        repeated = client.post(
            f"/api/v2/user-documents/{uploaded['documentId']}/reindex",
            headers=headers("user-a"),
        )
        assert repeated.status_code == 202
        assert repeated.json()["jobId"] == first.json()["jobId"]

        hidden = client.post(
            f"/api/v2/user-documents/{uploaded['documentId']}/reindex",
            headers=headers("user-b"),
        )
        assert hidden.status_code == 404


def test_failed_reindex_keeps_ready_document(settings) -> None:
    dispatcher = CapturingDispatcher()
    app = create_app(
        settings=settings,
        embedding_service=DeterministicEmbedding(),
        job_dispatcher=dispatcher,
    )
    with TestClient(app) as client:
        uploaded = client.post(
            "/api/v2/user-documents",
            headers=headers("user-a"),
            files={"file": ("notes.txt", "Nội dung chỉ mục đang hoạt động", "text/plain")},
        ).json()
        client.app.state.async_document_processor.process(uploaded["jobId"])
        before = client.get(
            f"/api/v2/user-documents/{uploaded['documentId']}",
            headers=headers("user-a"),
        ).json()
        reindex = client.post(
            f"/api/v2/user-documents/{uploaded['documentId']}/reindex",
            headers=headers("user-a"),
        ).json()

        def fail_parse(*_args, **_kwargs):
            raise ValueError("broken parser")

        client.app.state.user_document_service._parser.parse = fail_parse
        try:
            client.app.state.async_document_processor.process(reindex["jobId"])
        except Exception:
            pass

        after = client.get(
            f"/api/v2/user-documents/{uploaded['documentId']}",
            headers=headers("user-a"),
        ).json()
        job = client.get(
            f"/api/v2/indexing-jobs/{reindex['jobId']}",
            headers=headers("user-a"),
        ).json()
        assert after["status"] == "READY"
        assert after["chunkCount"] == before["chunkCount"]
        assert after["indexedAt"] == before["indexedAt"]
        assert job["status"] == "FAILED"
