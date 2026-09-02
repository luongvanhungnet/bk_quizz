# Giai đoạn 5 — FastAPI/RAG trên Google Cloud Run

## Kết quả triển khai

Giai đoạn này đưa RAG API sang Cloud Run mà không thay Celery/Redis:

- container nghe `0.0.0.0:${PORT:-8080}` và dừng graceful khi nhận `SIGTERM`;
- `/health/startup` chỉ kiểm tra dependency bắt buộc của API: Neon, R2, Qdrant
  và embedding; nó không phụ thuộc heartbeat Celery;
- `/health/ready` vẫn là health nghiệp vụ đầy đủ, gồm Redis và Celery worker;
- metadata nằm trong Neon, vector trong Qdrant, file nguồn RAG trong R2;
- `/tmp/bkquiz-rag` chỉ dùng làm staging và được xóa sau parse;
- Ollama bị từ chối trong production;
- Alembic không chạy trong startup của API hoặc worker.

Celery worker và beat được triển khai tạm bằng Cloud Run worker pools. Đây là
cầu nối cho tới Giai đoạn 6 thay broker bằng Pub/Sub, Cloud Tasks và Scheduler.
Worker pools chạy liên tục, không autoscale và có chi phí cả khi không có job.

## 1. Điều kiện đầu vào

- Giai đoạn 3 đã chạy tới Alembic `0007_qdrant_snapshots` trên Neon.
- Giai đoạn 4 đã tạo Qdrant cluster và chuyển FAISS nếu có dữ liệu cũ.
- Có R2 bucket và token **Object Read & Write** giới hạn đúng bucket.
- Có Redis mà Cloud Run truy cập được. Chưa chuyển sang Upstash ở giai đoạn này.
- Google Cloud CLI hỗ trợ `gcloud run worker-pools`.

API và worker phải dùng cùng Neon, Qdrant, R2, Redis, internal key và image digest.

## 2. Cấu hình R2 cho file nguồn RAG

Có thể dùng chung bucket BKQuiz hiện tại vì object nằm dưới prefix
`rag-documents/`. Cấu hình:

```text
DOCUMENT_STORAGE_BACKEND=r2
DOCUMENT_STORAGE_ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
DOCUMENT_STORAGE_BUCKET=<TEN_BUCKET_R2_THUC_TE>
DOCUMENT_STORAGE_REGION=auto
DOCUMENT_STORAGE_PREFIX=rag-documents
DOCUMENT_STAGING_DIR=/tmp/bkquiz-rag
```

Các secret:

```text
DOCUMENT_STORAGE_ACCESS_KEY
DOCUMENT_STORAGE_SECRET_KEY
```

Không dùng public R2 URL. RAG truy cập bucket qua S3 API có xác thực.

### Chuyển file nguồn RAG cũ lên R2

Dừng RAG API/worker cũ, giữ thư mục `USER_UPLOAD_DIR`, sau đó chạy:

```powershell
cd D:\BKQuiz\rag-service

# Khai báo DATABASE_URL pooled Neon, Qdrant và DOCUMENT_STORAGE_* trước.
$env:APP_ENV = 'production'
$env:OLLAMA_ENABLED = 'false'
$env:USER_UPLOAD_DIR = 'D:\BKQuiz\rag-service\data\uploads\users'
$env:DOCUMENT_STAGING_DIR = "$env:TEMP\bkquiz-rag-migration"

python scripts\migrate_rag_files_to_r2.py --dry-run
python scripts\migrate_rag_files_to_r2.py
```

`missing` phải bằng `0`. Script mặc định giữ file local để rollback. Chỉ dùng
`--delete-local` sau khi đã smoke test reindex từ Cloud Run worker.

## 3. Tạo Artifact Registry và build image

