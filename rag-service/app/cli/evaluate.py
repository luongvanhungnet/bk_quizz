import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Đánh giá retrieval và grounded answer của BKQuiz RAG.")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-generation", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    internal = os.getenv("SPRING_BOOT_INTERNAL_API_KEY", "")
    debug = os.getenv("RAG_DEBUG_API_KEY", "")
    if not internal or not debug:
        raise SystemExit("Thiếu SPRING_BOOT_INTERNAL_API_KEY hoặc RAG_DEBUG_API_KEY.")
    dataset = json.loads(args.dataset.read_text(encoding="utf-8-sig"))
    headers = {"X-Internal-API-Key": internal, "X-Debug-RAG-Key": debug, "X-User-Id": args.user_id}
    reports: dict[str, dict[str, Any]] = {}
    citation_valid = refusal_valid = gemini_errors = generated = total_tokens = 0
    generation_latencies: list[float] = []
    with httpx.Client(timeout=300) as client:
        retrieval_items = [
            {key: item[key] for key in ("question", "expectedDocumentIds", "expectedPageNumbers") if key in item}
            for item in dataset
        ]
        for mode in ("baseline", "hybrid"):
            response = client.post(
                f"{args.base_url.rstrip('/')}/api/v1/evaluation/retrieval",
                params={"k": args.k, "mode": mode}, headers=headers, json=retrieval_items,
            )
            response.raise_for_status()
            reports[mode] = response.json()
        if not args.skip_generation:
            for item in dataset:
                started = time.perf_counter()
                response = client.post(
                    f"{args.base_url.rstrip('/')}/api/v2/user-rag/ask", headers=headers,
                    json={"question": item["question"], "topK": args.k,
                          "documentIds": item.get("documentIds"), "includeSystemDocuments": False},
                )
                generation_latencies.append((time.perf_counter() - started) * 1000)
                if response.status_code >= 400:
                    gemini_errors += 1
                    continue
                body = response.json()
                generated += 1
                total_tokens += body.get("usage", {}).get("totalTokens", 0)
                returned = {source["documentId"] for source in body.get("sources", [])}
                if returned.issubset(set(item.get("expectedDocumentIds", []))):
                    citation_valid += 1
                if bool(body.get("insufficientContext")) == (not item.get("expectedAnswerable", True)):
                    refusal_valid += 1
    baseline, hybrid = reports["baseline"], reports["hybrid"]
    price = float(os.getenv("EVALUATION_PRICE_PER_MILLION_TOKENS", "0") or 0)
    report = {
        "dataset": str(args.dataset), "k": args.k, "queryCount": len(dataset),
        "baseline": baseline, "hybrid": hybrid,
        "delta": {key: round(hybrid[key] - baseline[key], 6) for key in ("hitRate", "recall", "mrr", "meanLatencyMs", "p95LatencyMs")},
        "generation": {
            "citationAccuracy": round(citation_valid / generated, 6) if generated else None,
            "refusalAccuracy": round(refusal_valid / generated, 6) if generated else None,
            "meanLatencyMs": round(sum(generation_latencies) / len(generation_latencies), 3) if generation_latencies else None,
            "geminiErrorRate": round(gemini_errors / len(dataset), 6) if dataset else 0,
            "estimatedCost": round(total_tokens / 1_000_000 * price, 8) if price else None,
        },
    }
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output)
    allowed_drop = float(os.getenv("EVALUATION_MAX_RECALL_DROP", "0.02"))
    return 2 if hybrid["recall"] < baseline["recall"] - allowed_drop or (generated and citation_valid != generated) else 0


if __name__ == "__main__":
    raise SystemExit(main())
