# Giai đoạn 8 — chuyển STOMP realtime sang Ably

## Kết quả triển khai

Giai đoạn 8 thay Spring STOMP simple broker trong production bằng Ably Pub/Sub:

- Spring publish sự kiện classroom qua Ably REST sau khi transaction commit;
- frontend kết nối Ably Realtime và chỉ subscribe event `classroom-event`;
- `POST /api/realtime/token` cấp TokenRequest ngắn hạn cho đúng thành viên active;
- capability chỉ có `subscribe` trên đúng một channel classroom;
- API key Ably chỉ tồn tại trong Google Secret Manager và Cloud Run;
- PostgreSQL/REST vẫn là nguồn sự thật, Ably chỉ thông báo để frontend refetch;
- STOMP được giữ làm fallback local và rollback.

Không có Flyway migration trong giai đoạn này. RAG, Pub/Sub, Upstash và các stage
trước không thay đổi.

## 1. Tạo Ably application và API key

Trong Ably Dashboard:

1. Tạo application, ví dụ `bkquiz-stg`.
2. Tạo API key dành riêng cho Spring backend.
3. Capability của key cần cho namespace `bkquiz:classroom:*`:
   - `publish` để Spring phát event;
   - `subscribe` để key có thể ký token subscribe cho browser.
4. Không cấp `presence`, `history` hoặc publish cho browser.
5. Sao chép full API key một lần. Không đưa key vào frontend hoặc Git.

Spring luôn thu hẹp token của browser xuống một channel cụ thể và operation
`subscribe`. Membership được kiểm tra lại mỗi lần Ably gia hạn token.

## 2. Lưu API key vào Secret Manager

```powershell
$PROJECT_ID = 'bkquiz-stg-235740'
$REGION = 'asia-southeast1'
$SERVICE = 'bkquiz-api'
$SECRET_NAME = 'bkquiz-ably-api-key'

gcloud config set project $PROJECT_ID

gcloud secrets describe $SECRET_NAME --project=$PROJECT_ID 2>$null
if ($LASTEXITCODE -ne 0) {
  gcloud secrets create $SECRET_NAME `
    --project=$PROJECT_ID `
    --replication-policy=automatic
}

$ABLY_API_KEY = Read-Host 'Paste Ably API key'
$TEMP_SECRET = [IO.Path]::GetTempFileName()
try {
  [IO.File]::WriteAllText(
    $TEMP_SECRET,
    $ABLY_API_KEY,
    [Text.UTF8Encoding]::new($false)
  )
  gcloud secrets versions add $SECRET_NAME `
    --project=$PROJECT_ID `
    --data-file=$TEMP_SECRET
}
finally {
  Remove-Item $TEMP_SECRET -Force -ErrorAction SilentlyContinue
  $ABLY_API_KEY = $null
}
```

Lấy service account thực tế của backend và cấp quyền đọc secret:

```powershell
$BACKEND_SA = gcloud run services describe $SERVICE `
  --project=$PROJECT_ID `
  --region=$REGION `
  --format='value(spec.template.spec.serviceAccountName)'

if ([string]::IsNullOrWhiteSpace($BACKEND_SA)) {
  throw 'Khong tim thay service account cua bkquiz-api.'
}

gcloud secrets add-iam-policy-binding $SECRET_NAME `
  --project=$PROJECT_ID `
  --member="serviceAccount:$BACKEND_SA" `
  --role='roles/secretmanager.secretAccessor'
```

## 3. Build backend Stage 8

```powershell
cd D:\BKQuiz\backend

$REPOSITORY = 'bkquiz'
$TAG = "stage8-$(Get-Date -Format yyyyMMdd-HHmmss)"
$IMAGE = "${REGION}-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/backend:$TAG"

gcloud builds submit D:\BKQuiz\backend --tag $IMAGE
```

Nếu Artifact Registry dùng tên image khác, chỉ thay phần `backend`; script deploy
nhận mọi Artifact Registry image hợp lệ.

## 4. Validate và deploy Spring Cloud Run

```powershell
cd D:\BKQuiz

.\backend\deploy\deploy-stage8.ps1 `
  -Image $IMAGE `
  -AblySecret $SECRET_NAME `
  -AblySecretVersion latest `
  -ValidateOnly

.\backend\deploy\deploy-stage8.ps1 `
  -Image $IMAGE `
  -AblySecret $SECRET_NAME `
  -AblySecretVersion latest `
  -WhatIf

.\backend\deploy\deploy-stage8.ps1 `
  -Image $IMAGE `
  -AblySecret $SECRET_NAME `
  -AblySecretVersion latest
