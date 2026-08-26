# Hướng dẫn kiểm thử BKQuiz RAG Phase 5

Tài liệu này áp dụng cho Windows PowerShell, Python 3.11 và mã nguồn tại `D:\BKQuiz\rag-service`. Không commit file `.env`, API key hoặc dữ liệu trong `data/`.

## 1. Chuẩn bị môi trường

```powershell
cd D:\BKQuiz\rag-service
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Cập nhật tối thiểu trong `.env`:

```dotenv
GEMINI_API_KEY=<key thật hoặc bỏ trống nếu chỉ test indexing/search>
GEMINI_MODEL=<model khả dụng của project>
SPRING_BOOT_INTERNAL_API_KEY=<secret dài và ngẫu nhiên>
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=sqlite:///data/rag.db
```

Redis 7 phải chạy để dùng API v2, Celery worker, distributed rate limit và mọi môi trường production. Riêng upload đồng bộ `/api/v1/user-documents` trong development có thể fallback sang local process lock khi `INDEX_LOCK_MODE=auto`; readiness vẫn báo Redis `DOWN`. Nếu Docker Desktop hoạt động:

```powershell
docker compose up -d redis
docker compose ps
```

## 2. Migration

Chạy trong `rag-service`:

```powershell
alembic upgrade head
alembic current
```

Kết quả cuối phải là `0003_performance_indexes (head)`. Lệnh cũng chạy độc lập từ monorepo root:

```powershell
cd D:\BKQuiz
.\rag-service\.venv\Scripts\alembic.exe -c rag-service\alembic.ini upgrade head
```

Migration tạo `documents`, `indexing_jobs`, `audit_events` và partial index cho job
pending/running. SQLite bật foreign key, WAL, `synchronous=NORMAL`, cache 64 MB và
`wal_autocheckpoint`.

Chuẩn bị embedding ONNX int8 trước khi chạy API:

```powershell
python scripts/prepare_onnx_embedding.py `
  --model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 `
  --output data/models/embedding-onnx
```

Expected: exit code `0`, `Max cosine drift` không vượt `0.01`.

## 3. Chạy local

Mở ba PowerShell tại `D:\BKQuiz\rag-service`.

API:

```powershell
.\scripts\run_local.ps1 -Service api
```

Worker Windows dùng pool `solo`:

```powershell
.\scripts\run_local.ps1 -Service worker
```

Beat phát hiện job stale:

```powershell
.\scripts\run_local.ps1 -Service beat
```

Trước khi test Gemini, chạy `.\.venv\Scripts\python.exe .\test_gemini_direct.py`.
Nếu nhận `GEMINI_CONFIG_CONFLICT`, xóa key cũ khỏi PowerShell bằng
`Remove-Item Env:GEMINI_API_KEY -ErrorAction Ignore` hoặc luôn dùng launcher.

## 4. Health và metrics

```powershell
curl.exe http://127.0.0.1:8000/health/live
curl.exe http://127.0.0.1:8000/health/ready
curl.exe http://127.0.0.1:8000/metrics
curl.exe http://127.0.0.1:8000/api/v2/capabilities `
  -H "X-Internal-API-Key: $InternalKey"
curl.exe http://127.0.0.1:9101/metrics
```

- Liveness: `200 {"status":"UP"}`.
- Readiness: `200` khi SQLite, Redis, storage/disk, embedding và cấu hình Gemini đều sẵn sàng; `503` kèm từng check khi thiếu dependency.
- Development với `INDEX_LOCK_MODE=auto`: upload v1 vẫn hoạt động khi Redis tắt, nhưng chỉ an toàn với một API process.
- API metrics chứa `rag_http_requests_total`; worker metrics dùng cổng 9101.

## 5. Smoke API v2

Chuẩn bị một file TXT thật rồi đặt biến:

```powershell
$base = 'http://127.0.0.1:8000/api/v2'
$key = '<SPRING_BOOT_INTERNAL_API_KEY trong .env>'
$user = '00000000-0000-0000-0000-000000000001'
$headers = @('X-Internal-API-Key: ' + $key, 'X-User-Id: ' + $user)
```

Upload bất đồng bộ:

```powershell
$upload = curl.exe -s -X POST "$base/user-documents" `
  -H $headers[0] -H $headers[1] -H 'Idempotency-Key: manual-upload-1' `
  -F 'file=@D:\path\to\document.txt;type=text/plain' | ConvertFrom-Json
