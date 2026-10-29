# Giai đoạn 9 — khóa RAG bằng IAM và hardening production

## Kết quả triển khai

Giai đoạn 9 hoàn tất lớp bảo vệ production cuối của BKQuiz:

- Spring lấy Google-signed ID token từ Application Default Credentials của
  Cloud Run và gửi `Authorization: Bearer ...` tới RAG;
- RAG chỉ cho service account của Spring có `roles/run.invoker`;
- quyền `allUsers` của `bkquiz-rag-api` bị gỡ sau khi revision Spring mới đã
  sẵn sàng;
- Cloud Run Invoker IAM check được bật rõ ràng trên RAG;
- `X-Internal-API-Key` vẫn được kiểm tra trong FastAPI như lớp bảo vệ thứ hai;
- Ollama bị đặt `OLLAMA_ENABLED=false` và toàn bộ biến `OLLAMA_*` production bị
  xóa; local development không thay đổi;
- script từ chối secret nhạy cảm đang được cấu hình dưới dạng literal;
- hai Cloud Monitoring alert được tạo cho lỗi 5xx kéo dài của Spring và RAG;
- có checklist backup/restore và disaster test cho Neon, R2, Qdrant và Upstash.

Không có migration database ở giai đoạn này. Backend image bắt buộc phải được
build lại vì `RagClient` có thêm Cloud Run ID token. RAG image hiện tại có thể
giữ nguyên nếu đã chạy code Stage 7.

## 1. Điều kiện trước khi chạy

Trong PowerShell:

```powershell
$PROJECT_ID = 'bkquiz-stg-235740'
$REGION = 'asia-southeast1'
$BACKEND_SERVICE = 'bkquiz-api'
$RAG_SERVICE = 'bkquiz-rag-api'

gcloud config set project $PROJECT_ID
gcloud auth list
```

Tài khoản đang active cần quyền cập nhật Cloud Run, IAM policy của service,
Artifact Registry và Monitoring. Hai Cloud Run service phải đang hoạt động.

Kiểm tra service account runtime hiện tại:

```powershell
$BACKEND_SA = gcloud run services describe $BACKEND_SERVICE `
  --project=$PROJECT_ID `
  --region=$REGION `
  --format='value(spec.template.spec.serviceAccountName)'

$RAG_SA = gcloud run services describe $RAG_SERVICE `
  --project=$PROJECT_ID `
  --region=$REGION `
  --format='value(spec.template.spec.serviceAccountName)'

$BACKEND_SA
$RAG_SA
```

Không sử dụng email service account tự đoán. Script mặc định đọc chính email
đang gắn vào revision Cloud Run để tránh lỗi `Unknown service account`.

## 2. Build backend Stage 9

```powershell
cd D:\BKQuiz\backend

$REPOSITORY = 'bkquiz'
$TAG = "stage9-$(Get-Date -Format yyyyMMdd-HHmmss)"
$BACKEND_IMAGE = "${REGION}-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/backend:$TAG"

gcloud builds submit D:\BKQuiz\backend --tag $BACKEND_IMAGE
```

Không deploy image Stage 8 cũ: image đó chưa biết tạo Cloud Run ID token và sẽ
nhận 401/403 ngay sau khi RAG bị chuyển thành private.

## 3. Notification channel (khuyến nghị)

Liệt kê channel đã tạo trong Cloud Monitoring:

```powershell
gcloud beta monitoring channels list `
  --project=$PROJECT_ID `
  --format='table(name,displayName,type)'
```

Giữ lại full resource name, ví dụ:

```text
projects/bkquiz-stg-235740/notificationChannels/123456789
```

Nếu chưa có channel, có thể deploy trước không truyền tham số; alert policy vẫn
được tạo nhưng chưa gửi email/SMS. Sau đó gắn channel trong Monitoring Console.

## 4. Validate, xem trước và deploy

Không có notification channel:

```powershell
cd D:\BKQuiz

.\backend\deploy\deploy-stage9.ps1 `
  -BackendImage $BACKEND_IMAGE `
  -ValidateOnly

.\backend\deploy\deploy-stage9.ps1 `
  -BackendImage $BACKEND_IMAGE `
  -WhatIf

.\backend\deploy\deploy-stage9.ps1 `
  -BackendImage $BACKEND_IMAGE