```powershell
$PROJECT_ID = 'bkquiz-stg-235740'
$REGION = 'asia-southeast1'
$REPOSITORY = 'bkquiz'
$IMAGE = "${REGION}-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/bkquiz-rag:stage5"

gcloud config set project $PROJECT_ID
gcloud services enable run.googleapis.com artifactregistry.googleapis.com `
  cloudbuild.googleapis.com secretmanager.googleapis.com

gcloud artifacts repositories describe $REPOSITORY `
  --location=$REGION 2>$null
if ($LASTEXITCODE -ne 0) {
  gcloud artifacts repositories create $REPOSITORY `
    --repository-format=docker --location=$REGION
}

gcloud builds submit D:\BKQuiz\rag-service --tag $IMAGE
```

Image dùng cùng một Dockerfile cho API, worker và beat; worker pool ghi đè
command khi deploy.

Repository có `.gcloudignore` riêng để loại `.venv`, `data`, model cache, log và
credential khỏi source archive. Archive bình thường chỉ chứa source cần build;
nếu CLI báo hàng trăm MB, dừng lệnh và kiểm tra:

```powershell
cd D:\BKQuiz\rag-service
gcloud meta list-files-for-upload
```

Dockerfile không dùng `RUN --mount=type=cache`, vì `gcloud builds submit --tag`
có thể dùng legacy Docker builder không hỗ trợ cú pháp BuildKit này.

## 4. Chạy Alembic đúng một lần

Tạo secret `bkquiz-rag-database-url-direct` chứa Neon **direct** SQLAlchemy URL:

```text
postgresql+psycopg://USER:PASSWORD@HOST/DATABASE?sslmode=require
```

Tạo Cloud Run Job migration:

```powershell
gcloud run jobs deploy bkquiz-rag-migrate `
  --image=$IMAGE `
  --region=$REGION `
  --command=python `
  '--args=-m,alembic,upgrade,head' `
  --set-secrets=DATABASE_URL=bkquiz-rag-database-url-direct:1

gcloud run jobs execute bkquiz-rag-migrate --region=$REGION --wait
```

Trong PowerShell phải quote **toàn bộ** token `--args=...`. Nếu không,
PowerShell chuyển danh sách dấu phẩy thành một chuỗi có dấu cách và Python sẽ
cố import module tên `alembic upgrade head`. Có thể kiểm tra cấu hình đã lưu:

```powershell
$job = gcloud run jobs describe bkquiz-rag-migrate `
  --region=$REGION --format=json | ConvertFrom-Json
$job.spec.template.spec.template.spec.containers[0].args | ConvertTo-Json
```

Kết quả đúng là một mảng bốn phần tử: `-m`, `alembic`, `upgrade`, `head`.

Chỉ khi job thành công mới deploy revision mới. Runtime dùng Neon pooled URL;
không chạy `alembic upgrade` trong command của API/worker.

## 5. Chuẩn bị environment và Secret Manager

Sao chép file mẫu ra ngoài Git rồi thay URL/ID không nhạy cảm:

```powershell
Copy-Item D:\BKQuiz\rag-service\deploy\cloud-run.env.example.yaml `
  "$env:TEMP\bkquiz-rag-cloud-run.env.yaml"
notepad "$env:TEMP\bkquiz-rag-cloud-run.env.yaml"
```

Các secret cần tạo và cấp `Secret Manager Secret Accessor` cho service account:

| Environment | Secret đề xuất |
|---|---|
| `DATABASE_URL` | `bkquiz-rag-database-url-pooled` |
| `SPRING_BOOT_INTERNAL_API_KEY` | `bkquiz-rag-internal-key` |
| `GEMINI_API_KEY` | `bkquiz-gemini-api-key` |
| `QDRANT_API_KEY` | `bkquiz-qdrant-api-key` |
| `DOCUMENT_STORAGE_ACCESS_KEY` | `bkquiz-r2-access-key` |
| `DOCUMENT_STORAGE_SECRET_KEY` | `bkquiz-r2-secret-key` |
| `REDIS_URL` | `bkquiz-rag-redis-url` |