$upload
```

Expected: HTTP `202`, `documentStatus=PROCESSING`, `jobStatus=PENDING`, có `documentId` và `jobId`. Gửi lại cùng idempotency key phải trả đúng cặp ID cũ.

Polling:

```powershell
curl.exe -s "$base/indexing-jobs/$($upload.jobId)" -H $headers[0] -H $headers[1]
```

Expected cuối: `status=SUCCEEDED`, `progress=100`, `step=SUCCEEDED`. Các bước trung gian lần lượt 10/30/50/70/90 phần trăm.

Hủy và retry (dùng với một job chưa xong hoặc đã thất bại):

```powershell
curl.exe -X POST "$base/indexing-jobs/$($upload.jobId)/cancel" -H $headers[0] -H $headers[1]
curl.exe -X POST "$base/indexing-jobs/$($upload.jobId)/retry" -H $headers[0] -H $headers[1]
```

Search và ask:

```powershell
$requestHeaders = @{
  'X-Internal-API-Key' = $key
  'X-User-Id' = $user
}
$searchBody = @{
  question = 'Nội dung chính của tài liệu là gì?'
  documentIds = @($upload.documentId)
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri "$base/user-rag/search" `
  -Headers $requestHeaders -ContentType 'application/json; charset=utf-8' `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($searchBody))

$askBody = @{
  question = 'Nội dung chính của tài liệu là gì?'
  documentIds = @($upload.documentId)
  includeSystemDocuments = $false
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri "$base/user-rag/ask" `
  -Headers $requestHeaders -ContentType 'application/json; charset=utf-8' `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($askBody))
```

Việc chuyển body thành byte UTF-8 là bắt buộc khi chạy bằng Windows PowerShell
5.1 và câu hỏi chứa tiếng Việt. Không nhập tay `$DocumentId`: luôn lấy từ
`$upload.id` (API v1) hoặc `$upload.documentId` (API v2).

Delete:

```powershell
curl.exe -i -X DELETE "$base/user-documents/$($upload.documentId)" -H $headers[0] -H $headers[1]
```

Expected `204`; search sau đó không được trả chunk của document đã xóa. Dùng `X-User-Id` khác để đọc job/document phải nhận 404.

## 6. Docker Compose

Standalone:

```powershell
docker compose up --build -d redis rag-api rag-worker rag-beat
docker compose ps
docker compose logs -f rag-api rag-worker
```

Root monorepo profile:

```powershell
cd D:\BKQuiz
docker compose --profile rag up --build -d rag-redis rag-api rag-worker rag-beat
```

Fake-Gemini integration không cần key thật:

```powershell
cd D:\BKQuiz\rag-service
docker compose -f docker-compose.yml -f docker-compose.test.yml up `
  --build --abort-on-container-exit --exit-code-from integration-test integration-test
```

Expected: container `integration-test` in `Phase 5 Docker integration passed`. Test thực hiện upload User A → poll → ask/citation → chặn User B → delete → search rỗng.

Kiểm tra persistence: upload thành công, ghi lại `documentId`, chạy `docker compose restart rag-api rag-worker`, sau đó GET document/search vẫn hoạt động vì SQLite, uploads, indexes và model cache dùng volume `rag-data`.

## 7. Unit, contract, lint và security

Trong `rag-service`:

```powershell
python -m pytest -q
ruff check app tests scripts integration
mypy
python -m pip check
pip-audit -r requirements.txt
python -m compileall -q app migrations scripts
python scripts\export_openapi.py
git diff --exit-code -- docs\openapi.json
```

Chạy test từ monorepo root:

```powershell
cd D:\BKQuiz
.\rag-service\.venv\Scripts\python.exe -m pytest -q rag-service\tests
```

Kết quả đã xác minh trên máy phát triển ngày 19/07/2026: 68 test xanh; Ruff, mypy (13 module trọng yếu), `pip check`, `pip-audit`, compile, OpenAPI export và Uvicorn liveness smoke thành công. Khi Redis tắt, upload thật `D:\docs\rag-test.txt` và `D:\docs\itss.pdf` đều trả `READY`, search và ask có citation. `docker compose config` của standalone, test override và root profile đều hợp lệ. Docker runtime chưa chạy trên máy này do Docker Desktop daemon đang tắt.

