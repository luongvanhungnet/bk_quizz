import google.auth
from google.auth.transport.requests import AuthorizedSession


SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/generative-language.retriever",
]

PROJECT_ID = "gen-lang-client-0839815713"
MODEL = "gemini-3.6-flash"


credentials, _ = google.auth.default(scopes=SCOPES)

session = AuthorizedSession(credentials)

url = (
    "https://generativelanguage.googleapis.com/v1/"
    f"models/{MODEL}:generateContent"
)

response = session.post(
    url,
    headers={
        "x-goog-user-project": PROJECT_ID,
        "Content-Type": "application/json",
    },
    json={
        "contents": [
            {
                "parts": [
                    {"text": "Reply exactly with OK"}
                ]
            }
        ]
    },
    timeout=60,
)

response.raise_for_status()

data = response.json()

print(data["candidates"][0]["content"]["parts"][0]["text"])