Ghim version cụ thể thay vì `latest` để rollback revision có tính xác định.

## 6. Deploy RAG API

```powershell
$SERVICE_ACCOUNT = "bkquiz-rag@$PROJECT_ID.iam.gserviceaccount.com"
$ENV_FILE = "$env:TEMP\bkquiz-rag-cloud-run.env.yaml"

gcloud run deploy bkquiz-rag-api `
  --image=$IMAGE `
  --region=$REGION `
  --service-account=$SERVICE_ACCOUNT `
  --env-vars-file=$ENV_FILE `
  --set-secrets="DATABASE_URL=bkquiz-rag-database-url-pooled:1,SPRING_BOOT_INTERNAL_API_KEY=bkquiz-rag-internal-key:1,GEMINI_API_KEY=bkquiz-gemini-api-key:1,QDRANT_API_KEY=bkquiz-qdrant-api-key:1,DOCUMENT_STORAGE_ACCESS_KEY=bkquiz-r2-access-key:1,DOCUMENT_STORAGE_SECRET_KEY=bkquiz-r2-secret-key:1,REDIS_URL=bkquiz-rag-redis-url:1" `
  --port=8080 `
  --cpu=2 `
  --memory=2Gi `
  --concurrency=4 `
  --timeout=900s `
  --min=0 `
  --max=3 `
  --cpu-boost `
  --startup-probe="httpGet.path=/health/startup,httpGet.port=8080,timeoutSeconds=5,periodSeconds=10,failureThreshold=24" `
  --liveness-probe="httpGet.path=/health/live,httpGet.port=8080,timeoutSeconds=5,periodSeconds=30,failureThreshold=3" `
  --allow-unauthenticated
```

`--allow-unauthenticated` hiện cần thiết vì Spring `RagClient` dùng shared
internal key và chưa gửi Google ID token. Mọi endpoint dữ liệu vẫn kiểm tra
`X-Internal-API-Key` và user context; chỉ health là public. Không đưa URL/key RAG
vào frontend. IAM service-to-service nên được bổ sung trước production public.

Lấy URL:

```powershell
$RAG_URL = gcloud run services describe bkquiz-rag-api `
  --region=$REGION --format='value(status.url)'
Invoke-RestMethod "$RAG_URL/health/live"
Invoke-RestMethod "$RAG_URL/health/startup"
```

## 7. Deploy Celery worker và beat tạm thời

Cloud Run worker pool không có public URL và không autoscale. Chạy đúng một
worker `solo` để bảo vệ topology hiện tại:

```powershell
$SECRETS = "DATABASE_URL=bkquiz-rag-database-url-pooled:1,SPRING_BOOT_INTERNAL_API_KEY=bkquiz-rag-internal-key:1,GEMINI_API_KEY=bkquiz-gemini-api-key:1,QDRANT_API_KEY=bkquiz-qdrant-api-key:1,DOCUMENT_STORAGE_ACCESS_KEY=bkquiz-r2-access-key:1,DOCUMENT_STORAGE_SECRET_KEY=bkquiz-r2-secret-key:1,REDIS_URL=bkquiz-rag-redis-url:1"

gcloud run worker-pools deploy bkquiz-rag-worker `
  --image=$IMAGE --region=$REGION --service-account=$SERVICE_ACCOUNT `
  --env-vars-file=$ENV_FILE --set-secrets=$SECRETS `
  --command=celery `
  '--args=-A,app.worker.celery_app:celery_app,worker,--pool=solo,--concurrency=1,--loglevel=INFO' `
  --cpu=2 --memory=2Gi --instances=1

gcloud run worker-pools deploy bkquiz-rag-beat `
  --image=$IMAGE --region=$REGION --service-account=$SERVICE_ACCOUNT `
  --env-vars-file=$ENV_FILE --set-secrets=$SECRETS `
  --command=celery `
  '--args=-A,app.worker.celery_app:celery_app,beat,--loglevel=INFO' `
  --cpu=1 --memory=1Gi --instances=1
