# Giai đoạn 7 — chuyển Redis coordination sang Upstash

## Kết quả triển khai

Giai đoạn 7 chuyển Redis dùng chung của RAG sang Upstash Redis:

- distributed index lock dùng `CACHE_REDIS_URL`;
- rate-limit dùng cùng client và một Lua script atomic `INCR + EXPIRE`;
- connection pool được giới hạn bằng `CACHE_REDIS_MAX_CONNECTIONS`;
- production Upstash bắt buộc `rediss://`, credential và hostname
  `*.upstash.io`;
- health trả `cacheRedis` và `cacheRedisProvider`;
- `REDIS_URL` chỉ còn dành cho Celery local hoặc rollback.

Pub/Sub, Cloud Tasks và Cloud Scheduler của Giai đoạn 6 không thay đổi. Spring
Boot không dùng Redis nên không cần deploy lại backend. Không có migration
Alembic hoặc Flyway trong giai đoạn này.

## 1. Tạo database Upstash

Trong Upstash Console:

1. Chọn **Create Database**.
2. Đặt tên, ví dụ `bkquiz-rag-cache-stg`.
3. Chọn primary region gần Cloud Run `asia-southeast1` nhất.
4. Trong **Connect**, sao chép Redis TCP/TLS connection string.

Giá trị cần có dạng:

```text
rediss://default:<PASSWORD>@<ENDPOINT>.upstash.io:6379
```

Không dùng `UPSTASH_REDIS_REST_URL` hoặc REST token. `redis-py` trong RAG dùng
Redis protocol qua TLS.

## 2. Lưu URL vào Secret Manager

Không đặt URL chứa password trực tiếp trong câu lệnh deploy hoặc file YAML.

```powershell
$PROJECT_ID = 'bkquiz-stg-235740'
$SECRET_NAME = 'bkquiz-rag-cache-redis-url'
$UPSTASH_REDIS_URL = Read-Host 'Paste Upstash rediss URL'

gcloud secrets describe $SECRET_NAME --project=$PROJECT_ID 2>$null
if ($LASTEXITCODE -ne 0) {
  gcloud secrets create $SECRET_NAME `
    --project=$PROJECT_ID `
    --replication-policy=automatic
}

$TEMP_SECRET = [IO.Path]::GetTempFileName()
try {
  [IO.File]::WriteAllText(
    $TEMP_SECRET,
    $UPSTASH_REDIS_URL,
    [Text.UTF8Encoding]::new($false)
  )
  gcloud secrets versions add $SECRET_NAME `
    --project=$PROJECT_ID `
    --data-file=$TEMP_SECRET
}
finally {
  Remove-Item $TEMP_SECRET -Force -ErrorAction SilentlyContinue
  $UPSTASH_REDIS_URL = $null
}
```

Ghi lại version vừa tạo, ví dụ `1`. Không in hoặc đưa URL vào Git.

Cấp quyền đọc secret cho runtime service account thực tế:

```powershell
$RAG_SA = gcloud run services describe bkquiz-rag-api `
  --project=$PROJECT_ID `
  --region=asia-southeast1 `
  --format='value(spec.template.spec.serviceAccountName)'

gcloud secrets add-iam-policy-binding $SECRET_NAME `
  --project=$PROJECT_ID `
  --member="serviceAccount:$RAG_SA" `
  --role='roles/secretmanager.secretAccessor'
```

## 3. Build image Stage 7

```powershell
cd D:\BKQuiz\rag-service

$REGION = 'asia-southeast1'
$REPOSITORY = 'bkquiz'
$TAG = "stage7-$(Get-Date -Format yyyyMMdd-HHmmss)"
$IMAGE = "${REGION}-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/bkquiz-rag:$TAG"

gcloud builds submit D:\BKQuiz\rag-service --tag $IMAGE
```

## 4. Kiểm tra và deploy

