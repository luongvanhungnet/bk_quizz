from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer
from sentence_transformers.backend import export_dynamic_quantized_onnx_model

SAMPLES = [
    "Embedding biểu diễn ý nghĩa của văn bản.",
    "Hybrid retrieval combines vector search and BM25.",
    "BKQuiz tạo câu hỏi có trích dẫn nguồn.",
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Chuẩn bị embedding ONNX int8 cho BKQuiz RAG.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", default="data/models/embedding-onnx")
    parser.add_argument("--max-cosine-drift", type=float, default=0.01)
    args = parser.parse_args()

    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)

    torch_model = SentenceTransformer(args.model, device="cpu", backend="torch")
    reference = torch_model.encode(SAMPLES, normalize_embeddings=True, convert_to_numpy=True)

    onnx_model = SentenceTransformer(args.model, device="cpu", backend="onnx")
    onnx_model.save_pretrained(str(output))
    export_dynamic_quantized_onnx_model(
        onnx_model,
        "avx2",
        str(output),
        file_suffix="qint8_avx2",
    )

    quantized = SentenceTransformer(
        str(output),
        device="cpu",
        backend="onnx",
        model_kwargs={"file_name": "onnx/model_qint8_avx2.onnx"},
    )
    candidate = quantized.encode(SAMPLES, normalize_embeddings=True, convert_to_numpy=True)
    cosine_drift = float(np.max(np.abs(np.sum(reference * candidate, axis=1) - 1.0)))
    print(f"ONNX model: {output}")
    print(f"Max cosine drift: {cosine_drift:.6f}")
    if cosine_drift > args.max_cosine_drift:
        print("FAILED: cosine drift vượt ngưỡng; runtime sẽ tiếp tục dùng Torch.")
        return 2
    print("OK: đặt EMBEDDING_BACKEND=onnx và EMBEDDING_PRECISION=int8.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