```

Nếu region/project chưa hỗ trợ worker pools, giữ worker và beat trên máy/VM hiện
tại nhưng trỏ chúng vào cùng Neon, Qdrant, R2 và Redis. Không dùng Cloud Run Job
cho Celery worker chạy vô hạn.

## 8. Kết nối Spring Boot

Có thể cấu hình lại toàn bộ variables và secret references của Spring bằng
script idempotent sau. Biến trùng tên sẽ được thay thế và danh sách được kiểm
tra lại sau deploy:

```powershell
cd D:\BKQuiz
.\backend\deploy\configure-cloud-run.ps1 -WhatIf
.\backend\deploy\configure-cloud-run.ps1 -ValidateOnly
.\backend\deploy\configure-cloud-run.ps1
```

Script không chứa giá trị secret; nó chỉ tham chiếu các Secret Manager version
đã tạo. Có thể override project, region, frontend, RAG URL hoặc R2 bucket bằng
tham số của script.

```powershell
gcloud run services update bkquiz-api `
  --region=$REGION `
  --set-env-vars="RAG_ENABLED=true,RAG_SERVICE_URL=$RAG_URL,RAG_CONNECT_TIMEOUT=10s,RAG_READ_TIMEOUT=900s" `
  --update-secrets="RAG_INTERNAL_API_KEY=bkquiz-rag-internal-key:1"
```

Spring API và worker nghiệp vụ hiện tại phải truy cập được RAG URL. Không cấu
hình RAG URL trực tiếp trong Cloudflare Pages.

## 9. Smoke test

1. `/health/live` trả `200`.
2. `/health/startup` trả Neon/R2/Qdrant/embedding đều `UP`.
3. Sau khi worker pool có heartbeat, `/health/ready` trả `200`.
4. Upload TXT/PDF từ frontend; kiểm tra object xuất hiện dưới
   `rag-documents/` trong R2.
5. Job chuyển `PENDING → RUNNING → SUCCEEDED`.
6. Search, sinh Quiz và reindex tài liệu thành công.
7. Deploy revision API mới hoặc scale-to-zero rồi reindex lại để chứng minh file
   không phụ thuộc filesystem instance cũ.

## 10. Rollback

1. Không xóa object R2, Qdrant collection hoặc bảng Neon.
2. Chuyển traffic API về revision trước:

```powershell
gcloud run revisions list --service=bkquiz-rag-api --region=$REGION
gcloud run services update-traffic bkquiz-rag-api `
  --region=$REGION --to-revisions=<REVISION_CU>=100
```

3. Worker pool có thể scale về 0 trong lúc xử lý sự cố:

```powershell
gcloud run worker-pools update bkquiz-rag-worker --region=$REGION --instances=0
gcloud run worker-pools update bkquiz-rag-beat --region=$REGION --instances=0
```

4. Khởi động worker local Giai đoạn 4 với cùng Neon/Qdrant/R2/Redis nếu cần.

## Giới hạn còn lại

- Celery/Redis vẫn tồn tại; Giai đoạn 6 mới chuyển Pub/Sub, Cloud Tasks và
  Cloud Scheduler.
- Redis hiện vẫn gộp broker, cache, lock và rate limit.
- RAG Cloud Run tạm dùng shared internal key thay vì IAM ID token.
- System-document reindex từ thư mục local không dành cho runtime Cloud Run;
  user documents và Quiz RAG đã dùng Neon/Qdrant/R2.

Tham khảo: [Cloud Run container contract](https://docs.cloud.google.com/run/docs/container-contract),
[Cloud Run worker pools](https://docs.cloud.google.com/run/docs/deploy-worker-pools),
[Cloudflare R2 với boto3](https://developers.cloudflare.com/r2/examples/aws/boto3/).
