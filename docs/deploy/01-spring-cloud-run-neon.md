# Stage 1 - Spring Boot trên Cloud Run với Neon PostgreSQL

Ngày cập nhật: 2026-08-26  
Phạm vi: chỉ Spring Boot backend và PostgreSQL nghiệp vụ. Stage này **không** triển khai R2, Qdrant, Pub/Sub, Upstash, Ably hoặc RAG cloud migration.

## 1. Kết quả Stage 1

Backend hiện hỗ trợ:

- Lắng nghe cổng do Cloud Run cấp qua `PORT`, mặc định 8080.
- Profile `prod` yêu cầu database URL/username/password từ environment.
- Neon pooled JDBC URL có SSL qua query parameter `sslmode=require` hoặc `sslmode=verify-full`.
- Hikari pool production mặc định 4 connection và có thể đổi bằng `DATABASE_POOL_SIZE`.
- Flyway production mặc định tắt để nhiều Cloud Run instance không chạy migration đồng thời.
- Spring JobWorker production mặc định tắt và không tạo bean khi `WORKER_ENABLED=false`.
- Graceful shutdown với thời hạn mặc định 30 giây.
- Actuator liveness/readiness; readiness bao gồm trạng thái ứng dụng và kết nối database.
- Cookie secure vẫn cấu hình được; CSRF refresh cookie/XSRF giữ nguyên.
- CORS credentials chỉ nhận origin cụ thể; startup từ chối wildcard.
- Container tiếp tục chạy non-root và nhận `SIGTERM` từ Cloud Run.

## 2. Cấu hình production

Luôn đặt:

```text
SPRING_PROFILES_ACTIVE=prod
```

Các biến Stage 1:

| Biến | Bắt buộc | Production default | Ghi chú |
|---|---:|---:|---|
| `PORT` | Cloud Run cấp | `8080` | Không cần tự đặt trên Cloud Run |
| `DATABASE_URL` | Có | Không có | JDBC URL của Neon pooled endpoint |
| `DATABASE_USERNAME` | Có | Không có | Không hard-code hoặc bake vào image |
| `DATABASE_PASSWORD` | Có | Không có | Đưa qua Secret Manager |
| `DATABASE_POOL_SIZE` | Không | `4` | Nhân với max Cloud Run instances để tính connection budget |
| `FRONTEND_ORIGINS` | Có | Không có giá trị production an toàn | Danh sách origin cụ thể, phân tách dấu phẩy; không wildcard |
| `COOKIE_SECURE` | Không | `true` | Production validator từ chối `false` |
| `WORKER_ENABLED` | Không | `false` | API Cloud Run không chạy PostgreSQL polling worker |
| `FLYWAY_ENABLED` | Không | `false` | Giữ false trên mọi runtime replica |

Các biến bảo mật/ứng dụng vẫn cần cấu hình theo môi trường, đặc biệt `JWT_ACCESS_SECRET`. Không dùng giá trị mẫu, `.env` development hoặc secret được bake vào Docker image.

### Neon pooled runtime URL

`DATABASE_URL` phải là JDBC URL, không phải URI `postgresql://` thuần:

```text
jdbc:postgresql://<neon-pooled-host>/<database>?sslmode=require
```

Nếu môi trường có CA/hostname validation phù hợp, dùng `sslmode=verify-full`. Pooled endpoint thường có hostname chứa dấu hiệu `pooler`; lấy chính xác URL từ Neon dashboard và chỉ thêm prefix `jdbc:` nếu dashboard cung cấp URI PostgreSQL.

Không đưa username/password vào URL. Dùng riêng `DATABASE_USERNAME` và `DATABASE_PASSWORD`.

## 3. Flyway - chạy đúng một lần

### Hotfix schema V25

Revision backend từ ngày 2026-08-27 yêu cầu migration
`V25__align_cognitive_integer_columns.sql`. Migration này đổi các cột Cognitive
từ PostgreSQL `SMALLINT` sang `INTEGER` để khớp mapping Java và sửa lỗi Cloud Run
không khởi động với thông báo:

```text
Schema validation: wrong column type encountered in column [complexity_score]
```

Phải chạy Flyway bằng direct Neon endpoint trước khi deploy image chứa V25.
Không bật Flyway trên nhiều Cloud Run instance để tự sửa lỗi này.

### Nguyên tắc

1. Tạo Neon branch/snapshot trước migration để có điểm rollback database.
2. Dùng **direct Neon endpoint**, không dùng pooled runtime endpoint.
3. Chỉ một operator hoặc một CI release job được chạy migration.
4. Chờ migration thành công rồi mới deploy Cloud Run revision mới.
5. Mọi Cloud Run runtime revision giữ `FLYWAY_ENABLED=false`.

