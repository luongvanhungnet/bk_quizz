
import numpy as np
from fastapi.testclient import TestClient

from app.main import create_app


class Embedding:
    model_name = "test-model"
    dimension = 2
    def encode_documents(self, values):
        return np.asarray([[1.0, 0.0] for _ in values], dtype=np.float32)
    def encode_query(self, _value):
        return np.asarray([[1.0, 0.0]], dtype=np.float32)


def headers(user="user-a", debug=None):
    result = {"X-Internal-API-Key": "test-internal-key", "X-User-Id": user}
    if debug is not None:
        result["X-Debug-RAG-Key"] = debug
    return result


def test_debug_and_evaluation_require_separate_key(settings) -> None:
    configured = settings.model_copy(update={"rag_debug_api_key": "debug-secret", "rag_min_score": -1})
    with TestClient(create_app(settings=configured, embedding_service=Embedding())) as client:
        uploaded = client.post(
            "/api/v1/user-documents", headers=headers(),
            files={"file": ("facts.txt", "Mã kỹ thuật BK-2026", "text/plain")},
        )
        assert uploaded.status_code == 201
        document_id = uploaded.json()["id"]
        forbidden = client.post(
            "/api/v1/user-rag/search", headers=headers(),
            json={"question": "BK-2026", "debug": True},
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["code"] == "RAG_DEBUG_FORBIDDEN"
        debug = client.post(
            "/api/v1/user-rag/search", headers=headers(debug="debug-secret"),
            json={"question": "BK-2026", "debug": True},
        )
        assert debug.status_code == 200
        assert debug.json()["debug"]["originalQuery"] == "BK-2026"
        assert all(len(item["preview"]) <= 200 for item in debug.json()["debug"]["vectorCandidates"])
        evaluation = client.post(
            "/api/v1/evaluation/retrieval?k=1&mode=hybrid",
            headers=headers(debug="debug-secret"),
            json=[{"question": "BK-2026", "expectedDocumentIds": [document_id], "expectedPageNumbers": []}],
        )
        assert evaluation.status_code == 200, evaluation.text
        assert evaluation.json()["hitRate"] == 1.0
        cross_tenant = client.post(
            "/api/v1/evaluation/retrieval?k=1",
            headers=headers(user="user-b", debug="debug-secret"),
            json=[{"question": "BK-2026", "expectedDocumentIds": [document_id], "expectedPageNumbers": []}],
        )
        assert cross_tenant.status_code == 422
        assert cross_tenant.json()["code"] == "INVALID_DOCUMENT_SELECTION"
