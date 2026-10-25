# Cách chạy dự án BKQuiz

Tài liệu này mô tả ba cách chạy BKQuiz bằng PowerShell:

1. chạy từng thành phần để phát triển và debug;
2. chạy toàn bộ môi trường local bằng một lệnh Docker Compose;
3. phát hành backend/RAG lên Google Cloud Run và frontend lên Cloudflare Pages.

Không ghi API key, mật khẩu, token hoặc URL chứa credential trực tiếp vào Git.
Các giá trị dạng `<...>` trong tài liệu phải được thay bằng cấu hình của môi
trường tương ứng.

## 0. Thành phần và cổng mặc định

| Thành phần | Công nghệ | Địa chỉ local |
|---|---|---|
| Frontend | React/Vite | `http://localhost:5173` |
| Spring API và Spring job worker | Spring Boot | `http://localhost:8080` |
| RAG API | FastAPI/Uvicorn | `http://localhost:8090` khi chạy trực tiếp; `8000` trong Compose |
| PostgreSQL | PostgreSQL/pgvector | `localhost:5432` |
| Redis local | Redis | `localhost:6379` |
| Qdrant local | Qdrant | `http://localhost:6333` |
| MinIO tùy chọn | S3-compatible storage | API `9000`, console `9001` |
| ClamAV | Antivirus | `3310` trong mạng Compose |

Yêu cầu công cụ:

- PowerShell 7 hoặc Windows PowerShell 5.1;
- Java 17;
- Node.js 24 và npm;
- Python 3.11;
- Docker Desktop có Docker Compose v2;
- Google Cloud CLI và GitHub CLI cho cách 3;
- Ollama chỉ là fallback local tùy chọn, không được bật trong production.

## 1. Cách 1 — chạy từng thành phần trên PowerShell

Cách này phù hợp nhất khi debug vì mỗi service có terminal và log riêng.

### 1.1. Chuẩn bị lần đầu

Từ thư mục dự án:

```powershell
Set-Location D:\BKQuiz

Copy-Item .env.example .env -ErrorAction SilentlyContinue
Copy-Item backend\.env.example backend\.env.local -ErrorAction SilentlyContinue
Copy-Item rag-service\.env.example rag-service\.env -ErrorAction SilentlyContinue
Copy-Item frontend\.env.example frontend\.env.local -ErrorAction SilentlyContinue
```

Mở các file vừa tạo và thay secret mẫu. Hai biến sau phải có **cùng giá trị**:

```text
backend/.env.local: RAG_INTERNAL_API_KEY
rag-service/.env:  SPRING_BOOT_INTERNAL_API_KEY
```

Cấu hình local quan trọng:

```text
backend/.env.local:
  DATABASE_URL=jdbc:postgresql://localhost:5432/bkquiz
  RAG_SERVICE_URL=http://127.0.0.1:8090
  FRONTEND_ORIGINS=http://localhost:5173
  COOKIE_SECURE=false

rag-service/.env:
  APP_ENV=development
  APP_PORT=8090
  JOB_DISPATCH_BACKEND=celery
  DATABASE_URL=sqlite:///data/rag.db
  REDIS_URL=redis://127.0.0.1:6379/0
  VECTOR_STORE_BACKEND=qdrant
  QDRANT_URL=http://127.0.0.1:6333
  DOCUMENT_STORAGE_BACKEND=local
```

Nếu dùng PostgreSQL local từ Compose, tài khoản Flyway có thể tạm dùng cùng
tài khoản owner local. Không áp dụng cách này cho Neon production.

Tạo Python virtual environment và cài dependency:

```powershell
Set-Location D:\BKQuiz\rag-service
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Cài frontend:

```powershell
Set-Location D:\BKQuiz\frontend
npm ci
```

### 1.2. Terminal 1 — dịch vụ hạ tầng local

```powershell
Set-Location D:\BKQuiz
docker compose --profile rag --profile s3 up -d `
  postgres minio minio-init clamav rag-redis rag-qdrant
```

Kiểm tra:

```powershell
docker compose ps
Invoke-RestMethod http://localhost:6333/healthz
```

### 1.3. Terminal 2 — RAG API

```powershell
Set-Location D:\BKQuiz\rag-service
.\scripts\run_local.ps1 -Service api
```

Kiểm tra:

```powershell
Invoke-RestMethod http://localhost:8090/health/live
Invoke-RestMethod http://localhost:8090/health/ready
```

