# Giai đoạn 6 — Pub/Sub, Cloud Tasks và Cloud Scheduler

## Kết quả triển khai

Giai đoạn 6 thay broker Celery/Redis và Celery Beat trong production:

1. RAG API ghi job `PENDING` vào Neon rồi phát `INDEXING_REQUESTED` lên Pub/Sub.
2. Pub/Sub push sự kiện có OIDC vào endpoint nội bộ của RAG.
3. Endpoint tạo Cloud Task HTTP có tên idempotent.
4. Cloud Task gọi RAG để parse, chunk, embedding và commit index.
5. Cloud Scheduler gọi reconcile mỗi phút để phục hồi job stale hoặc sự kiện bị mất.

Celery vẫn tồn tại cho local development với `JOB_DISPATCH_BACKEND=celery`.
Redis vẫn bắt buộc cho distributed lock và rate limit; việc chuyển Redis cache sang
Upstash thuộc giai đoạn sau. Không cần migration Alembic mới.

## Thành phần được thêm

- `app/services/gcp_job_transport.py`: publisher Pub/Sub, Cloud Tasks enqueuer,
  kiểm tra Google OIDC và decoder event.
- `app/api/routes/cloud_jobs.py`: ba endpoint nội bộ cho Pub/Sub, Cloud Tasks và
  Cloud Scheduler.
- `deploy/deploy-stage6.ps1`: tạo resource, IAM và deploy revision idempotent.
- Health readiness dùng `pubsub`, `cloudTasks`, `cloudScheduler` thay
  `celeryWorker` khi backend là `gcp`.

Endpoint nội bộ không dùng internal key của Spring. Chúng bắt buộc Google ID
token đúng audience và đúng service account; Cloud Tasks còn phải có đúng header
queue. Không đưa endpoint này vào frontend.

## 1. Biến môi trường mới

```text
JOB_DISPATCH_BACKEND=gcp
GCP_PROJECT_ID=bkquiz-stg-235740
GCP_REGION=asia-southeast1
PUBSUB_INDEXING_TOPIC=bkquiz-rag-indexing
CLOUD_TASKS_QUEUE=bkquiz-rag-indexing
CLOUD_TASKS_WORKER_URL=https://<RAG_CLOUD_RUN_URL>
CLOUD_TASKS_OIDC_AUDIENCE=https://<RAG_CLOUD_RUN_URL>
CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL=bkquiz-rag-events@bkquiz-stg-235740.iam.gserviceaccount.com
CLOUD_TASKS_DISPATCH_DEADLINE_SECONDS=900
```

Không thêm secret mới. Runtime tiếp tục dùng ADC của service account Cloud Run.
Giữ `REDIS_URL` vì Redis còn phục vụ lock/rate-limit.

## 2. Build image Stage 6

```powershell
cd D:\BKQuiz\rag-service

$PROJECT_ID = 'bkquiz-stg-235740'
$REGION = 'asia-southeast1'
$REPOSITORY = 'bkquiz'
$TAG = "stage6-$(Get-Date -Format yyyyMMdd-HHmmss)"
$IMAGE = "${REGION}-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/bkquiz-rag:$TAG"

gcloud config set project $PROJECT_ID
gcloud builds submit D:\BKQuiz\rag-service --tag $IMAGE
```

Không dùng lại tag `stage5`; tag riêng giúp rollback chính xác.

## 3. Kiểm tra trước deploy

Script dùng ASCII để chạy được trên Windows PowerShell 5.1 và PowerShell 7:

```powershell
cd D:\BKQuiz

.\rag-service\deploy\deploy-stage6.ps1 `
  -Image $IMAGE `
  -ValidateOnly

.\rag-service\deploy\deploy-stage6.ps1 `
  -Image $IMAGE `
  -WhatIf
```

`-ValidateOnly` chỉ xác nhận image và service hiện có. `-WhatIf` không thay đổi
Google Cloud.

## 4. Deploy hạ tầng và revision

```powershell
.\rag-service\deploy\deploy-stage6.ps1 -Image $IMAGE
```

Script thực hiện:

- bật Pub/Sub, Cloud Tasks, Cloud Scheduler và IAM Credentials API;
- tạo service account `bkquiz-rag-events` nếu chưa có;
- tự đọc runtime service account đang gắn với `bkquiz-rag-api`, không giả định tên;
- cấp `pubsub.publisher` và `cloudtasks.enqueuer` cho `bkquiz-rag`;
- cấp quyền tạo OIDC token đúng service account;
- tạo topic, push subscription và queue;
- queue chạy tối đa một task đồng thời để phù hợp máy 2 GiB;
- deploy image mới với các biến Stage 6;
- tạo Scheduler chạy reconcile mỗi phút.

Service account sự kiện chưa tồn tại là trạng thái bình thường ở lần chạy đầu;
script sẽ tự tạo. Không chạy riêng lệnh `iam service-accounts describe` với
`$ErrorActionPreference=Stop`, vì Windows PowerShell có thể biến kết quả
`NOT_FOUND` dự kiến thành lỗi dừng script.