### Lệnh PowerShell

Từ thư mục `D:\BKQuiz`, đặt credential trong environment của terminal/CI secret store. Không ghi giá trị vào repo hoặc command history dùng chung:

```powershell
$env:FLYWAY_URL = 'jdbc:postgresql://<neon-direct-host>/<database>?sslmode=require'
$env:FLYWAY_USER = '<migration-user>'
$env:FLYWAY_PASSWORD = '<injected-by-secret-store>'

docker run --rm `
  -e FLYWAY_URL `
  -e FLYWAY_USER `
  -e FLYWAY_PASSWORD `
  -v "${PWD}/backend/src/main/resources/db/migration:/flyway/sql:ro" `
  flyway/flyway:12.4.0-alpine `
  -locations=filesystem:/flyway/sql `
  -validateMigrationNaming=true `
  -connectRetries=10 `
  migrate
```

Version `12.4.0` khớp Flyway dependency hiện tại của Spring Boot build. Kiểm tra sau migration:

```powershell
docker run --rm `
  -e FLYWAY_URL `
  -e FLYWAY_USER `
  -e FLYWAY_PASSWORD `
  -v "${PWD}/backend/src/main/resources/db/migration:/flyway/sql:ro" `
  flyway/flyway:12.4.0-alpine `
  -locations=filesystem:/flyway/sql `
  -validateMigrationNaming=true `
  info
```

Không chạy `migrate` từ startup của từng Cloud Run instance. Không bật `FLYWAY_ENABLED=true` trên Cloud Run service.

## 4. Build image

Dockerfile tương thích Cloud Run:

- Java 17 JRE runtime.
- Process Java là PID 1 qua exec-form `ENTRYPOINT`.
- Chạy bằng user non-root.
- Nhận `SIGTERM` và Spring graceful shutdown.
- Cổng thực tế do `server.port=${PORT:8080}` quyết định; `EXPOSE 8080` chỉ là metadata.
- Không bake profile hoặc secret để Docker Compose development không đổi hành vi.

Build local:

```powershell
Set-Location D:\BKQuiz\backend
docker build -t bkquiz-backend:stage1 .
```

Build lên Artifact Registry, ví dụ:

```powershell
$env:GCP_PROJECT = '<gcp-project>'
$env:GCP_REGION = '<region>'
$env:IMAGE = "$env:GCP_REGION-docker.pkg.dev/$env:GCP_PROJECT/bkquiz/backend:<revision>"

gcloud builds submit D:\BKQuiz\backend --tag $env:IMAGE --project $env:GCP_PROJECT
```

## 5. Deploy Cloud Run API

Secret nên được tạo trong Google Secret Manager và cấp quyền đọc cho service account riêng của backend. Ví dụ triển khai; thay tên secret/resource bằng giá trị của môi trường:

```powershell
gcloud run deploy bkquiz-api `
  --image $env:IMAGE `
  --region $env:GCP_REGION `
  --project $env:GCP_PROJECT `
  --service-account '<backend-service-account>' `
  --set-env-vars 'SPRING_PROFILES_ACTIVE=prod,WORKER_ENABLED=false,FLYWAY_ENABLED=false,DATABASE_POOL_SIZE=4,COOKIE_SECURE=true,FRONTEND_ORIGINS=https://<frontend-host>' `
  --set-secrets 'DATABASE_URL=neon-pooled-jdbc-url:latest,DATABASE_USERNAME=neon-runtime-user:latest,DATABASE_PASSWORD=neon-runtime-password:latest,JWT_ACCESS_SECRET=bkquiz-jwt-access-secret:latest' `
  --port 8080 `
  --timeout 300 `
  --concurrency 40 `
  --max-instances 4 `
  --allow-unauthenticated
```

Connection budget với ví dụ trên là tối đa khoảng `4 pool x 4 instances = 16` runtime connections, chưa tính migration/admin connections. Điều chỉnh theo quota Neon thực tế trước khi tăng `--max-instances`.

`--allow-unauthenticated` chỉ cho phép request đến service; authorization nghiệp vụ vẫn do Spring Security xử lý. Có thể đặt Cloudflare/proxy hoặc load balancer phía trước ở stage frontend sau.

## 6. Health và smoke test

Sau deploy:

```powershell
$env:SERVICE_URL = gcloud run services describe bkquiz-api `
  --region $env:GCP_REGION `
  --project $env:GCP_PROJECT `
  --format='value(status.url)'

