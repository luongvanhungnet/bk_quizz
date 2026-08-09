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