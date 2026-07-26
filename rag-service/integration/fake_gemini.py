import json

from fastapi import FastAPI, Request

app = FastAPI()


@app.post("/{path:path}")
async def generate(path: str, request: Request) -> dict:
    body = await request.json()
    prompt = json.dumps(body, ensure_ascii=False)
    if "standaloneQuestion" in prompt:
        text = json.dumps({"standaloneQuestion": "Câu hỏi độc lập", "rewritten": False})
    else:
        text = json.dumps(
            {"answer": "Câu trả lời kiểm thử [S1]", "usedSourceIds": ["S1"], "insufficientContext": False}
        )
    return {
        "candidates": [
            {"content": {"parts": [{"text": text}], "role": "model"}, "finishReason": "STOP"}
        ],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 10, "totalTokenCount": 20},
        "modelVersion": "fake-gemini",
    }
