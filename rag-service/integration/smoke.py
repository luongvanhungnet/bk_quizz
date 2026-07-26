import os
import time

import httpx

BASE = os.getenv("RAG_BASE_URL", "http://rag-api:8000/api/v2")
KEY = os.getenv("SPRING_BOOT_INTERNAL_API_KEY", "integration-secret")
USER_A = "00000000-0000-0000-0000-00000000000a"
USER_B = "00000000-0000-0000-0000-00000000000b"


def headers(user: str) -> dict[str, str]:
    return {"X-Internal-API-Key": KEY, "X-User-Id": user, "X-Request-Id": "phase5-integration"}


def main() -> int:
    with httpx.Client(timeout=90) as client:
        upload = client.post(
            f"{BASE}/user-documents", headers={**headers(USER_A), "Idempotency-Key": "integration-upload-1"},
            files={"file": ("integration.txt", "BKQuiz integration retrieval content", "text/plain")},
        )
        upload.raise_for_status()
        ids = upload.json()
        for _ in range(90):
            job = client.get(f"{BASE}/indexing-jobs/{ids['jobId']}", headers=headers(USER_A))
            job.raise_for_status()
            if job.json()["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                break
            time.sleep(2)
        assert job.json()["status"] == "SUCCEEDED", job.text
        assert client.get(f"{BASE}/user-documents/{ids['documentId']}", headers=headers(USER_B)).status_code == 404
        ask = client.post(
            f"{BASE}/user-rag/ask", headers=headers(USER_A),
            json={"question": "BKQuiz integration retrieval content", "documentIds": [ids["documentId"]]},
        )
        ask.raise_for_status()
        assert ask.json()["sources"][0]["documentId"] == ids["documentId"]
        deleted = client.delete(f"{BASE}/user-documents/{ids['documentId']}", headers=headers(USER_A))
        assert deleted.status_code == 204
        search = client.post(
            f"{BASE}/user-rag/search", headers=headers(USER_A),
            json={"question": "BKQuiz integration retrieval content"},
        )
        search.raise_for_status()
        assert search.json()["results"] == []
    print("Phase 5 Docker integration passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