curl.exe -i "$env:SERVICE_URL/actuator/health/liveness"
curl.exe -i "$env:SERVICE_URL/actuator/health/readiness"
curl.exe -i "$env:SERVICE_URL/api/health"
```

Kỳ vọng:

- Liveness trả HTTP 200 và `UP` khi process hoạt động.
- Readiness trả HTTP 200 và `UP` khi Neon kết nối được.
- `/api/health` báo `database=connected`.
- Log startup ghi document processor disabled; không có heartbeat/poll từ `JobWorker`.

Kiểm tra CORS bằng đúng origin production:

```powershell
curl.exe -i -X OPTIONS "$env:SERVICE_URL/api/auth/refresh-token" `
  -H 'Origin: https://<frontend-host>' `
  -H 'Access-Control-Request-Method: POST' `
  -H 'Access-Control-Request-Headers: Content-Type,X-XSRF-TOKEN'
```

Refresh cookie và XSRF behavior không đổi trong Stage 1. Trước khi chuyển frontend sang Cloudflare Pages vẫn phải chốt topology same-origin/cross-site như báo cáo Stage 0.

## 7. Filesystem trên Cloud Run

Profile production dùng `/tmp/bkquiz/...` cho local temp/storage fallback. `/tmp` là ephemeral và không được xem là persistent storage.

Vì R2 nằm ngoài Stage 1:

- Không coi upload source, classroom attachment hoặc avatar là durable trên Cloud Run.
- Không dựa vào file còn tồn tại sau restart/scale/redeploy.
- Không bật production traffic cho workflow upload cần độ bền cho tới Stage R2.
- Database và các API không dùng upload vẫn chạy stateless theo Stage 1.

## 8. Local Docker development

Hành vi local không đổi:

- Profile mặc định vẫn dùng pool 6.
- Flyway mặc định bật.
- `WORKER_ENABLED` mặc định true ngoài profile production.
- Root Docker Compose tiếp tục tách `api` với worker false và `worker` với worker true.
- Local storage vẫn dùng `./data` hoặc Docker volume như trước.

Kiểm tra:

```powershell
Set-Location D:\BKQuiz
docker compose config --quiet
docker compose up --build postgres api worker
```

## 9. Test Stage 1

```powershell
Set-Location D:\BKQuiz\backend
.\mvnw.cmd verify
```

Test mới kiểm tra:

- Không tạo `JobWorker` khi worker bị tắt.
- Profile production có default Cloud Run an toàn và nhận override environment.
- Neon JDBC URL giữ nguyên SSL mode.
- Actuator readiness `UP` khi PostgreSQL sẵn sàng.
- `/api/health` xác nhận database connected.

## 10. Rollback

### Application rollback

Liệt kê revision và đưa toàn bộ traffic về revision trước:

```powershell
gcloud run revisions list `
  --service bkquiz-api `
  --region $env:GCP_REGION `
  --project $env:GCP_PROJECT

gcloud run services update-traffic bkquiz-api `
  --region $env:GCP_REGION `
  --project $env:GCP_PROJECT `
  --to-revisions '<previous-revision>=100'
```

Giữ `FLYWAY_ENABLED=false` và `WORKER_ENABLED=false` trong rollback revision.

### Database rollback

- Flyway migrations của BKQuiz là forward migrations; không tự chạy SQL downgrade hoặc `flyway undo`.
- Nếu migration gây lỗi, ngừng rollout và đưa traffic về revision tương thích khi schema còn backward-compatible.
- Nếu cần khôi phục dữ liệu/schema, dùng Neon branch/snapshot/PITR đã tạo trước migration và đổi ba database secrets/runtime URL sang branch phục hồi.
- Xác minh readiness và smoke test trước khi chuyển lại traffic.

## 11. Blocker còn lại sau Stage 1

- Upload/avatar/classroom file chưa durable trên Cloud Run; chờ R2.
- RAG vẫn dùng SQLite, local upload và FAISS; chưa thể chạy stateless/multi-replica trên Cloud Run.
- Spring JobWorker vẫn là PostgreSQL polling scheduler. API đã tắt worker; cần một worker deployment có min instance hoặc stage Pub/Sub/Cloud Tasks trước khi xử lý nền trên cloud.
- Redis/Celery, STOMP và Ollama production chưa thay đổi trong Stage 1.
- Cookie/CSRF giữa Cloudflare Pages và Cloud Run cần quyết định domain/proxy trước frontend rollout.
- Chưa có IaC và automated release gate bảo đảm Flyway job hoàn tất trước Cloud Run deployment.