`/health/ready` có thể báo degraded cho tới khi RAG worker chạy.

### 1.4. Terminal 3 — RAG Celery worker

Local development mặc định vẫn dùng Celery/Redis:

```powershell
Set-Location D:\BKQuiz\rag-service
.\scripts\run_local.ps1 -Service worker
```

### 1.5. Terminal 4 — RAG Celery beat

```powershell
Set-Location D:\BKQuiz\rag-service
.\scripts\run_local.ps1 -Service beat
```

Không chạy worker/beat Celery nếu đã đổi `JOB_DISPATCH_BACKEND=gcp`; chế độ đó
dành cho Pub/Sub, Cloud Tasks và Cloud Scheduler trên Google Cloud.

### 1.6. Terminal 5 — Spring Boot

```powershell
Set-Location D:\BKQuiz\backend
. .\load-local-env.ps1
.\mvnw.cmd spring-boot:run
```

Đặt `WORKER_ENABLED=true` nếu muốn process này xử lý email, generation job và
các job Spring. Khi bật worker, phải cấu hình Resend hợp lệ. Với API-only có thể
đặt `WORKER_ENABLED=false`.

Kiểm tra:

```powershell
Invoke-RestMethod http://localhost:8080/actuator/health/liveness
Invoke-RestMethod http://localhost:8080/actuator/health/readiness
```

### 1.7. Terminal 6 — frontend

```powershell
Set-Location D:\BKQuiz\frontend
npm run dev
```

Mở `http://localhost:5173`. Frontend gọi `/api` và Vite proxy request sang
`http://localhost:8080`; cookie local yêu cầu `COOKIE_SECURE=false`.

### 1.8. Ollama local tùy chọn

Chỉ chạy bước này khi muốn thử fallback Qwen local:

```powershell
ollama serve
ollama pull qwen3:1.7b
```

Sau đó đặt `OLLAMA_ENABLED=true` trong `rag-service/.env`. Production bắt buộc
`OLLAMA_ENABLED=false`.

### 1.9. Dừng hạ tầng

Nhấn `Ctrl+C` trong từng terminal ứng dụng, sau đó:

```powershell
Set-Location D:\BKQuiz
docker compose --profile rag --profile s3 down
```

Không thêm `-v` nếu muốn giữ database, MinIO, Redis và Qdrant local.

## 2. Cách 2 — chạy local bằng một lệnh Docker Compose

Repository có frontend container development, API, Spring worker, RAG API,
RAG worker/beat, PostgreSQL, Redis, Qdrant, MinIO và ClamAV. Chuẩn bị `.env`
ở thư mục gốc trước khi chạy:

```powershell
Set-Location D:\BKQuiz
Copy-Item .env.example .env -ErrorAction SilentlyContinue
notepad .env
```

Ít nhất hãy thay mật khẩu/secret mẫu, cấu hình Gemini nếu cần AI, và dùng cùng
`SPRING_BOOT_INTERNAL_API_KEY` cho Spring và RAG. Nếu muốn Spring lưu file vào
MinIO local, đặt `STORAGE_PROVIDER=s3`.

Khởi động toàn bộ bằng đúng một lệnh:

```powershell
docker compose --profile s3 --profile rag up --build
```

Sau khi health check hoàn tất:

- frontend: `http://localhost:5173`;
- Spring API: `http://localhost:8080`;
- Swagger: `http://localhost:8080/api/docs`;
- RAG API: `http://localhost:8000`;
- MinIO console: `http://localhost:9001`;
- Qdrant: `http://localhost:6333`.

Chạy nền nếu không muốn giữ terminal:

```powershell
docker compose --profile s3 --profile rag up --build -d
docker compose logs -f api worker rag-api rag-worker rag-beat frontend
```

Kiểm tra và dừng:

```powershell
docker compose ps
docker compose --profile s3 --profile rag down
```

Muốn reset toàn bộ volume local phải chủ động chạy lệnh dưới đây. Lệnh này xóa
dữ liệu local và không nên dùng nếu chưa backup:

```powershell
docker compose --profile s3 --profile rag down -v
```

## 3. Cách 3 — chạy production bằng Google Cloud Run từ PowerShell

Kiến trúc production hiện tại là:

- Spring Boot và FastAPI/RAG chạy trên Google Cloud Run;
- frontend tĩnh chạy trên Cloudflare Pages, không chạy trong Cloud Run;
- Neon, R2, Qdrant, Pub/Sub/Cloud Tasks/Scheduler, Upstash và Ably phải được
  cấu hình theo các giai đoạn 1–9;
