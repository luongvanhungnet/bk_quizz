import argparse
import json
import os
from pathlib import Path

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="So sánh retrieval baseline và hybrid.")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8090")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    internal_key = os.environ.get("SPRING_BOOT_INTERNAL_API_KEY", "")
    debug_key = os.environ.get("RAG_DEBUG_API_KEY", "")
    if not internal_key or not debug_key:
        raise SystemExit("Thiếu SPRING_BOOT_INTERNAL_API_KEY hoặc RAG_DEBUG_API_KEY.")
    dataset = json.loads(args.dataset.read_text(encoding="utf-8-sig"))
    headers = {
        "X-Internal-API-Key": internal_key,
        "X-Debug-RAG-Key": debug_key,
        "X-User-Id": args.user_id,
    }
    reports = {}
    with httpx.Client(timeout=300) as client:
        for mode in ("baseline", "hybrid"):
            response = client.post(
                f"{args.base_url.rstrip('/')}/api/v1/evaluation/retrieval",
                params={"k": args.k, "mode": mode},
                headers=headers,
                json=dataset,
            )
            response.raise_for_status()
            reports[mode] = response.json()
    metrics = ("hitRate", "recall", "mrr", "meanLatencyMs", "p50LatencyMs", "p95LatencyMs")
    report = {
        "dataset": str(args.dataset),
        "k": args.k,
        "queryCount": len(dataset),
        **reports,
        "delta": {
            metric: round(reports["hybrid"][metric] - reports["baseline"][metric], 6)
            for metric in metrics
        },
    }
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
