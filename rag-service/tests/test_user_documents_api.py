import asyncio
import hashlib
import json
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from app.api.routes.v2 import _stream_ndjson, _unexpected_stream_failure
from app.core.exceptions import ServiceError
from app.main import create_app
from app.services.gemini_service import GeminiResult, TokenUsage


class DeterministicEmbedding:
    model_name = "test-model"
    dimension = 4

    def _encode(self, values: list[str]) -> np.ndarray:
        rows = []
        for value in values:
            digest = hashlib.sha256(value.encode("utf-8")).digest()
            row = np.array([digest[index] + 1 for index in range(4)], dtype=np.float32)
            rows.append(row / np.linalg.norm(row))
        return np.asarray(rows, dtype=np.float32)

    def encode_documents(self, values: list[str]) -> np.ndarray:
        return self._encode(values) if values else np.empty((0, 4), dtype=np.float32)

    def encode_query(self, value: str) -> np.ndarray:
        return self._encode([value])


class FailingEmbedding(DeterministicEmbedding):
    fail = False

    def encode_documents(self, values: list[str]) -> np.ndarray:
        if self.fail:
            raise ServiceError(503, "EMBEDDING_MODEL_UNAVAILABLE", "Embedding tạm thời lỗi.")
        return super().encode_documents(values)


class LowSimilarityEmbedding:
    model_name = "test-model"
    dimension = 2

    def encode_documents(self, values: list[str]) -> np.ndarray:
        return np.asarray([[1.0, 0.0] for _ in values], dtype=np.float32)

    def encode_query(self, _: str) -> np.ndarray:
        return np.asarray([[0.0, 1.0]], dtype=np.float32)


class QuizGemini:
    async def generate(self, message: str, **_: object) -> GeminiResult:
        assert "Nguồn kiến thức chính xác để tạo câu hỏi" in message
        answer = """{"questions":[{"type":"SINGLE_CHOICE","prompt":"RAG là gì?",
        "explanation":"RAG dùng nguồn kiến thức.","options":[
        {"text":"Đúng","correct":true},{"text":"Sai 1","correct":false},
        {"text":"Sai 2","correct":false},{"text":"Sai 3","correct":false}],
        "acceptedAnswers":[],"questionCitations":[{"sourceId":"S1","evidenceQuote":"Nguồn kiến thức chính xác để tạo câu hỏi"}],
        "answerCitations":[{"sourceId":"S1","evidenceQuote":"Nguồn kiến thức chính xác để tạo câu hỏi"}],
        "explanationCitations":[{"sourceId":"S1","evidenceQuote":"Nguồn kiến thức chính xác để tạo câu hỏi"}]}]}"""
        return GeminiResult(answer, "test-model", TokenUsage(10, 10, 20))


class CohesionQuizGemini:
    called = False

    async def generate(self, message: str, **_: object) -> GeminiResult:
        self.called = True
        assert "Functional Cohesion" in message
        answer = """{"questions":[{"type":"SINGLE_CHOICE","prompt":"Functional Cohesion là gì?",
        "explanation":"Các thành phần phối hợp thực hiện một chức năng.","options":[
        {"text":"Một chức năng duy nhất","correct":true},{"text":"Truy cập mã nội bộ","correct":false},
        {"text":"Truyền cờ điều khiển","correct":false},{"text":"Truyền dữ liệu thừa","correct":false}],
        "acceptedAnswers":[],"questionCitations":[{"sourceId":"S1","evidenceQuote":"Functional Cohesion là loại cohesion"}],
        "answerCitations":[{"sourceId":"S1","evidenceQuote":"thực hiện một chức năng duy nhất"}],
        "explanationCitations":[{"sourceId":"S1","evidenceQuote":"module có trách nhiệm rõ ràng"}]}]}"""
        return GeminiResult(answer, "test-model", TokenUsage(10, 10, 20))


