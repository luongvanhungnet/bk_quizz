# BKQuiz - Kiểm kê hiện trạng trước khi di chuyển lên cloud

Ngày kiểm kê: 2026-08-26  
Phạm vi repository: `D:\BKQuiz`  
Trạng thái tài liệu: hiện trạng trước migration; **chưa thực hiện thay đổi kiến trúc cloud**.

## 1. Mục tiêu và nguyên tắc kiểm kê

Kiến trúc đích đang được chuẩn bị:

| Thành phần hiện tại | Đích dự kiến |
|---|---|
| React/Vite | Cloudflare Pages |
| Spring Boot | Google Cloud Run |
| PostgreSQL nghiệp vụ | Neon PostgreSQL |
| Upload local/S3-compatible | Cloudflare R2 |
| RAG SQLite | Neon PostgreSQL |
| FAISS trên filesystem | Qdrant |
| FastAPI/RAG | Google Cloud Run |
| Celery + Redis broker | Pub/Sub + Cloud Tasks + Cloud Scheduler |
| Redis lock/rate-limit/cache | Upstash Redis |
| Spring STOMP simple broker | Ably |
| Ollama local | Tắt trong production |

Tài liệu này chỉ mô tả implementation hiện tại, biến môi trường, rủi ro, phụ thuộc migration và cách kiểm tra. Không có secret nào được ghi lại. Các file `.env` thực tế không được đọc; chỉ các file cấu hình và `.env.example` được dùng để kiểm kê.

## 2. Tổng quan runtime hiện tại

BKQuiz đang gồm ba ứng dụng chính và hai nhóm worker:

1. `frontend`: React 18 + TypeScript + Vite, gọi Spring Boot qua `/api` và kết nối STOMP qua `/ws`.
2. `backend`: Spring Boot/Java 17, PostgreSQL là nguồn dữ liệu nghiệp vụ, Flyway quản lý schema, đồng thời chạy REST API, WebSocket/STOMP và các scheduled task.
3. `rag-service`: FastAPI/Python 3.11, SQLite lưu metadata RAG, FAISS + JSON lưu vector/chunk trên disk, Redis phục vụ Celery, distributed lock, heartbeat/dedupe và rate limit.
4. Spring `JobWorker`: poll bảng `jobs` trong PostgreSQL để xử lý email, upload/index, poll RAG và sinh Quiz.
5. Celery worker/beat: xử lý indexing bên RAG và phục hồi/reconcile job RAG.

Luồng upload hiện tại:

```text
Browser -> Spring Boot -> SourceObjectStorage (local hoặc S3-compatible)
                    -> PostgreSQL source/job
Spring JobWorker -> đọc lại file -> multipart HTTP -> FastAPI
FastAPI -> local USER_UPLOAD_DIR -> SQLite job/document -> Celery
Celery -> parser/embedding -> FAISS + JSON local -> SQLite READY
Spring JobWorker -> poll RAG -> đồng bộ chunk về PostgreSQL
```

Luồng sinh Quiz hiện tại:

```text
Browser -> Spring API -> PostgreSQL job
Spring JobWorker -> RAG NDJSON streaming
RAG -> retrieval local FAISS/BM25 -> Gemini API/OAuth -> Ollama fallback (nếu bật)
Spring -> checkpoint/event PostgreSQL -> commit toàn bộ Quiz
Browser -> poll job và job_events
```

## 3. Frontend React/Vite

### 3.1 Build directory, routing và API base URL

Implementation:

- Build dùng `vite build`; không override `build.outDir`, do đó output mặc định là `frontend/dist`.
- Router dùng `createBrowserRouter`, nên Cloudflare Pages cần SPA fallback để mọi route ứng dụng trả `index.html`.
- API base URL lấy từ `VITE_API_BASE_URL`; khi rỗng mặc định `/api`.
- Development proxy chuyển `/api` và `/ws` đến `VITE_DEV_API_TARGET`, mặc định `http://localhost:8080`; `/ws` bật proxy WebSocket.
- Một số stream API trong `bkquiz.ts` dùng `fetch` trực tiếp nhưng vẫn ghép cùng `VITE_API_BASE_URL` và gửi cookie.

File chính:

- `frontend/package.json`
- `frontend/vite.config.ts`
- `frontend/.env.example`
- `frontend/src/main.tsx`
- `frontend/src/app/routes.tsx`
- `frontend/src/api/runtime.ts`
- `frontend/src/api/client.ts`
- `frontend/src/api/bkquiz.ts`

Biến môi trường:

- `VITE_API_BASE_URL` - hiện mặc định `/api`.
- `VITE_DEV_API_TARGET` - chỉ dùng cho Vite dev proxy.

Rủi ro migration:

- Chưa có cấu hình Cloudflare Pages/Wrangler hoặc rule SPA fallback trong repository.
- Nếu Pages gọi trực tiếp domain Cloud Run, cookie refresh/CSRF sẽ trở thành cross-origin và có thể cross-site. Phương án ít rủi ro nhất cho Stage 1 là giữ `/api` cùng origin bằng Cloudflare Worker/route proxy; nếu dùng domain khác phải thiết kế lại `SameSite`, cookie domain và CORS.
- Biến `VITE_*` được đóng vào bundle tại build time; URL môi trường không thể đổi sau build nếu không có runtime config.
- Cần đảm bảo các endpoint NDJSON/stream không bị proxy buffer hoặc timeout ngoài ý muốn.

Lệnh kiểm tra:

```powershell
Set-Location D:\BKQuiz\frontend
npm ci
npm run lint
npm run typecheck
npm test -- --run
npm run build
Test-Path .\dist\index.html
```

### 3.2 Access token, refresh cookie và CSRF

Implementation frontend:

- Access token được giữ trong `accessTokenStore`, không lưu vào `localStorage`.
- Mọi request API gửi `credentials: "include"` và `Authorization: Bearer ...` khi có access token.
- Khi nhận `401`, client dùng một refresh request dùng chung rồi retry request ban đầu, tránh nhiều refresh song song.
- `AuthProvider` thử refresh khi ứng dụng khởi động để phục hồi phiên.
- Frontend đọc cookie `XSRF-TOKEN` và gửi header `X-XSRF-TOKEN` cho refresh/logout/logout-all.

Implementation backend:

- Refresh token là opaque token trong cookie `bkquiz_refresh`, `HttpOnly`, `Path=/api/auth`, `SameSite=Lax`; `Secure` lấy từ `COOKIE_SECURE` và profile production đặt true.
- Refresh session/hash được lưu trong PostgreSQL; cookie không phải JWT refresh tự chứa trạng thái.
- `XSRF-TOKEN` là cookie đọc được bởi JavaScript, `Path=/`, `SameSite=Lax`.
- Spring Security tắt CSRF framework và dùng `CookieCsrfFilter` riêng cho ba endpoint refresh/logout.
- Filter so khớp cookie/header theo constant-time và kiểm tra `Origin` nếu header này tồn tại.