```powershell
cd D:\BKQuiz

.\rag-service\deploy\deploy-stage7.ps1 `
  -Image $IMAGE `
  -CacheRedisSecret $SECRET_NAME `
  -CacheRedisSecretVersion 1 `
  -ValidateOnly

.\rag-service\deploy\deploy-stage7.ps1 `
  -Image $IMAGE `
  -CacheRedisSecret $SECRET_NAME `
  -CacheRedisSecretVersion 1 `
  -WhatIf

.\rag-service\deploy\deploy-stage7.ps1 `
  -Image $IMAGE `
  -CacheRedisSecret $SECRET_NAME `
  -CacheRedisSecretVersion 1
```

Thay `1` bằng version thực tế. Script đọc secret chỉ để xác nhận scheme/hostname,
không in password. Cloud Run nhận secret reference `CACHE_REDIS_URL`.

## 5. Smoke test

```powershell
$RAG_URL = gcloud run services describe bkquiz-rag-api `
  --region=$REGION --format='value(status.url)'

Invoke-RestMethod "$RAG_URL/health/live"
Invoke-RestMethod "$RAG_URL/health/startup"
Invoke-RestMethod "$RAG_URL/health/ready"
```

Readiness cần chứa:

```json
{
  "checks": {
    "cacheRedis": "UP"
  },
  "cacheRedisProvider": "upstash"
}
```

Tiếp tục kiểm tra:

1. Upload hai tài liệu bằng hai request gần nhau.
2. Reindex cùng một tài liệu đồng thời; chỉ một mutation được giữ lock.
3. Gửi upload vượt rate limit; API phải trả `429 RATE_LIMITED`.
4. Sinh Quiz/search sau khi Cloud Run scale-to-zero rồi khởi động lại.
5. Kiểm tra Upstash Metrics có command nhưng không có key chứa nội dung tài liệu.

## 6. Xóa binding Redis cũ

Giữ `REDIS_URL` trong lần deploy đầu để rollback nhanh. Sau ít nhất một vòng
smoke test ổn định, chạy:

```powershell
.\rag-service\deploy\deploy-stage7.ps1 `
  -Image $IMAGE `
  -CacheRedisSecret $SECRET_NAME `
  -CacheRedisSecretVersion 1 `
  -RemoveLegacyRedisBinding
```

Không dùng tùy chọn này nếu vẫn chạy Celery local/worker pool với cùng Cloud Run
environment.

## 7. Chạy local

Local Docker tiếp tục dùng Redis container:

```text
CACHE_REDIS_PROVIDER=redis
CACHE_REDIS_URL=redis://redis:6379/0
REDIS_URL=redis://redis:6379/0
JOB_DISPATCH_BACKEND=celery
```

Stage 7 không yêu cầu developer phải có tài khoản Upstash khi chạy local.

## 8. Rollback

Nếu Upstash lỗi, giữ nguyên image Stage 7 nhưng cho cache fallback về binding
`REDIS_URL` cũ:

```powershell
gcloud run services update bkquiz-rag-api `
  --region=$REGION `
  --remove-secrets=CACHE_REDIS_URL `
  --update-env-vars=CACHE_REDIS_PROVIDER=redis
```

Nếu đã xóa `REDIS_URL`, gắn lại secret Redis cũ trước khi rollback.

## 9. Test mã nguồn

```powershell
cd D:\BKQuiz\rag-service
Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue

.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pip check
```

Tham khảo: [Upstash Redis Getting Started](https://upstash.com/docs/redis/overall/getstarted),
[Upstash TLS connection](https://upstash.com/docs/redis/tutorials/python_realtime_chat).

## Giới hạn còn lại

- Cache truy vấn embedding/retrieval hiện vẫn là cache RAM theo instance; không
  chuyển nội dung tài liệu vào Upstash trong Stage 7.
- STOMP/WebSocket chưa chuyển sang Ably.
- Celery package vẫn nằm trong image để local development và rollback; production
  Stage 6/7 không dùng Celery broker.