## 8. Evaluation và index recovery

```powershell
python -m app.cli.evaluate evaluation\datasets\my-dataset.json `
  --user-id $user --k 5 --skip-generation `
  --output evaluation\reports\latest.json

python scripts\manage_indexes.py verify
python scripts\manage_indexes.py rebuild-user --user-id $user
python scripts\manage_indexes.py cleanup --keep 2
python scripts\manage_indexes.py cleanup-orphans --retention-hours 24
```

Evaluation trả Recall@5, Hit Rate@5, MRR và latency cho baseline/hybrid. Bỏ `--skip-generation` để thêm citation/refusal accuracy, Gemini error rate và cost estimate khi `EVALUATION_PRICE_PER_MILLION_TOKENS` được cấu hình.

## 9. Lỗi thường gặp

| Hiện tượng/code | Nguyên nhân và cách xử lý |
|---|---|
| `DATABASE_MIGRATION_REQUIRED` | Chạy `alembic upgrade head`; xác nhận URL SQLite trỏ đúng shared volume. |
| `JOB_QUEUE_UNAVAILABLE` | Redis/Celery broker tắt; bật Redis rồi gửi lại upload với cùng idempotency key. |
| Job đứng `RUNNING` | Chạy beat; sau `INDEXING_JOB_STALE_SECONDS`, job được đưa về `PENDING`. |
| `RATE_LIMIT_STORE_UNAVAILABLE` | Redis không truy cập được; lỗi retryable, kiểm tra `REDIS_URL`. |
| `INDEX_LOCK_UNAVAILABLE` | Production không lấy được distributed index lock; khởi động/kiểm tra Redis rồi retry. |
| `INDEX_MUTATION_IN_PROGRESS` | User đang có một index mutation khác; retry theo `retryAfterSeconds`. |
| `RATE_LIMITED`/`GEMINI_RATE_LIMITED` | Chờ `retryAfterSeconds`; không tạo vòng retry tức thời. |
| `AI_SERVICE_TEMPORARILY_UNAVAILABLE` | Circuit breaker đang mở; chờ mặc định 60 giây. |
| `GEMINI_AUTH_ERROR` | Sai API key/quyền project; không retry tự động. |
| `INVALID_JSON_BODY` | Gửi JSON hợp lệ bằng UTF-8 và khai báo `application/json; charset=utf-8`. |
| `INVALID_DOCUMENT_SELECTION` | Document không READY, đã xóa hoặc không thuộc principal hiện tại. |
| `USER_INDEX_REBUILD_REQUIRED` | Chạy verify/rebuild; active snapshot cũ vẫn được giữ nếu lần build mới thất bại. |
| Readiness 503 nhưng liveness 200 | Xem trường `checks` để xác định SQLite, Redis, disk, embedding hoặc Gemini config. |

Contract đầy đủ cho Spring Boot nằm tại `docs/spring-boot-integration.md`; OpenAPI tại `docs/openapi.json`.

## Kiểm tra công thức toán

```powershell
alembic upgrade head
python -m pytest tests/test_math_markup.py tests/test_pdf_math_extractor.py tests/test_gemini_math_vision.py -q
```

Upload hoặc reindex PDF có tích phân/chỉ số rồi kiểm tra document trả `mathExtractionStatus`, `mathFormulaCount`, `mathWarningCount`; endpoint chunks trả cả `text`, `rawText` và `mathEnhanced`. `PARTIAL` là kết quả hợp lệ khi Vision không khả dụng, không phải lỗi indexing.

Reindex tài liệu `READY` mà không upload lại file:

```powershell
$reindex = Invoke-RestMethod -Method Post `
  -Uri "$base/user-documents/$($upload.documentId)/reindex" `
  -Headers @{ "X-Internal-API-Key"=$internalKey; "X-User-Id"=$userId }
$reindex | ConvertTo-Json
```

Kỳ vọng HTTP `202`, `documentId` không đổi và một `jobId` mới. Gọi lại khi job còn `PENDING/RUNNING` phải trả cùng `jobId`; upload file trùng qua endpoint upload vẫn trả `DUPLICATE_DOCUMENT`.
