# Contract tích hợp Spring Boot → BKQuiz RAG v2

Frontend chỉ gọi Spring Boot. Spring Boot lấy user ID từ JWT principal đã xác thực và gọi RAG qua mạng nội bộ; không trả internal key, Redis URL, Gemini key hoặc Python URL cho trình duyệt.

## Kết nối và headers

| Môi trường | Base URL |
|---|---|
| Local | `http://127.0.0.1:8000/api/v2` |
| Root Docker profile `rag` | `http://rag-api:8000/api/v2` |

Mọi endpoint nghiệp vụ cần:

- `X-Internal-API-Key`: secret server-to-server; có thể rotate bằng current/previous key.
- `X-User-Id`: UUID/string canonical lấy từ principal, không lấy từ body/query của frontend.
- `X-Classroom-Id`: chỉ gửi khi Spring đã kiểm tra quyền lớp học.
- `X-Request-Id`: truyền trace ID hiện tại; response luôn phản hồi cùng header.

## Upload và polling

`POST /user-documents`, multipart field `file`, header `Idempotency-Key` ổn định theo một lần upload. Timeout đề xuất 30 giây vì endpoint chỉ stream/validate/lưu file.

```json
{
  "documentId": "uuid",
  "jobId": "uuid",
  "documentStatus": "PROCESSING",
  "jobStatus": "PENDING"
}
```

Spring trả `202` cho frontend và poll `GET /indexing-jobs/{jobId}` với backoff 1, 2, 4, 8 giây, tối đa 10 giây. Dừng ở `SUCCEEDED`, `FAILED`, `CANCELLED`. Các bước/progress chuẩn: `VALIDATING 10`, `PARSING 30`, `CHUNKING 50`, `EMBEDDING 70`, `COMMITTING 90`, `SUCCEEDED 100`.

- `POST /indexing-jobs/{id}/retry`: chỉ `FAILED|CANCELLED`.
- `POST /indexing-jobs/{id}/cancel`: idempotent; worker kiểm tra hủy giữa các bước.
- Job/document user khác luôn trả 404.

## Tài liệu và RAG

- `GET /user-documents?page=1&size=20&status=READY`
- `GET /user-documents/{id}`
- `GET /user-documents/{id}/chunks?page=1&size=500`: đồng bộ chunk ID, text, trang/slide/heading về PostgreSQL.
- `DELETE /user-documents/{id}`: hủy job chưa xong, loại khỏi search ngay.
- `POST /user-rag/search`: body `{question,topK?,documentIds?,conversationHistory?,debug?}`.
- `POST /user-rag/ask`: thêm `includeSystemDocuments`.
- `POST /user-rag/generate-quiz`: sinh quiz structured output; mọi câu bắt buộc có nguồn riêng cho câu hỏi, đáp án và phần giải thích.
- `DELETE /users/{userId}/data`: Spring chỉ gọi khi path user trùng principal; xóa file, metadata, job, audit, index và cache tenant.

Timeout đề xuất: search 15 giây, ask 75 giây, delete 30 giây. Không tự retry ask nếu chưa có idempotency ở tầng Spring. Có thể retry GET, upload với cùng idempotency key, và lỗi có `retryable=true` theo `retryAfterSeconds`.

## Error contract v2

```json
{
  "timestamp": "2026-07-18T12:00:00Z",
  "requestId": "trace-id",
  "status": 429,
  "code": "RATE_LIMITED",
  "message": "Bạn đã gửi quá nhiều yêu cầu. Vui lòng thử lại sau.",
  "retryable": true,
  "retryAfterSeconds": 30,
  "details": []
}
```

| Nhóm | Code chính | Xử lý |
|---|---|---|
| Auth/context | `INVALID_INTERNAL_API_KEY`, `USER_CONTEXT_REQUIRED` | Không retry; kiểm tra cấu hình/JWT mapping |
| Validation | `VALIDATION_ERROR`, `FILE_TOO_LARGE`, `DUPLICATE_DOCUMENT` | Không retry tự động |
| Queue/Redis | `JOB_QUEUE_UNAVAILABLE`, `RATE_LIMIT_STORE_UNAVAILABLE`, `INDEX_LOCK_UNAVAILABLE`, `INDEX_MUTATION_IN_PROGRESS` | Retry theo `retryAfterSeconds`; production không fallback local lock |
| Job | `INDEXING_JOB_NOT_FOUND`, `JOB_NOT_RETRYABLE` | Hiển thị trạng thái cụ thể |
| Gemini | `GEMINI_RATE_LIMITED`, `GEMINI_QUOTA_EXHAUSTED`, `GEMINI_TIMEOUT`, `GEMINI_MODEL_UNAVAILABLE`, `GEMINI_SAFETY_BLOCKED`, `GEMINI_AUTH_ERROR`, `AI_SERVICE_TEMPORARILY_UNAVAILABLE` | Chỉ retry khi `retryable=true` |
| Retrieval | `INVALID_DOCUMENT_SELECTION`, `USER_INDEX_REBUILD_REQUIRED` | Không đổi tenant/filter; yêu cầu rebuild khi cần |

## Health và vận hành

- `GET /health/live`: liveness, không gọi dependency.
- `GET /health/ready`: SQLite, Redis, storage/disk, embedding và cấu hình Gemini; không gọi Gemini.
- `GET /metrics`: Prometheus API metrics.
- Worker metrics: cổng nội bộ `9101`.

OpenAPI đã commit tại [openapi.json](openapi.json). CI chạy `python scripts/export_openapi.py` rồi kiểm tra Git diff để phát hiện contract drift.

## Điểm nối với backend hiện tại

Spring lưu cặp `sourceDocumentId ↔ ragDocumentId/jobId`, poll indexing, đồng bộ chunk và chỉ cho sinh quiz khi nguồn đã `READY`. Frontend không được truyền `X-User-Id`; Spring luôn lấy owner từ principal hoặc resource đã kiểm tra quyền.