```

Có notification channel:

```powershell
$CHANNEL = 'projects/bkquiz-stg-235740/notificationChannels/123456789'

.\backend\deploy\deploy-stage9.ps1 `
  -BackendImage $BACKEND_IMAGE `
  -NotificationChannels $CHANNEL
```

Nếu chưa muốn tạo alert trong lần đầu, thêm `-SkipMonitoring`. Script thực hiện
theo thứ tự an toàn:

1. kiểm tra image, hai service, service account và secret binding;
2. cấp `roles/run.invoker` trên RAG cho service account Spring;
3. deploy Spring với `RAG_IAM_ENABLED=true` và audience đúng URL RAG;
4. tắt/xóa cấu hình Ollama;
5. cuối cùng mới gỡ `allUsers` khỏi RAG;
6. kiểm tra lại trạng thái mục tiêu.

Biến mới trên Spring:

```text
RAG_IAM_ENABLED=true
RAG_IAM_AUDIENCE=https://<rag-service>-<hash>.<region>.run.app
```

Không tự thêm dấu `/api/v2` vào audience. Audience phải là origin Cloud Run,
không có path và không có dấu `/` cuối.

## 5. Smoke test

### Kiểm tra RAG không còn public

```powershell
$RAG_URL = gcloud run services describe $RAG_SERVICE `
  --project=$PROJECT_ID `
  --region=$REGION `
  --format='value(status.url)'

try {
  Invoke-WebRequest "$RAG_URL/health/live" -UseBasicParsing
  throw 'RAG van dang public.'
}
catch {
  Write-Host 'RAG private check returned an authentication error as expected.'
}
```

Kiểm tra IAM:

```powershell
gcloud run services get-iam-policy $RAG_SERVICE `
  --project=$PROJECT_ID `
  --region=$REGION `
  --format='table(bindings.role,bindings.members)'
```

Phải có service account Spring trong `roles/run.invoker` và không có
`allUsers`/`allAuthenticatedUsers`.

### Kiểm tra backend và luồng thật

```powershell
$BACKEND_URL = gcloud run services describe $BACKEND_SERVICE `
  --project=$PROJECT_ID `
  --region=$REGION `
  --format='value(status.url)'

Invoke-RestMethod "$BACKEND_URL/actuator/health/liveness"
Invoke-RestMethod "$BACKEND_URL/actuator/health/readiness"
```

Sau đó đăng nhập frontend và thực hiện cả hai luồng:

1. upload/reindex một tài liệu;
2. sinh thêm một câu AI vào Quiz.

Nếu Spring không lấy được ID token, log sẽ có `RAG_AUTHENTICATION_FAILED` hoặc
`Không thể lấy Cloud Run ID token cho RAG`. Kiểm tra lại service account runtime,
binding `roles/run.invoker` và `RAG_IAM_AUDIENCE`.

## 6. Xác nhận Ollama đã tắt

```powershell
$RAG_JSON = gcloud run services describe $RAG_SERVICE `
  --project=$PROJECT_ID `
  --region=$REGION `
  --format=json | ConvertFrom-Json

@($RAG_JSON.spec.template.spec.containers[0].env) |
  Where-Object { $_.name -like 'OLLAMA*' } |
  Select-Object name,value
```

Kết quả chỉ được có `OLLAMA_ENABLED=false`. Production config của FastAPI cũng
fail startup nếu giá trị này là `true`.

## 7. Monitoring và log

Script tạo hai policy idempotent:

- `BKQuiz bkquiz-api Cloud Run 5xx`;
- `BKQuiz bkquiz-rag-api Cloud Run 5xx`.

Liệt kê policy:

```powershell
gcloud monitoring policies list `
  --project=$PROJECT_ID `
  --filter='userLabels.application=bkquiz AND userLabels.stage=9' `
  --format='table(displayName,enabled,name)'
```

Khuyến nghị tạo thêm dashboard Cloud Run với request count, p95 latency,
instance count, container CPU/memory và Neon/Qdrant provider metrics. Không mở
`/metrics` của RAG ra public chỉ để scrape; Cloud Run built-in metrics không cần
endpoint public.