File chính:

- `frontend/src/auth/accessToken.ts`
- `frontend/src/auth/api.ts`
- `frontend/src/auth/AuthProvider.tsx`
- `frontend/src/api/client.ts`
- `backend/src/main/java/com/genquiz/bk/auth/AuthController.java`
- `backend/src/main/java/com/genquiz/bk/auth/AccountTypeController.java`
- `backend/src/main/java/com/genquiz/bk/auth/AuthService.java`
- `backend/src/main/java/com/genquiz/bk/security/CookieCsrfFilter.java`
- `backend/src/main/java/com/genquiz/bk/security/JwtService.java`

Biến môi trường liên quan:

- `JWT_ACCESS_SECRET`, `JWT_ACCESS_TTL`
- `REFRESH_TOKEN_TTL`
- `COOKIE_SECURE`
- `FRONTEND_ORIGINS`
- `BCRYPT_STRENGTH`

Rủi ro migration:

- `SameSite=Lax` không bảo đảm gửi cookie trên request fetch cross-site Pages -> Cloud Run. Không được chỉ đổi CORS rồi kỳ vọng refresh hoạt động.
- Nếu chuyển sang `SameSite=None`, bắt buộc `Secure`, phải đánh giá CSRF và danh sách origin chính xác.
- Mô hình double-submit hiện yêu cầu frontend đọc `XSRF-TOKEN`; cookie này cần nằm trên domain mà JavaScript Pages đọc được. Reverse proxy cùng origin tránh thay đổi lớn nhất.
- Cloud Run phải nhận đúng `X-Forwarded-*`; backend đã bật forwarded headers nhưng cần smoke test cookie/redirect thực tế.

Lệnh kiểm tra:

```powershell
Set-Location D:\BKQuiz\frontend
npm test -- --run src/auth/api.test.ts src/auth/AuthProvider.test.tsx src/api/client.test.ts

Set-Location D:\BKQuiz\backend
.\mvnw.cmd -Dtest=JwtServiceTest,TokenHashServiceTest verify
```

### 3.3 CORS

Implementation:

- CORS chỉ đăng ký cho `/api/**`.
- Origins lấy từ `FRONTEND_ORIGINS`.
- Cho phép credentials.
- Methods: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS`.
- Headers: `Authorization`, `Content-Type`, `Idempotency-Key`, `X-XSRF-TOKEN`, `X-Request-Id`.
- Exposed headers: `X-Request-Id`, `Location`.
- WebSocket endpoint dùng cùng danh sách origin nhưng cấu hình riêng trong `ClassroomWebSocketConfig`.

File chính:

- `backend/src/main/java/com/genquiz/bk/security/SecurityConfig.java`
- `backend/src/main/java/com/genquiz/bk/classroom/ClassroomWebSocketConfig.java`
- `backend/src/main/resources/application.yml`

Rủi ro migration:

- Không dùng wildcard khi `allowCredentials=true`.
- Pages preview deployments có hostname động; không nên đưa wildcard rộng vào production. Cần tách origin production và preview có kiểm soát.
- `/ws` không dùng CORS config `/api/**`; migration Ably phải loại bỏ giả định endpoint same-origin.

Lệnh kiểm tra thủ công:

```powershell
curl.exe -i -X OPTIONS http://localhost:8080/api/auth/refresh-token `
  -H "Origin: http://localhost:5173" `
  -H "Access-Control-Request-Method: POST" `
  -H "Access-Control-Request-Headers: X-XSRF-TOKEN,Content-Type"
```

## 4. Spring Boot backend

### 4.1 Profiles và startup validation

Implementation:

- Cấu hình chung: `backend/src/main/resources/application.yml`.
- Profile production: `backend/src/main/resources/application-prod.yml`.
- Không tìm thấy bean `@Profile`; phần lớn khác biệt môi trường qua biến môi trường và `@ConditionalOnProperty`.
- Profile `prod` tắt Swagger/OpenAPI UI, đặt cookie secure và giảm log SQL/security.
- `StartupSecurityValidator` kiểm tra một số secret/origin/config không an toàn khi chạy production.
- Docker Compose hiện không đặt `SPRING_PROFILES_ACTIVE=prod`; cần đặt rõ trong cloud deployment.

Biến môi trường:

- `SPRING_PROFILES_ACTIVE=prod` cần được thêm ở deployment, dù không xuất hiện trong template hiện tại.
- `API_DOCS_ENABLED`, `COOKIE_SECURE`, `FRONTEND_ORIGINS`.

Rủi ro migration:

- Chạy Cloud Run mà quên `prod` có thể để docs bật và dùng default không phù hợp.
- Root `.env` được import optional trong development; production phải dùng Secret Manager/runtime env, không mount hoặc bake `.env` vào image.

Lệnh kiểm tra:

```powershell
Set-Location D:\BKQuiz\backend
$env:SPRING_PROFILES_ACTIVE='prod'
.\mvnw.cmd -DskipTests spring-boot:run
```

### 4.2 Datasource, JPA và Flyway

Implementation:

- PostgreSQL nghiệp vụ dùng `DATABASE_URL`, fallback `BKQUIZ_DATABASE_URL`, rồi local JDBC URL.
- Username/password có cặp `DATABASE_*` và fallback `BKQUIZ_DATABASE_*`.
- Hikari mặc định tối đa 6 connection, tối thiểu 1, acquire timeout 10 giây; JDBC URL thêm `reWriteBatchedInserts=true`.
- Hibernate `ddl-auto=validate`, UTC, batch size mặc định 50, ordered insert/update, slow-query threshold cấu hình được.
- Flyway luôn bật, migrations ở `classpath:db/migration`, validate naming.
- Có credential migration riêng qua `DATABASE_MIGRATION_USERNAME/PASSWORD`.
- Migrations hiện đến `V24`; dùng nhiều tính năng PostgreSQL như UUID, JSONB và partial index.

File chính:

- `backend/src/main/resources/application.yml`
- `backend/src/main/resources/db/migration/V1__baseline.sql` đến `V24__attempt_ai_chat.sql`
- `backend/pom.xml`

Biến môi trường:

- `DATABASE_URL`, `DATABASE_USERNAME`, `DATABASE_PASSWORD`
- `BKQUIZ_DATABASE_URL`, `BKQUIZ_DATABASE_USERNAME`, `BKQUIZ_DATABASE_PASSWORD`
- `DATABASE_MIGRATION_USERNAME`, `DATABASE_MIGRATION_PASSWORD`
- `DATABASE_POOL_SIZE`, `DATABASE_MIN_IDLE`
- `DATABASE_JDBC_BATCH_SIZE`, `DATABASE_SLOW_QUERY_MS`

Đánh giá Neon:

- PostgreSQL/Flyway hiện tại phù hợp về engine.
- Phải chọn đúng endpoint: runtime có thể dùng pooled endpoint; Flyway/DDL nên dùng direct/unpooled endpoint hoặc cấu hình đã được Neon hỗ trợ rõ ràng.
- Tổng số connection phải tính theo số instance Cloud Run x pool size. `6 x số instance` có thể nhanh chóng vượt quota Neon.
- Các job claim dùng `FOR UPDATE SKIP LOCKED` và scheduled worker phụ thuộc transaction/lock PostgreSQL; cần test trực tiếp trên Neon trước production.
- Cloud Run scale-to-zero có thể làm Spring DB-poll worker không chạy; worker cần min instance hoặc được thay bằng event/Cloud Tasks ở stage sau.

Lệnh kiểm tra:

```powershell
Set-Location D:\BKQuiz\backend
.\mvnw.cmd verify
```

Test này khởi tạo context/migration theo test configuration; kiểm tra Neon staging bổ sung:

```powershell
$env:DATABASE_URL='jdbc:postgresql://<neon-host>/<database>?sslmode=require'
$env:DATABASE_USERNAME='<runtime-user>'
# DATABASE_PASSWORD được cấp qua secret của terminal/CI, không ghi vào lệnh lưu trong repo.
.\mvnw.cmd -DskipTests spring-boot:run
```

### 4.3 Background/scheduled workers trong Spring

`@EnableScheduling` nằm trong `BkApplication`. Các scheduler tìm thấy:

| Worker/scheduler | File | Cơ chế hiện tại | Biến cấu hình chính |
|---|---|---|---|
| Job worker poll | `job/JobWorker.java` | Poll PostgreSQL, claim một job bằng `FOR UPDATE SKIP LOCKED` | `WORKER_ENABLED`, `JOB_POLL_DELAY`, `JOB_LEASE_DURATION`, `JOB_MAX_ATTEMPTS` |
| Worker heartbeat | `job/JobWorker.java` | Ghi `job_worker_heartbeats` mỗi 10 giây mặc định | `JOB_WORKER_HEARTBEAT_DELAY` |
| Reclaim stale jobs | `job/JobWorker.java` | Quét lease stale mỗi 30 giây | `JOB_LEASE_DURATION` |
| RAG health/capability poll | `rag/RagProcessorHealthService.java` | Poll RAG định kỳ, kể cả API process | `RAG_HEALTH_POLL_DELAY` |
| Classroom attachment cleanup | `classroom/ClassroomAttachmentCleanup.java` | Xóa attachment pending quá hạn | `CLASSROOM_ATTACHMENT_CLEANUP_DELAY` |
| Account anonymization | `user/UserService.java` | Cron mỗi giờ ở phút 15 | hiện hard-code trong annotation |

Job handlers đã đăng ký:

- `AUTH_EMAIL` -> `AuthMailJobHandler` -> Resend.
- `SOURCE_INGESTION` -> `SourceIngestionHandler` -> upload/reindex RAG.
- `RAG_INDEX_POLL` -> `RagIndexPollHandler` -> poll và sync chunks.
- `QUIZ_GENERATION` -> `QuizGenerationHandler` -> RAG streaming, checkpoint, commit.

`JobType` còn có `CHAT_RESPONSE`, `EXPORT`, `ACCOUNT_DELETION`, nhưng không tìm thấy `JobHandler` tương ứng trong registration hiện tại.

Retry hiện tại:

- Job có `attempts`, `maxAttempts`, `availableAt`, lease và trạng thái `QUEUED/RETRY/RUNNING/...` trong PostgreSQL.
- RAG error chỉ retry khi upstream đánh dấu retryable; `Retry-After` được tôn trọng.
- Quiz provider/batch retry mặc định tối thiểu 5 phút; batch thành công defer mặc định 15 giây.
- RAG indexing poll backoff `2 -> 3 -> 5 -> 10` giây; counter backoff hiện nằm trong memory của process nên reset khi restart.

Rủi ro migration:

- Không được nhầm Spring JobWorker với Celery worker; đây là hai hàng đợi độc lập.
- Cloud Run service scale-to-zero không phù hợp cho polling scheduler. Tối thiểu Stage 1 phải tách API/worker deployment và giữ worker có `min-instances=1`, hoặc chuyển từng loại job sang Cloud Tasks/Pub/Sub trước khi cho scale-to-zero.
- Mọi scheduled task chạy trên mỗi replica. Cleanup/anonymization cần singleton scheduling hoặc idempotency được kiểm chứng trước khi scale worker >1.
- `RagProcessorHealthService` tạo traffic từ mọi replica; cần cân nhắc một health aggregation path/cache phân tán.

Lệnh kiểm tra:

```powershell
Set-Location D:\BKQuiz\backend
.\mvnw.cmd -Dtest=JobWorkerHeartbeatTest,JobWorkerFailureClassificationTest,AuthMailJobHandlerTest,SourceIngestionHandlerTest,RagProcessorHealthServiceTest verify
```

### 4.4 Storage abstraction và S3-compatible implementation

Implementation nguồn tài liệu:

- Interface `SourceObjectStorage` cung cấp `scanAndStore`, `read`, `delete`.
- `LocalSourceObjectStorage` là default khi `STORAGE_PROVIDER=local`.
- `S3SourceObjectStorage` bật khi `STORAGE_PROVIDER=s3`, dùng AWS SDK `S3Client`, static credentials, endpoint override và path-style tùy chọn.
- Trước khi lưu S3, file được ghi temp, kiểm tra loại bằng Tika và scan ClamAV; metadata S3 chứa tên file và SHA.
- `ClassroomObjectStorage` hỗ trợ local/S3, presigned GET khoảng 5 phút.
- `AvatarService` hiện chỉ lưu/đọc local, không dùng abstraction S3; đây là khoảng trống đối với R2.

File chính:

- `backend/src/main/java/com/genquiz/bk/source/SourceObjectStorage.java`
- `backend/src/main/java/com/genquiz/bk/storage/LocalSourceObjectStorage.java`
- `backend/src/main/java/com/genquiz/bk/storage/S3SourceObjectStorage.java`
- `backend/src/main/java/com/genquiz/bk/storage/StorageConfig.java`
- `backend/src/main/java/com/genquiz/bk/storage/ClassroomObjectStorage.java`
- `backend/src/main/java/com/genquiz/bk/storage/AvatarService.java`
- `backend/src/main/java/com/genquiz/bk/storage/LocalFileAccessController.java`

Biến môi trường:

- `STORAGE_PROVIDER`
- `LOCAL_STORAGE_ROOT`, `LOCAL_STORAGE_TEMP`
- `USER_STORAGE_QUOTA_BYTES`
- `S3_ENDPOINT`, `S3_REGION`, `S3_BUCKET`
- `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_PATH_STYLE`
- `CLAMAV_ENABLED`, `CLAMAV_HOST`, `CLAMAV_PORT`
- `MAX_UPLOAD_SIZE`, `MAX_REQUEST_SIZE`

Đánh giá R2:

- Implementation S3-compatible là nền tảng phù hợp để thử R2.
- Không nên coi migration hoàn tất chỉ bằng đổi endpoint: avatar vẫn local; RAG vẫn nhận multipart và lưu thêm bản local trong `USER_UPLOAD_DIR`; local file controller và cleanup semantics cần tách khỏi filesystem.
- ClamAV hiện giả định TCP daemon. Cloud Run/R2 cần quyết định scan đồng bộ, service riêng hay quarantine workflow.
- Presigned URL, content-disposition, CORS bucket, checksum và multipart size cần integration test với R2 thật.

Lệnh kiểm tra:

```powershell
Set-Location D:\BKQuiz\backend
.\mvnw.cmd -Dtest=LocalFileStorageTest,SourceIngestionHandlerTest verify

Set-Location D:\BKQuiz
docker compose --profile s3 up -d postgres minio clamav
docker compose --profile s3 config
```

### 4.5 Spring -> RAG HTTP clients

Implementation:

- `RagClient` dùng Spring `RestClient`, base URL `${RAG_SERVICE_URL}/api/v2`.
- Headers nội bộ: `X-Internal-API-Key`, `X-User-Id`, `X-Request-Id`; upload thêm `Idempotency-Key`.
- Connect/read timeout cấu hình riêng.
- NDJSON được đọc cho quiz generation và Attempt tutor chat.

Endpoint đang gọi:

- `POST /user-documents` multipart.
- `POST /user-documents/{documentId}/reindex`.
- `GET /user-documents/resolve?sha256=...`.
- `GET /indexing-jobs/{jobId}`.
- `GET /user-documents/{documentId}`.
- `GET /user-documents/{documentId}/chunks?page=&size=500`.
- `POST /user-rag/generate-quiz` và `/generate-quiz/stream`.
- `POST /attempt-tutor/chat/stream`.
- `GET /capabilities`, `/health/ready`.

File chính:

- `backend/src/main/java/com/genquiz/bk/rag/RagClient.java`
- `backend/src/main/java/com/genquiz/bk/rag/RagProperties.java`
- `backend/src/main/java/com/genquiz/bk/rag/RagProcessorHealthService.java`
- `backend/src/main/java/com/genquiz/bk/source/SourceIngestionHandler.java`
- `backend/src/main/java/com/genquiz/bk/source/RagIndexPollHandler.java`
- `backend/src/main/java/com/genquiz/bk/quiz/QuizGenerationHandler.java`

Biến môi trường:

- `RAG_ENABLED`, `RAG_SERVICE_URL`, `RAG_INTERNAL_API_KEY`
- `RAG_CONNECT_TIMEOUT`, `RAG_READ_TIMEOUT`, `RAG_HEALTH_POLL_DELAY`

Rủi ro migration:

- Internal API key là shared secret; trên Cloud Run nên kết hợp service-to-service IAM/OIDC. Giữ key trong Secret Manager trong giai đoạn chuyển tiếp, không đưa vào image.
- Streaming request dài cần kiểm tra Cloud Run request timeout, proxy buffering và client disconnect.
- Upload hiện copy cả file qua Spring process; sau R2 nên cân nhắc signed object reference hoặc RAG đọc object đã được cấp quyền thay vì multipart lớn.
- `RAG_SERVICE_URL` phải là URL private/authenticated phù hợp; không đưa internal endpoint xuống frontend.

Lệnh kiểm tra:

```powershell
Set-Location D:\BKQuiz\backend
.\mvnw.cmd -Dtest=RagClientTest,RagProcessorHealthServiceTest,SourceIngestionHandlerTest verify

curl.exe -i http://localhost:8090/health/ready
curl.exe -i http://localhost:8090/api/v2/capabilities -H "X-Internal-API-Key: <redacted>"
```

## 5. RAG/FastAPI

### 5.1 Database configuration và SQLite-specific code

Implementation:

- `Settings.database_url` hiện **bắt buộc** bắt đầu bằng `sqlite:///`; validator báo lỗi nếu dùng PostgreSQL.
- SQLAlchemy engine luôn truyền `check_same_thread=False`.
- Connection event bật SQLite pragmas: foreign keys, WAL, `synchronous=NORMAL`, busy timeout, temp store memory, cache khoảng 64 MB và WAL autocheckpoint.
- Startup yêu cầu Alembic head chính xác `0005`.
- Models/Alembic dùng `sqlite_where` cho partial indexes.
- Readiness đặt tên check database là `sqlite`.
- SQLite lưu document, indexing job, operation/idempotency và math extraction metadata; PostgreSQL Spring vẫn là nguồn nghiệp vụ riêng.

File chính:

- `rag-service/app/core/config.py`
- `rag-service/app/db/database.py`
- `rag-service/app/db/models.py`
- `rag-service/alembic.ini`
- `rag-service/alembic/env.py`
- `rag-service/alembic/versions/0001_initial.py` đến `0005_reindex_jobs.py`
- `rag-service/app/api/routes/health.py`

Biến môi trường:

- `DATABASE_URL` - hiện mặc định dạng `sqlite:///data/rag.db`.

Đánh giá Neon:

- Đây là blocker kiến trúc, không phải thay đổi cấu hình đơn thuần.
- Cần bỏ validator SQLite-only, dùng PostgreSQL driver async/sync phù hợp, loại PRAGMA và `_ensure_parent`, tạo migration PostgreSQL tương ứng, thay `sqlite_where` bằng dialect-neutral/PostgreSQL predicate, kiểm tra UUID/timezone/concurrency.
- SQLite + filesystem hiện cùng nằm trong volume `rag-data`, khiến state và index commit có coupling chặt. Nên tách PostgreSQL metadata trước hoặc đồng thời với Qdrant contract, không triển khai nhiều RAG replica khi còn SQLite/FAISS local.

Lệnh kiểm tra:

```powershell
Set-Location D:\BKQuiz\rag-service
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest tests/test_database_migration.py -q
```

### 5.2 FAISS và filesystem dependencies

Implementation:

- Mỗi tenant/user có một `VectorStore` dưới `USER_INDEX_DIR`; system corpus dùng `SYSTEM_INDEX_DIR`.
- Snapshot gồm `vectors.faiss`, `chunks.json`, `manifest.json` trong thư mục version và con trỏ `active.json`.
- Commit dùng file tạm, `fsync` và `os.replace` để atomic-swap trên cùng filesystem.
- FAISS dùng `IndexFlatIP`; retrieval tải index/chunks từ disk.
- Original upload RAG nằm tại `USER_UPLOAD_DIR/<safe-user>/<document>/original-file`; reindex đọc file này.
- Readiness kiểm tra dung lượng trống của upload/index disk.
- Root Docker Compose mount cùng volume `rag-data` cho RAG API, worker và beat.
- Embedding/retrieval/BM25 caches là in-process; listener invalidation chỉ tác động process đang giữ store.

File chính:

- `rag-service/app/services/vector_store.py`
- `rag-service/app/services/user_index_manager.py`
- `rag-service/app/services/system_indexing_service.py`
- `rag-service/app/services/hybrid_retrieval.py`
- `rag-service/app/main.py`

Biến môi trường:

- `USER_UPLOAD_DIR`, `USER_INDEX_DIR`
- `SYSTEM_DOCUMENTS_DIR`, `SYSTEM_INDEX_DIR`
- `EMBEDDING_MODEL`, `EMBEDDING_BACKEND`, `EMBEDDING_PRECISION`, `EMBEDDING_ONNX_MODEL_PATH`
- `RAG_PRELOAD_EMBEDDING`, `RAG_CPU_THREADS`, `RAG_LOW_MEMORY_MODE`, `WORKER_MODEL_IDLE_SECONDS`
- `CHUNK_SIZE_CHARS`, `CHUNK_OVERLAP_CHARS`
- `RAG_DEFAULT_TOP_K`, `RAG_MAX_TOP_K`, `RAG_MIN_SCORE`, `RAG_MAX_CONTEXT_CHARS`
- `HYBRID_*`, `RERANKER_*`, `QUERY_EMBEDDING_CACHE_SIZE`, `RETRIEVAL_CACHE_*`

Đánh giá Qdrant:

- Qdrant phù hợp để loại volume FAISS và cho phép Cloud Run stateless/multi-replica, nhưng cần một storage adapter mới; không thể đổi URL/config trên implementation hiện tại.
- Phải bảo toàn filter `owner/user`, `documentIds`, chunk metadata, fingerprint/model version, atomic reindex semantics và tenant isolation.
- Hybrid BM25 hiện local. Cần quyết định dùng Qdrant sparse vectors/hybrid search hay giữ BM25 trong một service/state riêng.
- Cần thiết kế invalidate cache đa replica; hiện cache chỉ in-process.
- Original file phải chuyển sang R2 hoặc một object reference; Qdrant chỉ thay vector store, không thay upload storage.

Lệnh kiểm tra:

```powershell
Set-Location D:\BKQuiz\rag-service
.\.venv\Scripts\python.exe -m pytest tests/test_hybrid_retrieval.py tests/test_retrieval_service.py tests/test_system_indexing.py tests/test_index_lock_policy.py -q
```

### 5.3 Redis usages - phân loại rõ

Tất cả hiện dùng chung `REDIS_URL`, nhưng mục đích khác nhau:

| Nhóm | Implementation | Key/cơ chế | Đích migration |
|---|---|---|---|
| Celery broker | `worker/celery_app.py`, `worker/tasks.py` | Redis transport/queue `CELERY_QUEUE` | Pub/Sub + Cloud Tasks; không chuyển phần này sang Upstash như cache |
| Worker heartbeat | `worker/heartbeat.py` | TTL key, refresh định kỳ | Có thể Upstash hoặc health/lease trong nền tảng mới |
| Reconcile dedupe | `worker/tasks.py` | `SET NX EX` theo job ID | Cloud Tasks task-name/idempotency hoặc Upstash tạm thời |
| Distributed index lock | `services/user_index_manager.py` | Redis lock theo user/index | Qdrant/PostgreSQL advisory/idempotency hoặc Upstash; phải kiểm chứng semantics |
| Rate limit | `services/rate_limiter.py` | `INCR` + `EXPIRE` theo phút/user/scope | Upstash phù hợp |
| Embedding/retrieval/BM25 cache | các service RAG | In-memory LRU/TTL, **không dùng Redis** | Cần quyết định giữ per-instance hay chuyển Upstash; không tự động được migrate |

Biến môi trường:

- `REDIS_URL`, `REDIS_CONNECT_TIMEOUT_SECONDS`, `REDIS_SOCKET_TIMEOUT_SECONDS`
- `INDEX_LOCK_MODE`, `INDEX_LOCK_FALLBACK_COOLDOWN_SECONDS`
- `CELERY_QUEUE`, `CELERY_WORKER_HEARTBEAT_KEY`
- `CELERY_WORKER_HEARTBEAT_INTERVAL_SECONDS`, `CELERY_WORKER_HEARTBEAT_TTL_SECONDS`
- `PENDING_JOB_RECONCILE_SECONDS`
- `GEMINI_GLOBAL_RPM`, `GEMINI_USER_RPM`, `ASK_USER_RPM`, `UPLOAD_USER_RPM`

Rủi ro migration:

- Không được thay `REDIS_URL` bằng Upstash rồi coi Celery đã migrate; Celery broker và cache/lock/rate limit phải tách config trước.
- Upstash có latency/network và giới hạn command/connection khác Redis local; distributed lock cần kiểm tra fencing/idempotency, không chỉ mutual exclusion ngắn hạn.
- Rate limiter hiện fail closed nếu Redis lỗi; cần quyết định chính sách production rõ ràng.

Lệnh kiểm tra:

```powershell
Set-Location D:\BKQuiz\rag-service
.\.venv\Scripts\python.exe -m pytest tests/test_index_lock_policy.py tests/test_phase4_api_security.py tests/test_worker_runtime.py -q
```

### 5.4 Celery tasks, retry và scheduler

Implementation:

- Celery app `bkquiz-rag` dùng Redis broker, queue mặc định `rag-indexing`.
- Worker topology mặc định/được validate là `solo`, concurrency `1`; phù hợp local SQLite/FAISS nhưng không phải topology cloud cuối.
- `process_indexing_job` có `max_retries=3`, `acks_late`, reject khi worker lost, prefetch 1.
- Retry countdown exponential có jitter và cap 60 giây; ServiceError không retryable hoặc job hết lượt sẽ kết thúc theo job state.
- `recover_stale_jobs` phục hồi job stale và dispatch lại.
- `reconcile_pending_jobs` chỉ dispatch job pending cũ khi có heartbeat worker, dùng Redis dedupe key.
- Beat chạy maintenance mỗi 60 giây; task expiry 55 giây để không tích backlog maintenance khi worker dừng.

File chính:

- `rag-service/app/worker/celery_app.py`
- `rag-service/app/worker/tasks.py`
- `rag-service/app/worker/heartbeat.py`
- `rag-service/app/worker/runtime.py`
- `rag-service/app/services/indexing_job_service.py`

Biến môi trường:

- `CELERY_QUEUE`, `CELERY_WORKER_POOL`, `CELERY_WORKER_CONCURRENCY`
- `INDEXING_JOB_MAX_ATTEMPTS`, `INDEXING_JOB_STALE_SECONDS`
- heartbeat/reconcile variables nêu ở mục Redis.

Đánh giá Pub/Sub + Cloud Tasks + Cloud Scheduler:

- Không có adapter GCP hiện tại.
- Pub/Sub phù hợp phát sự kiện; Cloud Tasks phù hợp delivery HTTP có schedule/retry/idempotency; Cloud Scheduler thay Celery beat.
- Cần ánh xạ rõ ack/retry/dead-letter, job attempt trong DB, task name idempotency và stale recovery trước khi bỏ Celery.
- RAG indexing hiện cần disk chung và lock theo user. Chỉ đổi broker trước khi chuyển SQLite/FAISS có thể tạo worker Cloud Run stateless nhưng không nhìn thấy cùng dữ liệu.

Lệnh kiểm tra:

```powershell
Set-Location D:\BKQuiz\rag-service
.\.venv\Scripts\python.exe -m pytest tests/test_phase5_async_api.py tests/test_phase5_operations.py tests/test_worker_runtime.py -q

# Local worker; cần Redis và database RAG đã migrate.
.\.venv\Scripts\python.exe -m celery -A app.worker.celery_app:celery_app worker --pool=solo --concurrency=1 --loglevel=INFO
```

### 5.5 LLM providers và production Ollama

Implementation:

- Quiz provider order hiện hỗ trợ Gemini API key, Gemini OAuth và Ollama fallback theo cấu hình.
- Ollama dùng local HTTP base URL và model local; không phù hợp Cloud Run production target hiện tại.
- Math Vision và structured generation có cấu hình Gemini riêng.

File chính:

- `rag-service/app/services/quiz_llm_provider.py`
- `rag-service/app/services/ollama_qwen_provider.py`
- `rag-service/app/services/gemini_service.py`
- `rag-service/app/core/config.py`
- `rag-service/.env.example`

Biến môi trường chính:

- `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_*`
- `GEMINI_OAUTH_ENABLED`, `GEMINI_OAUTH_MODEL`, `GEMINI_OAUTH_QUOTA_PROJECT`, `GEMINI_OAUTH_TIMEOUT_SECONDS`
- `LLM_FALLBACK_ENABLED`
- `OLLAMA_ENABLED`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_*`
- `MATH_VISION_ENABLED`, `MATH_VISION_MODEL`, `MATH_VISION_TIMEOUT_SECONDS`

Yêu cầu production:

- Đặt `OLLAMA_ENABLED=false` và không deploy/advertise Ollama endpoint.
- Nếu `LLM_FALLBACK_ENABLED=true`, startup validation phải vẫn có ít nhất provider cloud hợp lệ.
- API key/ADC phải ở Secret Manager hoặc workload identity; không bake credential vào image.

Lệnh kiểm tra:

```powershell
Set-Location D:\BKQuiz\rag-service
.\.venv\Scripts\python.exe -m pytest tests/test_gemini_config.py tests/test_gemini_service.py tests/test_quiz_llm_fallback.py -q
```

## 6. STOMP/WebSocket realtime

Implementation server:

- Spring endpoint `/ws`.
- Simple broker in-process với destination prefix `/topic`; app prefix `/app`.
- STOMP `CONNECT` yêu cầu Bearer JWT trong native header.
- `SUBSCRIBE /topic/classrooms/{classroomId}` kiểm tra active classroom membership trong PostgreSQL.
- Publisher gửi event sau transaction commit qua `SimpMessagingTemplate`.
- Không tìm thấy `@MessageMapping`; thao tác ghi vẫn qua REST, WebSocket chủ yếu dùng invalidate/notification.

Implementation client:

- `@stomp/stompjs` trong `ClassroomDetail.tsx`.
- Broker URL là same-origin `ws(s)://<location.host>/ws`.
- Gửi access token khi connect; reconnect backoff từ khoảng 1 đến 30 giây.
- Khi nhận event, frontend invalidate React Query thay vì tin payload là nguồn dữ liệu cuối.

File chính:

- `backend/src/main/java/com/genquiz/bk/classroom/ClassroomWebSocketConfig.java`
- `backend/src/main/java/com/genquiz/bk/classroom/ClassroomRealtimePublisher.java`
- `frontend/src/app/pages/ClassroomDetail.tsx`
- `frontend/package.json`

Đánh giá Ably:

- Ably không phải drop-in replacement cho Spring simple broker/STOMP authorization.
- Cần endpoint cấp Ably token/capability theo user và classroom membership; không đưa Ably API secret xuống browser.
- Giữ REST/PostgreSQL là nguồn sự thật và event chỉ làm invalidation là mô hình phù hợp để bảo toàn.
- Cần map channel, event type, revoke membership, reconnect/history và quota. Có thể hỗ trợ song song STOMP/Ably trong rollout.

Lệnh kiểm tra hiện tại:

```powershell
Set-Location D:\BKQuiz\frontend
npm run typecheck
npm test -- --run src/app/components/SharedResourceCard.test.tsx

# Smoke test thủ công: đăng nhập hai thành viên cùng lớp,
# mở /classrooms/<id>, gửi message/share và xác nhận client còn lại invalidate/refetch ngay.
```

## 7. Health, readiness và observability

### Spring

- Public `GET /api/health` kiểm tra PostgreSQL và tổng hợp `springWorker`, `ragApi`, `ragWorker`, queue/pending/contract.
- Nếu document processor degraded nhưng DB còn hoạt động, endpoint nghiệp vụ này có thể vẫn trả HTTP 200 với body degraded; không nên dùng mù quáng làm Cloud Run readiness duy nhất.
- Actuator expose `health`, `info`, `metrics`, `prometheus`; probes bật.
- Security cho phép `/actuator/health/**`; metrics chi tiết cần quyền theo config hiện tại.

File:

- `backend/src/main/java/com/genquiz/bk/system/SystemController.java`
- `backend/src/main/java/com/genquiz/bk/rag/RagProcessorHealthService.java`
- `backend/src/main/resources/application.yml`
- `backend/src/main/java/com/genquiz/bk/security/SecurityConfig.java`

### RAG

- `GET /health/live`: process liveness.
- `GET /health/ready`: kiểm tra SQLite, Redis, Celery heartbeat, queue length, pending/running jobs, local disk, embedding và Gemini config.
- Thiếu worker heartbeat hoặc một dependency bị đánh DOWN có thể làm readiness 503 dù FastAPI process còn phục vụ một số endpoint.
- `/metrics` xuất Prometheus metrics.
- FastAPI docs/OpenAPI chỉ bật trong development.

File:

- `rag-service/app/api/routes/health.py`
- `rag-service/app/main.py`

Rủi ro migration:

- Cloud Run startup/liveness nên kiểm tra process; readiness nghiệp vụ tách khỏi dependency tùy chọn để tránh restart loop hoặc loại instance chỉ vì worker khác đang down.
- Sau khi broker/index/database tách cloud, health field `sqlite`, local disk và Celery heartbeat phải được thay bằng check đúng dependency mới.
- Chưa có cấu hình Cloud Monitoring/IaC trong repo; Prometheus endpoint không tự được scrape trên Cloud Run.

Lệnh kiểm tra:

```powershell
curl.exe -i http://localhost:8080/actuator/health/liveness
curl.exe -i http://localhost:8080/actuator/health/readiness
curl.exe -i http://localhost:8080/api/health
curl.exe -i http://localhost:8090/health/live
curl.exe -i http://localhost:8090/health/ready
curl.exe -i http://localhost:8090/metrics
```

## 8. Docker, Compose và CI

### Dockerfiles

- `backend/Dockerfile`: Maven/Java 17 multi-stage build, non-root runtime, port 8080, container memory percentage option.
- `rag-service/Dockerfile`: Python 3.11 slim, cài runtime deps, chuẩn bị ONNX model ở build, non-root; command chạy Alembic rồi Uvicorn một worker trên port 8000.
- Không có frontend Dockerfile vì frontend hiện chạy Vite/local hoặc build static.

Rủi ro Cloud Run:

- RAG command cố định port 8000 và không đọc Cloud Run `$PORT`; Cloud Run có thể cấu hình container port 8000, nhưng nên chuẩn hóa entrypoint để dùng `$PORT`.
- Chạy Alembic trong mọi container startup có race khi nhiều instance khởi động. Production nên có migration job/release step riêng.
- RAG image bake model làm image lớn và startup/build chậm; cần đo cold start/RAM trước Cloud Run.
- Local volumes của Spring/RAG không bền trên Cloud Run.

### Compose

- Root `docker-compose.yml`: PostgreSQL pgvector, optional MinIO profile `s3`, ClamAV, Spring API và worker tách bằng `WORKER_ENABLED`, Redis/RAG API/Celery worker/beat trong profile `rag`.
- Spring API và worker cùng mount local uploads.
- RAG API/worker/beat cùng mount `rag-data` để chia sẻ SQLite, upload và FAISS.
- `rag-service/docker-compose.yml`: stack RAG standalone.
- `rag-service/docker-compose.test.yml`: override integration test/fake Gemini.
- `infra/postgres/compose.yml`: PostgreSQL development riêng.

### CI

- `.github/workflows/ci.yml`: backend `mvnw verify`; frontend `npm ci`, lint, typecheck, test, build.
- `.github/workflows/rag-ci.yml`: Python 3.11, Alembic SQLite, pytest, Ruff, mypy, pip check/audit, OpenAPI drift, Docker build và compose integration.
- Chưa có IaC/deploy pipeline cho Cloudflare, GCP, Neon, R2, Qdrant, Upstash hoặc Ably.

Lệnh kiểm tra:

```powershell
Set-Location D:\BKQuiz
docker compose config
docker compose --profile s3 config
docker compose --profile rag config

Set-Location D:\BKQuiz\backend
docker build -t bkquiz-backend:audit .

Set-Location D:\BKQuiz\rag-service
docker build -t bkquiz-rag:audit .
docker compose -f docker-compose.yml -f docker-compose.test.yml config
```

## 9. Thứ tự và phụ thuộc migration đề xuất

Đây là dependency order, không phải lệnh triển khai ngay:

1. **Chốt domain/auth topology trước Cloudflare Pages.** Quyết định `/api` same-origin proxy hay cross-site cookies. Đây là điều kiện để Stage 1 frontend không làm hỏng refresh/CSRF.
2. **Đưa PostgreSQL nghiệp vụ sang Neon staging.** Kiểm tra Flyway, pooling, connection budget và `SKIP LOCKED`; chưa thay job architecture.
3. **Chuẩn hóa Spring stateless storage.** Mở rộng R2 cho source, classroom attachment và avatar; giữ API contract. RAG original-file vẫn là blocker riêng.
4. **Tách Spring API và worker deployment.** API có thể scale; DB-poll worker giữ min instance trong giai đoạn chuyển tiếp. Đưa migration ra release job.
5. **Chuyển RAG metadata SQLite sang PostgreSQL/Neon.** Đây là điều kiện để chạy nhiều RAG instance/worker an toàn.
6. **Chuyển original RAG upload sang R2 và FAISS sang Qdrant.** Bảo toàn tenant filter, reindex atomicity, fingerprint, chunk metadata và hybrid retrieval. Sau bước này RAG mới thực sự stateless.
7. **Tách Redis responsibilities.** Đặt rate-limit/lock/dedupe vào Upstash hoặc primitives mới; giữ broker riêng cho đến khi task delivery mới hoàn tất.
8. **Thay Celery bằng Pub/Sub + Cloud Tasks + Cloud Scheduler.** Chỉ thực hiện khi RAG DB/index/storage không còn phụ thuộc volume local.
9. **Thay STOMP bằng Ably.** Thêm token capability server-side và rollout song song; REST/DB vẫn là nguồn sự thật.
10. **Tắt Ollama production và harden observability/security.** Secret Manager, IAM service-to-service, Cloud Monitoring, alerts, backup/restore và disaster test.

Quan hệ phụ thuộc quan trọng:

```text
Cookie/domain decision -> Pages rollout
Neon business DB -> Spring Cloud Run API/worker staging
RAG SQLite -> PostgreSQL
RAG upload -> R2 -----> RAG stateless/multi-replica
FAISS -> Qdrant ------/
RAG stateless -> Celery broker replacement
Ably token auth -> STOMP retirement
```

## 10. Migration risks theo mức độ

### Blocker/critical

1. RAG config khóa cứng SQLite; không thể trỏ thẳng `DATABASE_URL` sang Neon.
2. FAISS, chunk manifest và original upload nằm trên filesystem dùng chung; Cloud Run filesystem không bền và không chia sẻ giữa instance.
3. Cookie refresh/CSRF với `SameSite=Lax` và readable XSRF cookie chưa có thiết kế domain cho Pages -> Cloud Run.
4. Spring JobWorker và các scheduler phụ thuộc process sống; Cloud Run scale-to-zero sẽ dừng xử lý nền.
5. Avatar vẫn local dù source/classroom đã có S3-compatible path.

### High

1. Celery broker, lock, heartbeat/dedupe và rate limit dùng chung một `REDIS_URL`; phải tách trước migration từng chức năng.
2. Cloud Run multi-instance + startup Alembic có race; cần migration job độc lập.
3. Neon connection budget nhân theo Hikari pool và số Cloud Run instance.
4. Ably cần authorization model mới; không thể chỉ thay URL STOMP.
5. ClamAV TCP daemon/local temp workflow chưa có production cloud topology.

### Medium

1. RAG caches/BM25 chỉ in-process và invalidation không đa replica.
2. Readiness hiện gộp dependency khác process và có thể quá nghiêm cho Cloud Run.
3. RAG Docker port/start command chưa cloud-native hoàn toàn.
4. Chưa có IaC, environment promotion, secret rotation, backup/restore hoặc rollback scripts.
5. `JobType` có các loại chưa thấy handler registration; cần xác nhận trước khi thay queue.

## 11. Stage 1 - điều kiện đầu vào và blocker

Stage 1 nên chỉ là nền tảng deploy/staging, chưa thay RAG datastore/vector/broker. Để bắt đầu an toàn cần chốt:

- Domain topology cho Pages/API và giải pháp cookie/CSRF; khuyến nghị `/api` reverse proxy cùng origin cho rollout đầu.
- GCP project/region, Cloud Run service accounts và Secret Manager ownership.
- Neon project/branch, direct URL cho migration, pooled URL cho runtime và connection budget.
- R2 bucket/CORS/lifecycle, lựa chọn malware scanning và phạm vi gồm cả avatar/classroom/source.
- Cách chạy Spring worker trong giai đoạn chuyển tiếp: Cloud Run service có min instance hoặc Cloud Run Job/Cloud Tasks; không được để scale-to-zero khi còn DB polling.
- Xác nhận Cloud Run staging có volume/state tạm cho RAG hiện tại hoặc trì hoãn deploy RAG cho tới khi PostgreSQL + Qdrant + R2 hoàn tất. Không nên chạy RAG hiện tại nhiều replica.
- Quy ước secret: không dùng `.env` production, không bake ADC/API key, không log credential.
- IaC và CI/CD owner; hiện repository chưa có cấu hình Cloudflare/GCP/Neon/Qdrant/Upstash/Ably.

## 12. Bộ lệnh audit đầy đủ

Chạy từ PowerShell; các lệnh không chứa secret:

```powershell
# Backend
Set-Location D:\BKQuiz\backend
.\mvnw.cmd verify

# Frontend
Set-Location D:\BKQuiz\frontend
npm ci
npm run lint
npm run typecheck
npm test -- --run
npm run build

# RAG
Set-Location D:\BKQuiz\rag-service
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/export_openapi.py
git diff --exit-code -- docs/openapi.json

# Compose config validation
Set-Location D:\BKQuiz
docker compose config
docker compose --profile s3 config
docker compose --profile rag config
```

## 13. Kết quả test tại thời điểm audit

| Gate | Kết quả |
|---|---|
| Backend `.\mvnw.cmd verify` | Đạt: 121 test; Flyway V1-V24 và Hibernate validation thành công trên PostgreSQL 16 Testcontainers |
| Frontend lint | Đạt |
| Frontend typecheck | Đạt |
| Frontend Vitest | Đạt: 90 test trong 34 test files |
| Frontend production build | Đạt; output ở `frontend/dist` |
| RAG Alembic 0001-0005 | Đạt trên SQLite tạm dành riêng cho audit |
| RAG pytest | Đạt: 179 test |
| RAG mypy | Đạt |
| RAG `pip check` | Đạt |
| RAG OpenAPI drift | Đạt; export không tạo diff |
| Docker Compose config | Đạt cho default, profile `s3` và profile `rag` |
| RAG Ruff | **Không đạt**: import block chưa được sắp xếp trong `rag-service/app/api/routes/v2.py:1` (`I001`) |
| RAG `pip-audit` | **Không đạt**: phát hiện 4 advisory trên `transformers==4.57.6`; hai advisory nêu fix version 5.0.0 và 5.3.0, hai advisory chưa hiện fix version trong output local |

Lưu ý môi trường: lần chạy pytest RAG đầu tiên bị startup guard chặn do `GEMINI_API_KEY` trong process environment không khớp `.env` development. Không có secret nào được ghi lại. Suite được chạy lại với `APP_ENV=test` và test credentials không nhạy cảm, sau đó đạt 179/179. Điều này xác nhận launcher/CI production cần nguồn secret xác định, không trộn process environment cũ với dotenv.

Các lỗi quality gate trên không được tự sửa trong lượt audit này để tuân thủ yêu cầu không thay đổi business/code logic.

## 14. Phạm vi file đã kiểm kê

Trước khi tạo báo cáo, 604 path trong repository được inventory bằng `rg --files` và loại các thư mục dependency/build (`node_modules`, `.venv`, `target`, `dist`, `.git`). Các nhóm file đã đọc/truy vết trực tiếp gồm:

- Root/CI/container: `README.md`, `.env.example`, `docker-compose.yml`, `.github/workflows/ci.yml`, `.github/workflows/rag-ci.yml`, `infra/postgres/compose.yml`, hai Dockerfile và các RAG compose file.
- Frontend: package/Vite/env config, API runtime/client, auth store/provider/API, routes, classroom STOMP page và các test liên quan.
- Spring: application profiles, security/auth/CSRF/CORS, datasource/Flyway, job domain/worker/handlers, RAG client/health, storage implementations, WebSocket config/publisher, system health và migrations V1-V24.
- RAG: Settings/lifespan, database/models/Alembic 0001-0005, API health/routes, vector/index/retrieval, Redis rate limit/lock, Celery app/tasks/heartbeat/runtime, Gemini/OAuth/Ollama router, parser/upload/indexing và test suite.

Không đọc giá trị trong `.env` thực tế, credential files, database rows, upload contents hoặc secrets runtime.