- secret nằm trong Google Secret Manager;
- Flyway/Alembic chạy bằng Cloud Run Job đúng một lần trước revision mới;
- Ollama bị tắt.

### 3.1. Cách khuyến nghị — kích hoạt release pipeline từ PowerShell

Pipeline tại `.github/workflows/release.yml` thực hiện quality gate, build
image, migration, deploy RAG trước Spring, smoke test, rollback khi lỗi và deploy
Cloudflare Pages.

Chuẩn bị Workload Identity Federation và GitHub Environment theo
`docs/deploy/10-cicd-release.md`, sau đó chạy:

```powershell
Set-Location D:\BKQuiz

$GH_REPO = 'deepdev-hub/bk_quizz'
$BRANCH = 'main'
$DEPLOY_ENV = 'staging' # đổi thành production khi đã kiểm tra staging

gh auth status
gh workflow run release.yml `
  --repo $GH_REPO `
  --ref $BRANCH `
  -f environment=$DEPLOY_ENV `
  -f run_migrations=true `
  -f deploy_frontend=true

gh run watch --repo $GH_REPO
```

Đặt `run_migrations=false` chỉ khi chắc chắn release không có Flyway/Alembic
migration mới. Production chỉ phát hành từ `main` và nên có required reviewer.

### 3.2. Cập nhật Cloud Run trực tiếp bằng `gcloud` khi cần

Phần này dành cho operator đã hoàn tất cấu hình service account, IAM, env và
Secret Manager. Lệnh `services update --image` giữ nguyên các binding hiện tại;
không dùng một lệnh `deploy` thiếu env/secrets để tạo lại service production.

```powershell
Set-Location D:\BKQuiz

$PROJECT_ID = 'bkquiz-stg-235740'
$REGION = 'asia-southeast1'
$REPOSITORY = 'bkquiz'
$BACKEND_SERVICE = 'bkquiz-api'
$RAG_SERVICE = 'bkquiz-rag-api'
$TAG = "manual-$(Get-Date -Format yyyyMMdd-HHmmss)"
$REGISTRY = "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY"
$BACKEND_IMAGE = "$REGISTRY/backend:$TAG"
$BACKEND_MIGRATION_IMAGE = "$REGISTRY/backend-migrate:$TAG"
$RAG_IMAGE = "$REGISTRY/rag-service:$TAG"

gcloud auth login
gcloud config set project $PROJECT_ID
gcloud builds submit backend --tag $BACKEND_IMAGE --timeout=30m
gcloud builds submit backend `
  --config backend/cloudbuild.migrate.yaml `
  --substitutions "_IMAGE=$BACKEND_MIGRATION_IMAGE" `
  --timeout=20m
gcloud builds submit rag-service --tag $RAG_IMAGE --timeout=45m
```

Nếu release có migration, gắn **direct Neon endpoint** từ Secret Manager và
chạy đúng một lần. Thay các tên/version secret bằng tên thật:

```powershell
$BACKEND_SA = gcloud run services describe $BACKEND_SERVICE `
  --region=$REGION --format='value(spec.template.spec.serviceAccountName)'
$RAG_SA = gcloud run services describe $RAG_SERVICE `
  --region=$REGION --format='value(spec.template.spec.serviceAccountName)'

gcloud run jobs deploy bkquiz-db-migrate `
  --region=$REGION `
  --image=$BACKEND_MIGRATION_IMAGE `
  --service-account=$BACKEND_SA `
  --set-secrets='FLYWAY_URL=bkquiz-database-url-direct:1,FLYWAY_USER=bkquiz-database-username:1,FLYWAY_PASSWORD=bkquiz-database-password:1' `
  --max-retries=0 `
  --task-timeout=15m
gcloud run jobs execute bkquiz-db-migrate --region=$REGION --wait

gcloud run jobs deploy bkquiz-rag-migrate `
  --region=$REGION `
  --image=$RAG_IMAGE `
  --service-account=$RAG_SA `
  --command=python `
  '--args=-m,alembic,upgrade,head' `
  --set-secrets='DATABASE_URL=bkquiz-rag-database-url-direct:1' `
  --max-retries=0 `
  --task-timeout=15m
gcloud run jobs execute bkquiz-rag-migrate --region=$REGION --wait
```

