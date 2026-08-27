import json

from app.services.gemini_service import GeminiResult, TokenUsage


def _headers(user: str = "user-a") -> dict[str, str]:
    return {
        "X-Internal-API-Key": "test-internal-key",
        "X-User-Id": user,
    }


class TutorGemini:
    async def generate_stream(self, message: str, *, on_delta, **kwargs):
        assert '"prompt":"2 + 2 bằng bao nhiêu?"' in message
        await on_delta("Đáp án là $4$ ")
        await on_delta("[S1].")
        return GeminiResult("Đáp án là $4$ [S1].", "test-model", TokenUsage(20, 8, 28))


def test_attempt_tutor_streams_answer_and_only_referenced_sources(client) -> None:
    client.app.state.gemini_service = TutorGemini()
    response = client.post(
        "/api/v2/attempt-tutor/chat/stream",
        headers=_headers(),
        json={
            "questionNumber": 1,
            "questionType": "SINGLE_CHOICE",
            "prompt": "2 + 2 bằng bao nhiêu?",
            "options": ["3", "4"],
            "learnerAnswer": "3",
            "correctAnswer": "4",
            "explanation": "Phép cộng cơ bản.",
            "sources": [
                {
                    "sourceId": "S1",
                    "sourceChunkId": "11111111-1111-1111-1111-111111111111",
                    "sourceDocumentId": "22222222-2222-2222-2222-222222222222",
                    "filename": "math.pdf",
                    "pageNumber": 1,
                    "slideNumber": None,
                    "chunkIndex": 0,
                    "heading": None,
                    "evidenceQuote": "Hai cộng hai bằng bốn.",
                },
                {
                    "sourceId": "S2",
                    "filename": "unused.pdf",
                    "chunkIndex": 1,
                    "evidenceQuote": "Nguồn không được sử dụng.",
                },
            ],
            "conversationHistory": [],
            "message": "Giải thích giúp tôi.",
        },
    )

    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line]
    assert [event["type"] for event in events] == [
        "STARTED", "DELTA", "DELTA", "SOURCES", "COMPLETED"
    ]
    assert [source["sourceId"] for source in events[-2]["sources"]] == ["S1"]
    assert events[-1]["usage"]["totalTokens"] == 28
