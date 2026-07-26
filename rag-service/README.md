# BKQuiz RAG Service — Phase 4

FastAPI microservice cung cấp Gemini Gateway, RAG tài liệu hệ thống và RAG tài liệu
riêng của người dùng. Embedding chạy local bằng Sentence Transformers, tìm kiếm exact
cosine qua FAISS; Gemini chỉ nhận các chunk đã truy xuất để sinh câu trả lời có nguồn.

## Pipeline Hybrid RAG

```text
Query + conversation history
        │
        ├─ Query rewrite có điều kiện (Gemini structured JSON)
        │
        ├─ FAISS semantic search
        └─ BM25 keyword search local
                    │
              Reciprocal Rank Fusion
                    │
          Cross-Encoder reranker local
                    │
       Dedup + diversity + context budget
                    │
          Gemini grounded structured JSON
                    │
         Citation validation / one repair
```

Hybrid, reranker và rewrite là ba feature flag độc lập. Nếu local reranker không tải
được, service ghi cảnh báo và tiếp tục dùng RRF; không gửi candidate sang dịch vụ ngoài.

## Kiến trúc và giới hạn

- Python 3.11, SQLite/SQLAlchemy/Alembic, FAISS và filesystem local.
- PDF, DOCX, PPTX, TXT, Markdown; file tối đa 20 MB theo mặc định.
- Tài liệu và index tách theo user. Database và metadata chunk đều kiểm tra owner.
- `X-Classroom-Id` chỉ được lưu làm metadata, chưa cấp quyền đọc cho thành viên khác.
- Chạy đúng **một** Uvicorn worker/replica trên volume bền vững. SQLite và lock hiện tại
  không hỗ trợ nhiều replica cùng ghi.
- PPTX lấy text của slide và bỏ notes. PDF scan chưa hỗ trợ OCR.
- Reranker mặc định tải model multilingual khoảng vài trăm MB ở lần khởi động đầu tiên.

## Cài đặt trên PowerShell

```powershell
Set-Location D:\BKQuiz\rag-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Khai báo ít nhất `GEMINI_MODEL`, `SPRING_BOOT_INTERNAL_API_KEY`; khai báo
`GEMINI_API_KEY` khi cần `/chat`, `/rag/ask` hoặc `/user-rag/ask`.

Gemini Free Tier có quota theo project và dữ liệu gửi lên có thể được Google dùng để
cải thiện sản phẩm. Không gửi tài liệu bí mật/nhạy cảm lên Free Tier. Model embedding
mặc định được tải từ Hugging Face ở lần dùng đầu và sau đó sử dụng cache local.

## Migration và khởi động

Service fail-fast nếu database chưa ở Alembic head:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8090
```

Không dùng `--workers` lớn hơn 1. Swagger chỉ bật khi `APP_ENV=development` tại
`http://127.0.0.1:8090/docs`.

## Contract Spring Boot

Frontend không gọi microservice trực tiếp. Spring Boot phải lấy user từ JWT đã xác
thực rồi gắn header:

```text
X-Internal-API-Key: <server-secret>
X-User-Id: <authenticated-user-id>
X-Classroom-Id: <optional-classroom-id>
```

Không chuyển internal key, Gemini key hoặc URL RAG xuống frontend. Thiếu user trả 401;
ID sai định dạng trả 422; truy cập tài liệu user khác trả 404.

Request search/ask chấp nhận thêm `conversationHistory` tối đa 6 message và
`debug=false`. Debug yêu cầu header `X-Debug-RAG-Key`; key này độc lập với internal key.

### Upload và quản lý tài liệu

```powershell
$headers = @{
  "X-Internal-API-Key" = "your-internal-secret"
  "X-User-Id" = "3656e84e-d187-46df-ae36-1a19baf132a4"
}

$upload = curl.exe -s -X POST http://127.0.0.1:8090/api/v1/user-documents `
  -H "X-Internal-API-Key: $($headers['X-Internal-API-Key'])" `
  -H "X-User-Id: $($headers['X-User-Id'])" `
  -F "file=@D:\docs\lesson.pdf;type=application/pdf" | ConvertFrom-Json

$documentId = $upload.id

curl.exe "http://127.0.0.1:8090/api/v1/user-documents?page=1&size=20&status=READY" `
  -H "X-Internal-API-Key: $($headers['X-Internal-API-Key'])" `
  -H "X-User-Id: $($headers['X-User-Id'])"

curl.exe -X DELETE http://127.0.0.1:8090/api/v1/user-documents/<document-id> `
  -H "X-Internal-API-Key: $($headers['X-Internal-API-Key'])" `
  -H "X-User-Id: $($headers['X-User-Id'])"
```

Response tài liệu không chứa stored filename, filesystem path hoặc absolute path.

### Search và hỏi đáp

```powershell
$searchBody = @{
  question = "Định luật được trình bày thế nào?"
  topK = 5
  documentIds = @($documentId)
  debug = $false
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8090/api/v1/user-rag/search `
  -Headers $headers `
  -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($searchBody))

$askBody = @{
  question = "Tóm tắt nội dung chính"
  topK = 5
  documentIds = @($documentId)
  includeSystemDocuments = $true
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8090/api/v1/user-rag/ask `
  -Headers $headers `
  -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($askBody))
```

Windows PowerShell 5.1 có thể mã hóa chuỗi request theo ANSI. Luôn chuyển JSON
sang byte UTF-8 như trên. Nếu upload trả `DUPLICATE_DOCUMENT`, lấy `id` từ API
danh sách tài liệu `READY` thay vì tải lại cùng nội dung.

