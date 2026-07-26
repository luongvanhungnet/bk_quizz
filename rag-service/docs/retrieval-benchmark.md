# Phase 4 retrieval benchmark

Ngày chạy: 2026-07-18  
Môi trường: Windows, CPU local, Python 3.11  
Reranker: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`

Fixture nhỏ gồm 50 chunk và 10 query chứa mã kỹ thuật. Vector-only cố ý nhận một
biểu diễn semantic không đủ để tìm mã; BM25 có thể tìm exact keyword. Mỗi query dùng
namespace cache riêng để đo retrieval thực thay vì cache hit.

| Mode | Hit Rate@1 | MRR | Mean (ms) | P50 (ms) | P95 (ms) |
|---|---:|---:|---:|---:|---:|
| Baseline vector-only | 0.000 | 0.000 | 0.480 | 0.194 | 1.800 |
| Hybrid + local reranker | 1.000 | 1.000 | 272.972 | 274.541 | 297.840 |

Kết luận: quality gate đạt trên fixture mã kỹ thuật, nhưng tiêu chí P95 không quá 3 lần
baseline không đạt trên microbenchmark này vì baseline dùng embedding xác định gần như
không tốn CPU, trong khi CrossEncoder thực hiện inference thật. Đây không phải benchmark
production đại diện; cần chạy `scripts/evaluate_retrieval.py` trên dataset BKQuiz thật.

Nếu latency production vượt ngân sách, có thể giảm `RERANK_CANDIDATES`, tắt
`RERANKER_ENABLED` để dùng RRF, hoặc triển khai backend ONNX/quantized trong một đợt tối
ưu riêng. Không hạ các mặc định Phase 4 chỉ dựa trên fixture tổng hợp này.