class CognitiveQuizGemini:
    called = False

    async def generate(self, message: str, **_: object) -> GeminiResult:
        self.called = True
        assert '"cognitiveLevel": "L1"' in message
        answer = """{"questions":[{"type":"SINGLE_CHOICE","planSlotId":"B1Q1",
        "cognitiveLevel":"L1","complexityProfile":{"conceptCount":1,
        "reasoningStepCount":0,"requiresNovelScenario":false,
        "answerDirectlyPresent":true,"requiresComparison":false,
        "conceptsUsed":["RAG"],"novelScenarioSummary":null},
        "prompt":"What does RAG combine?","explanation":"RAG combines retrieval and generation.",
        "options":[{"text":"retrieval and generation","correct":true},
        {"text":"sorting and caching","correct":false},{"text":"rendering and styling","correct":false},
        {"text":"testing and deployment","correct":false}],"acceptedAnswers":[],
        "questionCitations":[{"sourceId":"S1","evidenceQuote":"RAG combines retrieval and generation"}],
        "answerCitations":[{"sourceId":"S1","evidenceQuote":"RAG combines retrieval and generation"}],
        "explanationCitations":[{"sourceId":"S1","evidenceQuote":"RAG combines retrieval and generation"}]}]}"""
        return GeminiResult(answer, "test-model", TokenUsage(10, 10, 20))


class CitationRepairGemini:
    calls = 0

    async def generate(self, message: str, **_: object) -> GeminiResult:
        self.calls += 1
        quote = (
            "Nguồn kiến thức chính xác để tạo câu hỏi"
            if self.calls == 2
            else "Một câu không tồn tại trong nguồn"
        )
        answer = f"""{{"questions":[{{"type":"SINGLE_CHOICE","difficulty":"EASY",
        "prompt":"RAG là gì?","explanation":"RAG dùng nguồn kiến thức.","options":[
        {{"text":"Đúng","correct":true}},{{"text":"Sai 1","correct":false}},
        {{"text":"Sai 2","correct":false}},{{"text":"Sai 3","correct":false}}],
        "acceptedAnswers":[],"questionCitations":[{{"sourceId":"S1","evidenceQuote":"{quote}"}}],
        "answerCitations":[{{"sourceId":"S1","evidenceQuote":"{quote}"}}],
        "explanationCitations":[{{"sourceId":"S1","evidenceQuote":"{quote}"}}]}}]}}"""
        return GeminiResult(answer, "test-model", TokenUsage(10, 10, 20))


def _headers(user: str) -> dict[str, str]:
    return {"X-Internal-API-Key": "test-internal-key", "X-User-Id": user}


def test_upload_search_delete_and_two_user_isolation(settings) -> None:
    settings.rag_min_score = -1
    with TestClient(create_app(settings=settings, embedding_service=DeterministicEmbedding())) as client:
        uploaded = client.post(
            "/api/v1/user-documents",
            headers=_headers("user-a"),
            files={"file": ("private.txt", "Nội dung bí mật của user A", "text/plain")},
        )
        assert uploaded.status_code == 201, uploaded.text
        document_id = uploaded.json()["id"]
        assert uploaded.json()["status"] == "READY"
        assert "stored" not in uploaded.text.casefold()

        assert client.get(
            f"/api/v1/user-documents/{document_id}", headers=_headers("user-b")
        ).status_code == 404
        invalid_selection = client.post(
            "/api/v1/user-rag/search",
            headers=_headers("user-b"),
            json={"question": "bí mật", "documentIds": [document_id]},
        )
        assert invalid_selection.status_code == 422
        assert invalid_selection.json()["code"] == "INVALID_DOCUMENT_SELECTION"

        uploaded_b = client.post(
            "/api/v1/user-documents",
            headers=_headers("user-b"),
            files={"file": ("other.txt", "Nội dung chỉ thuộc user B", "text/plain")},
        )
        assert uploaded_b.status_code == 201
        document_b = uploaded_b.json()["id"]
        search_b = client.post(
            "/api/v1/user-rag/search",
            headers=_headers("user-b"),
            json={"question": "nội dung"},
        )
        assert {item["documentId"] for item in search_b.json()["results"]} == {document_b}
        assert len(list(Path(settings.user_index_dir).glob("*/manifest.json"))) == 2

        own_search = client.post(
            "/api/v1/user-rag/search",
            headers=_headers("user-a"),
            json={"question": "bí mật", "documentIds": [document_id]},
        )
        assert own_search.status_code == 200, own_search.text
        assert {item["documentId"] for item in own_search.json()["results"]} == {document_id}
        assert all("path" not in key.casefold() for item in own_search.json()["results"] for key in item)

        deleted = client.delete(
            f"/api/v1/user-documents/{document_id}", headers=_headers("user-a")
        )
        assert deleted.status_code == 204
        after_delete = client.post(
            "/api/v1/user-rag/search",
            headers=_headers("user-a"),
            json={"question": "bí mật"},
        )
        assert after_delete.status_code == 200
        assert after_delete.json()["results"] == []
        assert client.delete(
            f"/api/v1/user-documents/{document_b}", headers=_headers("user-b")
        ).status_code == 204