## 8. Backup và disaster test

### Neon PostgreSQL

- cấu hình history retention/PITR phù hợp gói Neon;
- mỗi tuần tạo một branch restore thử nghiệm tại timestamp trước đó;
- mỗi ngày chạy `pg_dump --format=custom` qua **direct endpoint**, không dùng
  pooled endpoint; lưu file dump đã mã hóa ở vị trí tách khỏi production;
- hàng tháng restore dump vào database rỗng và chạy kiểm tra Flyway/Hibernate.

Ví dụ không đưa password vào command history:

```powershell
$env:PGPASSWORD = Read-Host 'Neon migration password'
pg_dump --format=custom --no-owner --no-acl `
  --host='<direct-host>.neon.tech' --port=5432 `
  --username='<backup-user>' --dbname='bkquiz' `
  --file="bkquiz-$(Get-Date -Format yyyyMMdd-HHmmss).dump"
$env:PGPASSWORD = $null
```

### Cloudflare R2

- bucket production phải private và token chỉ có quyền bucket cần thiết;
- R2 durability không thay thế backup do xóa nhầm/application bug;
- mirror định kỳ sang bucket hoặc account thứ hai bằng `rclone`/S3-compatible
  tool; không dùng lifecycle xóa trên bản backup;
- bật bucket lock cho prefix backup nếu chính sách lưu giữ yêu cầu;
- mỗi quý restore ngẫu nhiên một file và đối chiếu checksum trong PostgreSQL.

### Qdrant

- dữ liệu chuẩn vẫn là PostgreSQL + R2, vì vậy có thể reindex toàn bộ;
- bật Qdrant Cloud automatic backup nếu gói hỗ trợ;
- tạo collection snapshot trước thay đổi schema/vector lớn;
- kiểm tra restore vào cluster thử nghiệm cùng minor version hoặc minor kế tiếp.

### Upstash

- Redis chỉ chứa cache, lock và rate-limit, không phải nguồn dữ liệu nghiệp vụ;
- mất Redis phải degrade/rebuild được, không restore vào giữa một job đang chạy;
- nếu dùng gói backup, bật daily backup và thử restore vào database riêng;
- sau restore, xóa lock/job key cũ trước khi đưa traffic trở lại.

### Tần suất disaster test

Mỗi quý thực hiện theo thứ tự:

1. restore Neon vào branch/database cô lập;
2. trỏ một RAG test revision vào database restore và Qdrant test collection;
3. restore/mirror một tập R2 mẫu;
4. reindex và chạy search + sinh Quiz;
5. ghi RPO/RTO thực tế, lỗi gặp phải và người chịu trách nhiệm;
6. xóa toàn bộ tài nguyên test sau khi xác nhận.

## 9. Rollback

Rollback an toàn phải mở RAG public trước, rồi mới tắt token ở Spring:

```powershell
gcloud run services update $RAG_SERVICE `
  --project=$PROJECT_ID `
  --region=$REGION `
  --no-invoker-iam-check

gcloud run services update $BACKEND_SERVICE `
  --project=$PROJECT_ID `
  --region=$REGION `
  --update-env-vars='RAG_IAM_ENABLED=false' `
  --remove-env-vars='RAG_IAM_AUDIENCE'
```

Ollama không được bật lại trong production. Nếu cần rollback AI provider, dùng
Gemini API/OAuth hoặc rollback revision RAG nhưng vẫn giữ `OLLAMA_ENABLED=false`.

## 10. Test mã nguồn

```powershell
cd D:\BKQuiz\backend
.\mvnw.cmd verify

cd D:\BKQuiz\rag-service
python -m pytest
python -m ruff check app tests
python -m mypy app
python -m pip check
```

Tài liệu tham khảo:

- https://cloud.google.com/run/docs/authenticating/service-to-service
- https://cloud.google.com/run/docs/securing/managing-access
- https://cloud.google.com/monitoring/alerts/policies-in-api
- https://cloud.google.com/secret-manager/docs/best-practices
- https://neon.com/blog/announcing-point-in-time-restore
- https://developers.cloudflare.com/r2/reference/durability/
- https://qdrant.tech/documentation/cloud/backups/
- https://upstash.com/docs/redis/howto/importexport