Script không xóa Celery worker pool. Điều này cho phép smoke test trước khi cắt
broker cũ. API mới chỉ dispatch qua GCP sau khi `JOB_DISPATCH_BACKEND=gcp`.

Nếu project hoặc service account khác mặc định:

```powershell
.\rag-service\deploy\deploy-stage6.ps1 `
  -ProjectId '<PROJECT_ID>' `
  -Region '<REGION>' `
  -RuntimeServiceAccount '<RAG_RUNTIME_SA>' `
  -Image $IMAGE
```

Thông thường không cần truyền `-RuntimeServiceAccount`; chỉ override khi muốn
dùng account khác account hiện đang gắn với Cloud Run service.

## 5. Kiểm tra resource

```powershell
$RAG_URL = gcloud run services describe bkquiz-rag-api `
  --region=$REGION --format='value(status.url)'

Invoke-RestMethod "$RAG_URL/health/live"
Invoke-RestMethod "$RAG_URL/health/startup"
Invoke-RestMethod "$RAG_URL/health/ready"

gcloud pubsub topics describe bkquiz-rag-indexing
gcloud pubsub subscriptions describe bkquiz-rag-indexing-push
gcloud tasks queues describe bkquiz-rag-indexing --location=$REGION
gcloud scheduler jobs describe bkquiz-rag-reconcile --location=$REGION
```

Readiness phải có:

```json
{
  "redis": "UP",
  "pubsub": "UP",
  "cloudTasks": "UP",
  "cloudScheduler": "UP"
}
```

Không còn check `celeryWorker` khi Stage 6 được bật.

## 6. Smoke test trước khi tắt Celery

1. Upload một TXT nhỏ từ frontend.
2. Xác nhận job đi `PENDING → RUNNING → SUCCEEDED`.
3. Kiểm tra Cloud Tasks:

```powershell
gcloud tasks list --queue=bkquiz-rag-indexing --location=$REGION
gcloud logging read `
  'resource.type="cloud_run_revision" AND resource.labels.service_name="bkquiz-rag-api"' `
  --limit=100 --freshness=30m
```

4. Chạy Scheduler thủ công rồi kiểm tra không tạo xử lý trùng:

```powershell
gcloud scheduler jobs run bkquiz-rag-reconcile --location=$REGION
```

5. Reindex một tài liệu và xác nhận R2/Qdrant/Neon cập nhật bình thường.

Pub/Sub và Cloud Tasks đều at-least-once. Việc claim job có điều kiện trong Neon
đảm bảo delivery trùng không xử lý cùng job hai lần.

## 7. Tắt Celery worker pool sau smoke test

Chỉ chạy sau khi upload và reindex qua Stage 6 thành công:

```powershell
gcloud run worker-pools update bkquiz-rag-worker `
  --region=$REGION --instances=0

gcloud run worker-pools update bkquiz-rag-beat `
  --region=$REGION --instances=0
```

Hoặc chạy lại script với `-DisableCeleryPools` sau khi đã xác minh:

```powershell
.\rag-service\deploy\deploy-stage6.ps1 `
  -Image $IMAGE `
  -DisableCeleryPools
```

## 8. Chạy local

Local Docker không đổi:

```text
JOB_DISPATCH_BACKEND=celery
REDIS_URL=redis://redis:6379/0
```

Chạy API, Celery worker và beat như Giai đoạn 5. Không đặt backend `gcp` local
trừ khi đã chạy ADC và cấu hình public callback URL hợp lệ.

## 9. Test mã nguồn

```powershell
cd D:\BKQuiz\rag-service
Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue

.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pip check
```

## 10. Rollback

1. Chuyển dispatcher về Celery:

```powershell
gcloud run services update bkquiz-rag-api `
  --region=$REGION `
  --update-env-vars=JOB_DISPATCH_BACKEND=celery
```

2. Khởi động lại worker và beat:

```powershell
gcloud run worker-pools update bkquiz-rag-worker --region=$REGION --instances=1
gcloud run worker-pools update bkquiz-rag-beat --region=$REGION --instances=1
```

3. Pause Scheduler và Pub/Sub subscription để không phát delivery song song:

```powershell
gcloud scheduler jobs pause bkquiz-rag-reconcile --location=$REGION
gcloud pubsub subscriptions detach bkquiz-rag-indexing-push
```

Không xóa job Neon, object R2 hoặc vector Qdrant. Reconcile Celery sẽ tiếp tục các
job `PENDING` còn lại.

## Giới hạn còn lại

- Redis lock/rate-limit được chuyển sang Upstash ở Giai đoạn 7.
- Spring background worker vẫn là cơ chế riêng, không thuộc worker indexing RAG.
- STOMP chưa chuyển Ably.
- RAG service vẫn public ở lớp Cloud Run để Spring gọi bằng shared internal key;
  endpoint Stage 6 tự kiểm tra Google OIDC riêng.

Tham khảo: [Cloud Tasks HTTP target](https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks),
[Cloud Scheduler HTTP target](https://docs.cloud.google.com/scheduler/docs/creating).
