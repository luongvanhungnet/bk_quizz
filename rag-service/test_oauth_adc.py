import json
import sys

import google.auth
from google.auth.transport.requests import AuthorizedSession


SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/generative-language.retriever",
]

MODEL = "gemini-3.6-flash"


def main() -> None:
    print("Python:", sys.executable)

    credentials, project_id = google.auth.default(scopes=SCOPES)

    quota_project = getattr(credentials, "quota_project_id", None)

    print("\n=== ADC ===")
    print("Credential type:", type(credentials).__name__)
    print("Project ID:", project_id)
    print("Quota project:", quota_project)
    print("Valid before request:", credentials.valid)

    if not quota_project:
        raise RuntimeError(
            "ADC has no quota_project_id. Run: "
            "gcloud auth application-default set-quota-project PROJECT_ID"
        )

    session = AuthorizedSession(credentials)

    url = (
        "https://generativelanguage.googleapis.com/v1/"
        f"models/{MODEL}:generateContent"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": "Reply exactly with OK"
                    }
                ]
            }
        ]
    }

    response = session.post(
        url,
        headers={
            "x-goog-user-project": quota_project,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )

    print("\n=== HTTP ===")
    print("Status:", response.status_code)

    try:
        data = response.json()
    except ValueError:
        print("Raw response:", response.text)
        response.raise_for_status()
        return

    if not response.ok:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        response.raise_for_status()

    print(json.dumps(data, indent=2, ensure_ascii=False))

    text = (
        data["candidates"][0]
        ["content"]["parts"][0]["text"]
    )

    print("\nGemini response:", text)
        
    models_response = session.get(
        "https://generativelanguage.googleapis.com/v1/models",
        headers={
            "x-goog-user-project": quota_project,
        },
        timeout=60,
    )

    models_response.raise_for_status()

    models = models_response.json()["models"]

    for model in models:
        print(model["name"])


if __name__ == "__main__":
    main()