```

Cloud Run nhận:

```text
REALTIME_PROVIDER=ably
ABLY_API_KEY=<Secret Manager reference>
ABLY_CHANNEL_PREFIX=bkquiz:classroom:
ABLY_TOKEN_TTL_SECONDS=300
REALTIME_PUBLISH_ENABLED=true
```

Không đặt `ABLY_API_KEY` thành literal environment variable.

## 5. Build lại frontend Cloudflare

Trong Cloudflare project settings, thêm build variable:

```text
VITE_REALTIME_PROVIDER=ably
```

Giữ nguyên API URL đang hoạt động:

```text
VITE_API_BASE_URL=https://bkquiz-api-990266761128.asia-southeast1.run.app/api
VITE_API_SAME_ORIGIN_PROXY=false
```

Sau khi lưu biến, trigger deployment mới. Nếu build/deploy thủ công:

```powershell
cd D:\BKQuiz\frontend
$env:VITE_API_BASE_URL = 'https://bkquiz-api-990266761128.asia-southeast1.run.app/api'
$env:VITE_API_SAME_ORIGIN_PROXY = 'false'
$env:VITE_REALTIME_PROVIDER = 'ably'

npm ci
npm run test
npm run typecheck
npm run build
```

Upload thư mục `frontend/dist` bằng đúng Cloudflare Pages/Workers pipeline hiện
tại. Không tạo biến `VITE_ABLY_API_KEY`.

## 6. Smoke test

1. Mở hai trình duyệt hoặc hai tài khoản là thành viên cùng một classroom.
2. Mở DevTools Network và xác nhận có kết nối đến Ably, không còn request `/ws`.
3. Tài khoản A gửi, sửa và xóa tin nhắn.
4. Tài khoản B phải cập nhật ngay và REST refetch trả đúng dữ liệu PostgreSQL.
5. Publish assignment và share Topic/Quiz; tài khoản B nhận card mới ngay.
6. User không thuộc lớp gọi token endpoint phải nhận 404.
7. Xóa thành viên, chờ token tối đa 5 phút hết hạn và xác nhận không thể gia hạn.
8. Tạm chặn Ably: thao tác REST vẫn thành công và polling 3 giây vẫn cập nhật.

Kiểm tra Cloud Run:

```powershell
$BACKEND_URL = gcloud run services describe $SERVICE `
  --project=$PROJECT_ID `
  --region=$REGION `
  --format='value(status.url)'

Invoke-RestMethod "$BACKEND_URL/actuator/health/liveness"
Invoke-RestMethod "$BACKEND_URL/actuator/health/readiness"
```

## 7. Local development

Local mặc định tiếp tục STOMP:

```text
REALTIME_PROVIDER=stomp
VITE_REALTIME_PROVIDER=stomp
```

Không cần tài khoản Ably khi chạy local. Vite vẫn proxy `/ws` tới Spring.

## 8. Rollback

Frontend phải đổi lại và build lại:

```text
VITE_REALTIME_PROVIDER=stomp
```

Backend:

```powershell
gcloud run services update bkquiz-api `
  --project=$PROJECT_ID `
  --region=$REGION `
  --update-env-vars='REALTIME_PROVIDER=stomp' `
  --remove-secrets='ABLY_API_KEY'
```

Trên topology Cloudflare khác origin với Cloud Run, STOMP rollback chỉ hoạt động
nếu frontend có reverse proxy `/ws` đúng backend. Nếu không có proxy, polling REST
3 giây vẫn là fallback an toàn trong khi rollback revision/frontend.

## 9. Test mã nguồn

```powershell
cd D:\BKQuiz\backend
.\mvnw.cmd verify

cd D:\BKQuiz\frontend
npm test
npm run typecheck
npm run lint
npm run build
```

## Giới hạn còn lại

- Event realtime chỉ là invalidation; lịch sử và dữ liệu chuẩn luôn lấy qua REST.
- Message delivery không được dùng để commit nghiệp vụ hoặc chấm điểm.
- Polling 3 giây vẫn giữ làm degradation path.
- STOMP dependency chưa xóa để local/rollback không bị gián đoạn.

Tham khảo:

- https://ably.com/docs/pub-sub/authentication
- https://ably.com/docs/pub-sub/channels
- https://ably.com/docs/pub-sub/getting-started/javascript
