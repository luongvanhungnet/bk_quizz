# Cấu hình Resend cho email xác thực BKQuiz

## Nguyên nhân lỗi hiện tại

Resend đã trả HTTP `400` với thông báo `API key is invalid`. Request
`POST /api/auth/verify-email/resend` trả `200` chỉ có nghĩa là backend đã nhận
yêu cầu và đưa email vào job queue. Việc gọi Resend diễn ra bất đồng bộ trong
`AuthMailJobHandler`, nên lỗi credential xuất hiện sau đó ở worker.

Header Bearer và payload gửi email trong backend đã đúng. Cần thu hồi key sai,
tạo key mới trong đúng Resend account, lưu thành phiên bản Secret Manager mới
và tạo Cloud Run revision nhận secret đó. Biến production chuẩn mới là
`RESEND_API_TOKEN`; cấu hình vẫn đọc `RESEND_API_KEY` cũ làm fallback trong một
giai đoạn chuyển tiếp.

Nếu script preflight gửi thành công nhưng UI vẫn lỗi với
`HttpConnectTimeoutException`, credential và sender đã hợp lệ; lỗi nằm ở kết
nối outbound từ Cloud Run tới `api.resend.com`. Backend production dùng IPv4,
HTTP/1.1, timeout kết nối 30 giây, timeout đọc 45 giây và retry job sau tối
thiểu 30 giây. Các giá trị có thể cấu hình bằng:

```text
RESEND_CONNECT_TIMEOUT=30s
RESEND_READ_TIMEOUT=45s
RESEND_NETWORK_RETRY_DELAY=30s
```

## 1. Chuẩn bị trên Resend

1. Mở Resend Dashboard → **API Keys**.
2. Thu hồi key đang lỗi và tạo key mới có quyền **Sending access**.
3. Mở **Domains**, thêm `luongvanhungnet.xyz` hoặc một sending subdomain.
4. Thêm đầy đủ DNS SPF/DKIM tại Cloudflare và chờ trạng thái `Verified`.
5. Nếu xác minh subdomain, ví dụ `mail.luongvanhungnet.xyz`, phải đổi sender
   thành `BKQuiz <noreply@mail.luongvanhungnet.xyz>` chính xác.

Không ghi key vào `.env`, command history, Git hoặc tài liệu.

## 2. Xoay key và cấu hình Cloud Run

Script sẽ yêu cầu nhập key dưới dạng SecureString, có thể gửi một email
preflight trước khi thay Cloud Run, tạo Secret Manager version mới, cấp quyền
cho runtime service account và pin revision vào đúng version mới.

```powershell
cd D:\BKQuiz

$PROJECT_ID = 'bkquiz-stg-235740'
$REGION = 'asia-southeast1'
$TEST_RECIPIENT = '<email-cua-ban>'

.\backend\deploy\configure-resend.ps1 `
  -ProjectId $PROJECT_ID `
  -Region $REGION `
  -Sender 'BKQuiz <noreply@luongvanhungnet.xyz>' `
  -TestRecipient $TEST_RECIPIENT `
  -WhatIf

.\backend\deploy\configure-resend.ps1 `
  -ProjectId $PROJECT_ID `
  -Region $REGION `
  -Sender 'BKQuiz <noreply@luongvanhungnet.xyz>' `
  -TestRecipient $TEST_RECIPIENT
```

Khi được hỏi, dán key mới bắt đầu bằng `re_`. Key không được in ra console.
Nếu preflight bị Resend từ chối, script dừng trước khi cập nhật Cloud Run.

Kiểm tra binding mà không đọc secret:

```powershell
.\backend\deploy\configure-resend.ps1 `
  -ProjectId $PROJECT_ID `
  -Region $REGION `
  -ValidateOnly
```

`configure-cloud-run.ps1` cũng đã được đổi để bind `RESEND_API_TOKEN` vào secret
chuẩn `bkquiz-resend-api-key:latest`. Biến `RESEND_API_KEY` cũ có thể giữ trong
revision để rollback nhưng sẽ không được chọn khi token mới tồn tại.

## 3. Deploy backend có mã phân loại lỗi mới

Build image mới và cập nhật Cloud Run. Pipeline Giai đoạn 10 có thể thực hiện
việc này; không cần bật Flyway vì thay đổi này không có migration.

```powershell
gh workflow run release.yml `
  --repo deepdev-hub/bk_quizz `
  --ref main `
  -f environment=staging `
  -f run_migrations=false `
  -f deploy_frontend=false
```

Nếu chưa dùng pipeline, build và update thủ công:

```powershell
$REPOSITORY = 'bkquiz'
$TAG = "resend-$(Get-Date -Format yyyyMMdd-HHmmss)"
$IMAGE = "${REGION}-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/backend:$TAG"

gcloud builds submit D:\BKQuiz\backend --tag $IMAGE
gcloud run services update bkquiz-api `
  --project=$PROJECT_ID --region=$REGION --image=$IMAGE
```

## 4. Smoke test

1. Đăng ký bằng một email mới hoặc nhấn gửi lại email xác minh.
2. HTTP `200` từ endpoint queue là kết quả mong đợi.
3. Chờ worker xử lý và kiểm tra hộp thư/spam.
4. Kiểm tra Cloud Run log:

```powershell
gcloud logging read `
  'resource.type="cloud_run_revision" AND resource.labels.service_name="bkquiz-api" AND textPayload:"AUTH_EMAIL"' `
  --project=$PROJECT_ID --limit=50 --freshness=30m
```

Nếu còn lỗi, job giờ giữ mã cụ thể:

- `RESEND_AUTHENTICATION_FAILED`: key sai hoặc đã thu hồi;
- `RESEND_SENDER_NOT_VERIFIED`: domain trong `APP_MAIL_FROM` chưa verified;
- `RESEND_SENDER_INVALID`: sender sai định dạng;
- `RESEND_REQUEST_REJECTED`: recipient hoặc payload bị từ chối;
- `RESEND_CONNECTION_TIMEOUT`: Cloud Run không kết nối Resend trong thời hạn;
- `RESEND_CONNECTION_FAILED`: lỗi DNS/TLS/kết nối outbound khác;
- lỗi `429/5xx/timeout` tiếp tục được retry với cùng idempotency key, nên không
  tạo email trùng nếu Resend đã nhận request trước khi kết nối bị ngắt.

Không dán access token, refresh token hoặc API key vào log hỗ trợ.