Trong PowerShell phải quote toàn bộ token
`'--args=-m,alembic,upgrade,head'`; nếu không Python có thể nhận sai tên module.
Chỉ deploy revision sau khi cả hai migration job thành công:

```powershell
$RAG_PREVIOUS = gcloud run services describe $RAG_SERVICE `
  --region=$REGION --format='value(status.latestReadyRevisionName)'
$BACKEND_PREVIOUS = gcloud run services describe $BACKEND_SERVICE `
  --region=$REGION --format='value(status.latestReadyRevisionName)'

gcloud run services update $RAG_SERVICE `
  --region=$REGION --image=$RAG_IMAGE

gcloud run services update $BACKEND_SERVICE `
  --region=$REGION --image=$BACKEND_IMAGE
```

Build và deploy frontend lên Cloudflare Pages:

```powershell
Set-Location D:\BKQuiz\frontend
$env:VITE_API_BASE_URL = 'https://<BACKEND_CLOUD_RUN_HOST>/api'
$env:VITE_API_SAME_ORIGIN_PROXY = 'false'
$env:VITE_REALTIME_PROVIDER = 'ably'

npm ci
npm run lint
npm run typecheck
npm test
npm run build
npx wrangler login
npx wrangler pages deploy dist `
  --project-name='<TEN_CLOUDFLARE_PAGES_PROJECT>' `
  --branch=main
```

`VITE_API_BASE_URL` được nhúng lúc build và phải kết thúc bằng `/api`. Không để
giá trị `/api` đơn thuần trên Cloudflare Pages nếu không có reverse proxy thật,
vì POST sẽ đi vào static site và trả HTTP 405.

### 3.3. Smoke test production

```powershell
$BACKEND_URL = gcloud run services describe $BACKEND_SERVICE `
  --project=$PROJECT_ID --region=$REGION --format='value(status.url)'
$RAG_URL = gcloud run services describe $RAG_SERVICE `
  --project=$PROJECT_ID --region=$REGION --format='value(status.url)'

Invoke-RestMethod "$BACKEND_URL/actuator/health/liveness"
Invoke-RestMethod "$BACKEND_URL/actuator/health/readiness"

$RAG_TOKEN = gcloud auth print-identity-token --audiences=$RAG_URL
Invoke-RestMethod "$RAG_URL/health/live" `
  -Headers @{ Authorization = "Bearer $RAG_TOKEN" }
```

Sau đó kiểm tra trên UI: đăng nhập/refresh token, upload avatar lên R2, upload và
reindex tài liệu, tạo Quiz trống, sinh thêm câu AI và realtime lớp học qua Ably.

### 3.4. Rollback revision

Nếu deploy trực tiếp thất bại sau khi đã đổi traffic:

```powershell
gcloud run services update-traffic $BACKEND_SERVICE `
  --project=$PROJECT_ID --region=$REGION `
  --to-revisions="$BACKEND_PREVIOUS=100"

gcloud run services update-traffic $RAG_SERVICE `
  --project=$PROJECT_ID --region=$REGION `
  --to-revisions="$RAG_PREVIOUS=100"
```

Cloudflare Pages rollback trong dashboard hoặc deployment history. Database
migration là forward-only: không tự chạy `flyway undo` hoặc Alembic downgrade.

## 4. Quality gate trước khi chạy hoặc phát hành

```powershell
Set-Location D:\BKQuiz\backend
.\mvnw.cmd verify

Set-Location D:\BKQuiz\frontend
npm ci
npm run lint
npm run typecheck
npm test
$env:VITE_API_BASE_URL = 'https://api.example.com/api'
npm run build

Set-Location D:\BKQuiz\rag-service
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests scripts integration
.\.venv\Scripts\python.exe -m mypy app
.\.venv\Scripts\python.exe -m pip check
```

## 5. Tài liệu liên quan

- `docs/deploy/01-spring-cloud-run-neon.md`
- `docs/deploy/02-cloudflare-r2-storage.md`
- `docs/deploy/03-rag-neon-postgresql.md`
- `docs/deploy/04-qdrant-vector-store.md`
- `docs/deploy/05-rag-fastapi-cloud-run.md`
- `docs/deploy/06-pubsub-cloud-tasks-scheduler.md`
- `docs/deploy/07-upstash-redis.md`
- `docs/deploy/08-ably-realtime.md`
- `docs/deploy/09-production-hardening.md`
- `docs/deploy/10-cicd-release.md`
- `docs/deploy/resend-email.md`
