from fastapi.testclient import TestClient

HEADERS = {"X-Internal-API-Key": "test-internal-key"}


def test_chat_requires_internal_key(client: TestClient) -> None:
    response = client.post("/api/v1/chat", json={"message": "Xin chào"})

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_INTERNAL_API_KEY"


def test_chat_rejects_wrong_internal_key(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat",
        headers={"X-Internal-API-Key": "wrong"},
        json={"message": "Xin chào"},
    )

    assert response.status_code == 401


def test_chat_rejects_blank_message(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat", headers=HEADERS, json={"message": "   "}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["message"] == "Dữ liệu gửi lên không hợp lệ."


def test_chat_rejects_too_short_message(client: TestClient) -> None:
    response = client.post("/api/v1/chat", headers=HEADERS, json={"message": "a"})

    assert response.status_code == 422


def test_chat_rejects_too_long_message(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat", headers=HEADERS, json={"message": "a" * 5001}
    )

    assert response.status_code == 422


def test_chat_reports_missing_gemini_configuration(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat", headers=HEADERS, json={"message": "Xin chào"}
    )

    assert response.status_code == 503
    assert response.json()["code"] == "GEMINI_NOT_CONFIGURED"
    assert response.headers["X-Request-Id"] == response.json()["traceId"]