def test_user_headers_and_duplicate_are_rejected(settings) -> None:
    with TestClient(create_app(settings=settings, embedding_service=DeterministicEmbedding())) as client:
        missing = client.get(
            "/api/v1/user-documents", headers={"X-Internal-API-Key": "test-internal-key"}
        )
        assert missing.status_code == 401
        invalid = client.get(
            "/api/v1/user-documents", headers=_headers("../../escape")
        )
        assert invalid.status_code == 422
        first = client.post(
            "/api/v1/user-documents",
            headers=_headers("user-a"),
            files={"file": ("same.txt", "same content", "text/plain")},
        )
        assert first.status_code == 201
        duplicate = client.post(
            "/api/v1/user-documents",
            headers=_headers("user-a"),
            files={"file": ("copy.txt", "same content", "text/plain")},
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["code"] == "DUPLICATE_DOCUMENT"


def test_user_search_rejects_null_and_non_ready_document_ids(settings) -> None:
    with TestClient(create_app(settings=settings, embedding_service=DeterministicEmbedding())) as client:
        null_id = client.post(
            "/api/v1/user-rag/search",
            headers=_headers("user-a"),
            json={"question": "Embedding là gì?", "documentIds": [None]},
        )
        assert null_id.status_code == 422
        assert null_id.json()["code"] == "VALIDATION_ERROR"
        assert null_id.json()["details"][0]["field"] == "documentIds.0"

        unknown_id = client.post(
            "/api/v1/user-rag/search",
            headers=_headers("user-a"),
            json={
                "question": "Embedding là gì?",
                "documentIds": ["00000000-0000-0000-0000-000000000000"],
            },
        )
        assert unknown_id.status_code == 422
        assert unknown_id.json()["code"] == "INVALID_DOCUMENT_SELECTION"


def test_v2_chunks_and_grounded_quiz_include_location_and_citations(settings) -> None:
    settings.rag_min_score = -1
    with TestClient(create_app(
        settings=settings,
        embedding_service=DeterministicEmbedding(),
        gemini_service=QuizGemini(),
    )) as client:
        uploaded = client.post(
            "/api/v1/user-documents",
            headers=_headers("user-a"),
            files={"file": (
                "lesson.txt",
                "Nguồn kiến thức chính xác để tạo câu hỏi RAG. "
                "Retrieval giúp tìm đoạn tài liệu liên quan và generation dùng đoạn đó "
                "để tạo câu trả lời có căn cứ cùng trích dẫn rõ ràng.",
                "text/plain",
            )},
        )
        document_id = uploaded.json()["id"]
        chunks = client.get(
            f"/api/v2/user-documents/{document_id}/chunks",
            headers=_headers("user-a"),
        )
        assert chunks.status_code == 200
        assert chunks.json()["items"][0]["chunkIndex"] == 0
        generated = client.post(
            "/api/v2/user-rag/generate-quiz",
            headers=_headers("user-a"),
            json={
                "documentIds": [document_id], "title": "RAG", "difficulty": "EASY",
                "questionCounts": {"singleChoice": 1, "multipleSelect": 0, "fillBlank": 0},
            },
        )
        assert generated.status_code == 200, generated.text
        question = generated.json()["questions"][0]
        assert question["difficulty"] == "EASY"
        assert question["questionCitations"][0]["chunkIndex"] == 0
        assert question["answerCitations"][0]["evidenceQuote"].startswith("Nguồn kiến thức")
        assert question["explanationCitations"][0]["chunkIndex"] == 0
        streamed = client.post(
            "/api/v2/user-rag/generate-quiz/stream",
            headers=_headers("user-a"),
            json={
                "documentIds": [document_id],
                "title": "RAG",
                "difficulty": "EASY",
                "questionCounts": {
                    "singleChoice": 1,
                    "multipleSelect": 0,
                    "fillBlank": 0,
                },
            },
        )
        assert streamed.status_code == 200
        assert streamed.headers["content-type"].startswith(
            "application/x-ndjson"
        )
        events = [
            json.loads(line)
            for line in streamed.text.splitlines()
            if line.strip()
        ]
        assert events[0]["stage"] == "RETRIEVING"
        assert any(event["type"] == "PROVIDER_STARTED" for event in events)
        assert events[-1]["type"] == "RESULT"


def test_unexpected_stream_failure_is_terminal_and_keeps_safe_stage() -> None:
    event = _unexpected_stream_failure(
        request_id="job-123",
        stage="MATCHING_CITATIONS",
        error_id="rag-error-456",
    )

    assert event["errorCode"] == "RAG_INTERNAL_ERROR"
    assert event["retryable"] is False
    assert event["stage"] == "MATCHING_CITATIONS"
    assert event["details"] == [{
        "reason": "UNEXPECTED_INTERNAL_ERROR",
        "stage": "MATCHING_CITATIONS",
        "errorId": "rag-error-456",
    }]


def test_stream_emits_heartbeat_while_processing_is_silent() -> None:
    async def scenario() -> list[dict[str, object]]:
        queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()

        async def producer() -> None:
            await asyncio.sleep(0.03)
            await queue.put({"type": "RESULT", "data": {}})
            await queue.put(None)

        task = asyncio.create_task(producer())
        chunks = [
            chunk
            async for chunk in _stream_ndjson(
                queue, task, heartbeat_seconds=0.005
            )
        ]
        return [json.loads(chunk) for chunk in chunks]

    events = asyncio.run(scenario())

    assert any(event["type"] == "HEARTBEAT" for event in events)
    assert events[-1]["type"] == "RESULT"


def test_grounded_quiz_uses_selected_document_below_search_threshold(settings) -> None:
    gemini = CohesionQuizGemini()
    with TestClient(create_app(
        settings=settings,
        embedding_service=LowSimilarityEmbedding(),
        gemini_service=gemini,
    )) as client:
        uploaded = client.post(
            "/api/v1/user-documents",
            headers=_headers("user-a"),
            files={"file": (
                "rag-step6-test.txt",
                "Functional Cohesion là loại cohesion trong đó tất cả các thành phần "
                "cùng phối hợp để thực hiện một chức năng duy nhất. "
                "Đây là loại cohesion tốt nhất vì module có trách nhiệm rõ ràng.",
                "text/plain",
            )},
        )
        document_id = uploaded.json()["id"]

        generated = client.post(
            "/api/v2/user-rag/generate-quiz",
            headers=_headers("user-a"),
            json={
                "documentIds": [document_id],
                "title": "Kiểm thử kiến thức",
                "difficulty": "EASY",
                "questionCounts": {
                    "singleChoice": 1,
                    "multipleSelect": 0,
                    "fillBlank": 0,
                },
            },
        )

        assert generated.status_code == 200, generated.text
        assert gemini.called is True


def test_cognitive_question_plan_is_canonical_without_legacy_difficulty_plan(settings) -> None:
    gemini = CognitiveQuizGemini()
    with TestClient(create_app(
        settings=settings,
        embedding_service=DeterministicEmbedding(),
        gemini_service=gemini,
    )) as client:
        uploaded = client.post(
            "/api/v1/user-documents",
            headers=_headers("user-a"),
            files={"file": (
                "cognitive.txt",
                "RAG combines retrieval and generation. Retrieval finds relevant document "
                "chunks and generation uses those chunks to create grounded answers with citations.",
                "text/plain",
            )},
        )

        generated = client.post(
            "/api/v2/user-rag/generate-quiz",
            headers=_headers("user-a"),
            json={
                "documentIds": [uploaded.json()["id"]],
                "title": "RAG fundamentals",
                "cognitiveMode": "BALANCED",
                "questionCounts": {
                    "singleChoice": 1, "multipleSelect": 0, "fillBlank": 0,
                },
                "batchIndex": 0,
                "totalBatches": 1,
                "questionPlan": [{
                    "planSlotId": "B1Q1",
                    "questionType": "SINGLE_CHOICE",
                    "cognitiveLevel": "L1",
                    "constraint": {
                        "cognitiveLevel": "L1",
                        "conceptMin": 1,
                        "conceptMax": 1,
                        "reasoningMin": 0,
                        "reasoningMax": 0,
                        "requiresNovelScenario": False,
                        "answerDirectlyPresent": True,
                        "requiresComparison": False,
                        "scoreMin": 1,
                        "scoreMax": 2,
                    },
                }],
            },
        )

        assert generated.status_code == 200, generated.text
        assert gemini.called is True
        assert generated.json()["questions"][0]["cognitiveLevel"] == "L1"
        assert generated.json()["questions"][0]["difficulty"] == "EASY"


def test_cognitive_levels_are_rejected_in_deprecated_difficulty_plan(settings) -> None:
    with TestClient(create_app(
        settings=settings,
        embedding_service=DeterministicEmbedding(),
    )) as client:
        response = client.post(
            "/api/v2/user-rag/generate-quiz",
            headers=_headers("user-a"),
            json={
                "documentIds": ["00000000-0000-0000-0000-000000000001"],
                "title": "RAG",
                "cognitiveMode": "BALANCED",
                "questionCounts": {
                    "singleChoice": 1, "multipleSelect": 0, "fillBlank": 0,
                },
                "difficultyPlan": ["L1"],
            },
        )

        assert response.status_code == 422
        assert response.json()["code"] == "COGNITIVE_PLAN_INVALID"
        assert response.json()["retryable"] is False

        conflicting = client.post(
            "/api/v2/user-rag/generate-quiz",
            headers=_headers("user-a"),
            json={
                "documentIds": ["00000000-0000-0000-0000-000000000001"],
                "title": "RAG",
                "cognitiveMode": "BALANCED",
                "questionCounts": {
                    "singleChoice": 1, "multipleSelect": 0, "fillBlank": 0,
                },
                "difficultyPlan": ["MEDIUM"],
                "questionPlan": [{
                    "planSlotId": "B1Q1",
                    "questionType": "SINGLE_CHOICE",
                    "cognitiveLevel": "L1",
                    "constraint": {
                        "cognitiveLevel": "L1",
                        "conceptMin": 1,
                        "conceptMax": 1,
                        "reasoningMin": 0,
                        "reasoningMax": 0,
                        "requiresNovelScenario": False,
                        "answerDirectlyPresent": True,
                        "requiresComparison": False,
                        "scoreMin": 1,
                        "scoreMax": 2,
                    },
                }],
            },
        )
        assert conflicting.status_code == 422
        assert conflicting.json()["code"] == "COGNITIVE_PLAN_INVALID"


def test_invalid_cognitive_checkpoint_has_a_specific_error_code(settings) -> None:
    with TestClient(create_app(
        settings=settings,
        embedding_service=DeterministicEmbedding(),
    )) as client:
        response = client.post(
            "/api/v2/user-rag/generate-quiz",
            headers=_headers("user-a"),
            json={
                "documentIds": ["00000000-0000-0000-0000-000000000001"],
                "title": "RAG",
                "cognitiveMode": "L1",
                "questionCounts": {
                    "singleChoice": 1, "multipleSelect": 0, "fillBlank": 0,
                },
                "questionPlan": [{
                    "planSlotId": "B1Q1",
                    "questionType": "SINGLE_CHOICE",
                    "cognitiveLevel": "L1",
                    "constraint": {
                        "cognitiveLevel": "L1",
                        "conceptMin": 1,
                        "conceptMax": 1,
                        "reasoningMin": 0,
                        "reasoningMax": 0,
                        "requiresNovelScenario": False,
                        "answerDirectlyPresent": True,
                        "requiresComparison": False,
                        "scoreMin": 1,
                        "scoreMax": 2,
                    },
                }],
                "acceptedQuestions": [{
                    "type": "SINGLE_CHOICE",
                    "difficulty": "EASY",
                    "planSlotId": "B1Q2",
                    "cognitiveLevel": "L1",
                    "complexityProfile": {
                        "conceptCount": 1,
                        "reasoningStepCount": 0,
                        "requiresNovelScenario": False,
                        "answerDirectlyPresent": True,
                        "requiresComparison": False,
                        "conceptsUsed": ["RAG"],
                    },
                    "prompt": "RAG là gì?",
                    "explanation": "Giải thích.",
                    "options": [
                        {"text": "A", "correct": True},
                        {"text": "B", "correct": False},
                    ],
                    "acceptedAnswers": [],
                    "questionCitations": [{
                        "sourceId": "S1", "evidenceQuote": "RAG",
                    }],
                    "answerCitations": [{
                        "sourceId": "S1", "evidenceQuote": "RAG",
                    }],
                    "explanationCitations": [{
                        "sourceId": "S1", "evidenceQuote": "RAG",
                    }],
                }],
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "COGNITIVE_CHECKPOINT_INVALID"


def test_grounded_quiz_rejects_batches_larger_than_twenty(settings) -> None:
    with TestClient(create_app(
        settings=settings,
        embedding_service=DeterministicEmbedding(),
    )) as client:
        response = client.post(
            "/api/v2/user-rag/generate-quiz",
            headers=_headers("user-a"),
            json={
                "documentIds": ["00000000-0000-0000-0000-000000000001"],
                "title": "RAG",
                "difficulty": "MIXED",
                "questionCounts": {
                        "singleChoice": 21,
                    "multipleSelect": 0,
                    "fillBlank": 0,
                },
            },
        )

        assert response.status_code == 422
        assert response.json()["code"] == "QUIZ_BATCH_TOO_LARGE"


def test_grounded_quiz_keeps_invalid_citation_as_warning(settings) -> None:
    gemini = CitationRepairGemini()
    with TestClient(create_app(
        settings=settings,
        embedding_service=DeterministicEmbedding(),
        gemini_service=gemini,
    )) as client:
        uploaded = client.post(
            "/api/v1/user-documents",
            headers=_headers("user-a"),
            files={"file": (
                "lesson.txt",
                "Nguồn kiến thức chính xác để tạo câu hỏi và giải thích đáp án RAG. "
                "Retrieval tìm các đoạn liên quan, còn generation tạo câu trả lời có căn cứ.",
                "text/plain",
            )},
        )
        generated = client.post(
            "/api/v2/user-rag/generate-quiz",
            headers=_headers("user-a"),
            json={
                "documentIds": [uploaded.json()["id"]],
                "title": "RAG",
                "difficulty": "EASY",
                "questionCounts": {
                    "singleChoice": 1, "multipleSelect": 0, "fillBlank": 0,
                },
            },
        )

        assert generated.status_code == 200, generated.text
        assert gemini.calls == 1
        assert generated.json()["validationStatus"] == "WARNING"
        assert generated.json()["warningCount"] == 1
        assert generated.json()["questions"][0]["questionCitations"] == []
        assert generated.json()["questions"][0]["prompt"] == "RAG là gì?"


def test_user_search_still_applies_similarity_threshold(settings) -> None:
    with TestClient(create_app(
        settings=settings,
        embedding_service=LowSimilarityEmbedding(),
    )) as client:
        uploaded = client.post(
            "/api/v1/user-documents",
            headers=_headers("user-a"),
            files={"file": (
                "lesson.txt",
                "Nội dung tài liệu đủ dài để kiểm tra rằng search thông thường "
                "vẫn áp dụng ngưỡng tương đồng và không trả kết quả không liên quan.",
                "text/plain",
            )},
        )

        searched = client.post(
            "/api/v1/user-rag/search",
            headers=_headers("user-a"),
            json={
                "question": "Một câu hỏi hoàn toàn không liên quan",
                "documentIds": [uploaded.json()["id"]],
            },
        )

        assert searched.status_code == 200
        assert searched.json()["results"] == []


def test_mime_executable_and_size_limits_are_enforced(settings) -> None:
    settings.max_upload_size_mb = 1
    with TestClient(create_app(settings=settings, embedding_service=DeterministicEmbedding())) as client:
        mismatch = client.post(
            "/api/v1/user-documents",
            headers=_headers("user-a"),
            files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
        )
        assert mismatch.status_code == 415
        assert mismatch.json()["code"] == "FILE_TYPE_MISMATCH"
        executable = client.post(
            "/api/v1/user-documents",
            headers=_headers("user-a"),
            files={"file": ("danger.txt", b"MZ executable", "text/plain")},
        )
        assert executable.status_code == 415
        assert executable.json()["code"] == "EXECUTABLE_FILE_BLOCKED"
        oversized = client.post(
            "/api/v1/user-documents",
            headers=_headers("user-a"),
            files={"file": ("large.txt", b"a" * (1024 * 1024 + 1), "text/plain")},
        )
        assert oversized.status_code == 413
        assert oversized.json()["code"] == "FILE_TOO_LARGE"


def test_embedding_failure_keeps_previous_index_and_cleans_new_file(settings) -> None:
    embedding = FailingEmbedding()
    settings.rag_min_score = -1
    with TestClient(create_app(settings=settings, embedding_service=embedding)) as client:
        first = client.post(
            "/api/v1/user-documents",
            headers=_headers("user-a"),
            files={"file": ("first.txt", "Tài liệu đầu tiên", "text/plain")},
        )
        assert first.status_code == 201
        first_id = first.json()["id"]
        embedding.fail = True
        failed = client.post(
            "/api/v1/user-documents",
            headers=_headers("user-a"),
            files={"file": ("second.txt", "Tài liệu sẽ lỗi", "text/plain")},
        )
        assert failed.status_code == 503
        assert failed.json()["code"] == "EMBEDDING_MODEL_UNAVAILABLE"
        failures = client.get(
            "/api/v1/user-documents?status=FAILED", headers=_headers("user-a")
        ).json()["items"]
        assert len(failures) == 1
        failed_id = failures[0]["id"]
        assert not list(Path(settings.user_upload_dir).glob(f"*/{failed_id}/original-file"))
        embedding.fail = False
        search = client.post(
            "/api/v1/user-rag/search",
            headers=_headers("user-a"),
            json={"question": "đầu tiên"},
        )
        assert {item["documentId"] for item in search.json()["results"]} == {first_id}