Nếu không có context, ask trả chính xác `Không tìm thấy đủ thông tin trong tài liệu.`
và không gọi Gemini.

### Debug và đánh giá retrieval

```powershell
curl.exe -X POST "http://127.0.0.1:8090/api/v1/user-rag/search" `
  -H "Content-Type: application/json" `
  -H "X-Internal-API-Key: your-internal-secret" `
  -H "X-Debug-RAG-Key: your-debug-secret" `
  -H "X-User-Id: user-id" `
  -d '{"question":"BK-2026","debug":true}'

$env:SPRING_BOOT_INTERNAL_API_KEY = "your-internal-secret"
$env:RAG_DEBUG_API_KEY = "your-debug-secret"
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py `
  D:\datasets\retrieval.json --user-id user-id --k 5 --output benchmark.json
```

Evaluation chạy vector-only và hybrid trên cùng dataset, tính Hit Rate@k, Recall@k,
MRR, mean/P50/P95 latency và không dùng Gemini làm giám khảo. ID tài liệu trong dataset
phải thuộc user ở header. Debug chỉ trả preview tối đa 200 ký tự.

## Tài liệu hệ thống Phase 2

Đặt PDF/TXT/Markdown trong `data/system-documents/`, sau đó chạy:

```powershell
.\.venv\Scripts\python.exe scripts\index_system_documents.py
.\.venv\Scripts\python.exe scripts\index_system_documents.py --force
```

API cũ `/api/v1/system-documents`, `/api/v1/rag/search`, `/api/v1/rag/ask`,
`/api/v1/chat` và health vẫn giữ nguyên.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app scripts migrations
```

Test không gọi Gemini thật. Bao phủ migration, parser, MIME/signature, upload, duplicate,
phân trang, soft-delete, FAISS/BM25/RRF, reranker, query rewrite, context budget,
grounding/citation, cache, evaluation và cô lập giữa hai user.

## Mã lỗi Phase 3 chính

| HTTP | Code | Ý nghĩa |
|---:|---|---|
| 401 | `USER_CONTEXT_REQUIRED` | Thiếu `X-User-Id` |
| 400 | `INVALID_JSON_BODY` | JSON hỏng hoặc body không được mã hóa UTF-8 |
| 404 | `DOCUMENT_NOT_FOUND` | Không tồn tại hoặc không thuộc owner |
| 409 | `DUPLICATE_DOCUMENT` | Trùng hash trong tài liệu active |
| 409 | `DOCUMENT_QUOTA_EXCEEDED` | Vượt số tài liệu |
| 409 | `STORAGE_QUOTA_EXCEEDED` | Vượt quota dung lượng |
| 413 | `FILE_TOO_LARGE` | File vượt giới hạn |
| 415 | `FILE_TYPE_MISMATCH` | Extension/MIME/signature không khớp |
| 422 | `INVALID_DOCUMENT_SELECTION` | Filter chứa tài liệu không thuộc user/không READY |
| 422 | `SCANNED_PDF_REQUIRES_OCR` | PDF scan không có text |

Mọi lỗi API có `traceId` và response header `X-Request-Id`; log không chứa API key,
filesystem path hoặc toàn bộ nội dung tài liệu.
# Phase 5 production contract

Phase 5 bổ sung API `/api/v2` cho upload bất đồng bộ, Celery/Redis job, polling/retry/cancel, key rotation, rate limit, circuit breaker, versioned FAISS index, health/metrics và Docker topology API–worker–Redis. Toàn bộ `/api/v1` vẫn được giữ tương thích.

Khi chạy trực tiếp development, `INDEX_LOCK_MODE=auto` cho phép upload đồng bộ v1 fallback sang process-local lock nếu Redis tắt. API v2, Celery và production vẫn bắt buộc Redis; Docker luôn đặt `INDEX_LOCK_MODE=redis`.

Trên Windows, Celery bắt buộc dùng pool `solo`; pool mặc định `prefork/spawn` có thể làm
`billiard` mất process handle (`WinError 5/6`) và khiến tài liệu kẹt ở `PENDING`.
Chạy worker bằng script đã kiểm tra Redis và khóa đúng topology:

```powershell
.\scripts\run_worker.ps1
```

Không bỏ `--pool=solo` khi chạy thủ công. Celery beat chỉ phục hồi/reconcile job,
không thay thế worker xử lý tài liệu.

API mặc định preload embedding ONNX int8 trước khi readiness chuyển `UP`; request tìm
kiếm đầu tiên vì vậy không còn chịu chi phí tải model. Chuẩn bị model local một lần:

```powershell
python scripts/prepare_onnx_embedding.py `
  --model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 `
  --output data/models/embedding-onnx
```

Script chỉ chấp nhận model khi cosine drift không vượt `0.01`. Nếu artifact ONNX chưa
có, runtime ghi `ONNX_MODEL_NOT_PREPARED` và fallback an toàn sang Torch. Celery worker
vẫn giải phóng embedding sau `WORKER_MODEL_IDLE_SECONDS` không có job. BM25 được cache
theo index fingerprint, FAISS chỉ lấy candidate budget và reranker bỏ qua tập ứng viên
quá nhỏ.

- Contract Spring Boot: [docs/spring-boot-integration.md](docs/spring-boot-integration.md)
- OpenAPI committed: [docs/openapi.json](docs/openapi.json)
- Hướng dẫn test chi tiết: [README-TESTING.md](README-TESTING.md)
