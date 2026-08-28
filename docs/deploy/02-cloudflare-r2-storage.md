# Stage 2 — Cloudflare R2 object storage

## Kết quả triển khai

Spring Boot dùng Cloudflare R2 thông qua S3-compatible API cho:

- tài liệu người dùng (`sources/...`);
- file và ảnh trong lớp học (`classrooms/...`);
- avatar (`avatars/{userId}/...`).

Bucket phải để **private**. Trình duyệt không nhận Access Key hoặc Secret Key. Tài liệu và avatar được đọc qua Spring Boot; file lớp học được cấp presigned GET URL có thời hạn.

Local development không đổi: `STORAGE_PROVIDER=local` tiếp tục ghi vào `./data/uploads`; Docker profile S3 vẫn có thể dùng MinIO.

## 1. Tạo bucket và credential R2

1. Mở Cloudflare Dashboard → **Storage & databases** → **R2**.
2. Tạo bucket, ví dụ `bkquiz-production`. Không bật public access.
3. Chọn **Manage R2 API Tokens** → tạo token **Object Read & Write**.
4. Giới hạn token vào đúng bucket `bkquiz-production`.
5. Lưu một lần hai giá trị `Access Key ID` và `Secret Access Key` vào password manager.
6. Ghi lại Account ID. Endpoint có dạng:

   ```text
   https://<ACCOUNT_ID>.r2.cloudflarestorage.com
   ```

R2 dùng region `auto`. Không dùng Global API Key của tài khoản Cloudflare.

## 2. Lưu secret trong Google Secret Manager

Khuyến nghị tạo hai secret bằng Google Cloud Console để giá trị không xuất hiện trong shell history:

- `bkquiz-r2-access-key`
- `bkquiz-r2-secret-key`

Cloud Run service account phải có role `Secret Manager Secret Accessor` cho hai secret. Khi gắn secret dưới dạng environment variable, nên ghim version cụ thể (ví dụ `1`) thay vì `latest` để rollback revision có tính xác định.

## 3. Cấu hình Cloud Run

Các biến không nhạy cảm:

```text
STORAGE_PROVIDER=s3
S3_ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
S3_REGION=auto
S3_BUCKET=bkquiz-production
S3_PATH_STYLE=true
LOCAL_STORAGE_TEMP=/tmp/bkquiz/tmp
```

Hai biến bí mật:

```text
S3_ACCESS_KEY=<Secret Manager: bkquiz-r2-access-key:1>
S3_SECRET_KEY=<Secret Manager: bkquiz-r2-secret-key:1>
```

Ví dụ cập nhật service đã tồn tại bằng PowerShell:

```powershell
$PROJECT_ID = "your-project-id"
$REGION = "asia-southeast1"
$SERVICE = "bkquiz-api"
$ACCOUNT_ID = "your-cloudflare-account-id"
$BUCKET = "bkquiz-production"

gcloud config set project $PROJECT_ID

gcloud run services update $SERVICE `
  --region $REGION `
  --update-env-vars "STORAGE_PROVIDER=s3,S3_ENDPOINT=https://$ACCOUNT_ID.r2.cloudflarestorage.com,S3_REGION=auto,S3_BUCKET=$BUCKET,S3_PATH_STYLE=true,LOCAL_STORAGE_TEMP=/tmp/bkquiz/tmp" `
  --update-secrets "S3_ACCESS_KEY=bkquiz-r2-access-key:1,S3_SECRET_KEY=bkquiz-r2-secret-key:1"
```

Nếu service account chưa có quyền đọc secret:

```powershell
$SERVICE_ACCOUNT = "bkquiz-cloud-run@$PROJECT_ID.iam.gserviceaccount.com"

gcloud secrets add-iam-policy-binding bkquiz-r2-access-key `
  --member "serviceAccount:$SERVICE_ACCOUNT" `
  --role "roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding bkquiz-r2-secret-key `
  --member "serviceAccount:$SERVICE_ACCOUNT" `
  --role "roles/secretmanager.secretAccessor"
```

Sau khi build image chứa thay đổi Stage 2, deploy image đó như revision mới. Production sẽ fail-fast nếu storage vẫn là local, endpoint không phải HTTPS R2, region khác `auto`, hoặc còn credential mẫu.

## 4. CORS của bucket

Luồng hiện tại upload qua Spring Boot nên không cần CORS cho upload. File lớp học có thể được trình duyệt tải qua presigned GET URL, vì vậy thêm policy chỉ cho frontend production:

```json
[
  {
    "AllowedOrigins": ["https://your-frontend.pages.dev"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["ETag", "Content-Length", "Content-Type"],
    "MaxAgeSeconds": 3600
  }
]
```

Thay origin bằng domain Cloudflare Pages/custom domain thật, không có dấu `/` cuối. Vào bucket → **Settings** → **CORS Policy** để lưu. Không thêm `PUT` cho đến khi BKQuiz triển khai direct upload bằng presigned URL.

## 5. Kiểm tra sau deploy

1. Kiểm tra revision sẵn sàng:

   ```powershell
   $BACKEND_URL = "https://your-cloud-run-service.run.app"
   curl.exe "$BACKEND_URL/actuator/health/readiness"
   curl.exe "$BACKEND_URL/actuator/health"
   ```

2. Đăng nhập từ frontend production.
3. Upload một avatar, tải một tài liệu nhỏ và gửi một file trong lớp học.
4. Trong R2 Object Browser, xác nhận xuất hiện các prefix `avatars/`, `sources/`, `classrooms/`.
5. Reload trang và mở lại avatar/tài liệu/file để xác nhận dữ liệu không phụ thuộc instance Cloud Run cũ.
6. Kiểm tra log Cloud Run không có `SignatureDoesNotMatch`, `AccessDenied`, `NoSuchBucket` hoặc `AVATAR_STORAGE_FAILED`.

## 6. Chẩn đoán lỗi thường gặp

| Lỗi | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `SignatureDoesNotMatch` | Endpoint, region hoặc cặp key không đồng bộ | Dùng endpoint account R2, `S3_REGION=auto`, tạo lại token đúng bucket |
| `AccessDenied` | Token chỉ đọc hoặc không được cấp cho bucket | Tạo token Object Read & Write, scope đúng bucket |
| `NoSuchBucket` | Sai `S3_BUCKET` hoặc bucket thuộc account khác | Kiểm tra chính xác tên bucket và Account ID |
| Browser chặn CORS | Origin/method không khớp policy | Dùng origin chính xác, thêm `GET` và `HEAD` |
| Service không start | Startup validator phát hiện cấu hình local/mẫu | Xem log revision và kiểm tra đủ bảy biến storage |
| File lớn thất bại trước Spring | Cloud Run HTTP/1 giới hạn request 32 MiB | Tạm giữ file dưới khoảng 30 MiB; bước sau nên dùng presigned direct upload |

## 7. Dữ liệu local hiện có

Thay đổi này tự động chuyển **upload mới** sang R2 nhưng không thể tự lấy file nằm trên ổ đĩa của revision Cloud Run cũ. Trước khi chuyển traffic:

- nếu chưa có dữ liệu production: bật R2 trực tiếp;
- nếu có file local trên máy phát triển/VM: giữ bản sao thư mục upload và thực hiện migration có kiểm kê riêng;
- không sửa hàng loạt `stored_files.provider` từ `LOCAL` sang `S3` khi object chưa được upload với đúng key;
- giữ revision cũ cho tới khi smoke test R2 hoàn tất.

## 8. Rollback

Rollback an toàn nhất là đưa traffic về revision Cloud Run trước:

```powershell
gcloud run revisions list --service $SERVICE --region $REGION
gcloud run services update-traffic $SERVICE --region $REGION --to-revisions "PREVIOUS_REVISION=100"
```

Không xóa bucket hoặc token R2 khi rollback; revision mới có thể đã ghi object hợp lệ. Sau khi sửa cấu hình, deploy revision mới và smoke test lại.

## Lưu ý vận hành

- Token R2 tuyệt đối không đặt trong frontend, Git, Docker image hoặc file `.env` đã commit.
- Presigned URL là bearer token; chỉ cấp thời hạn ngắn và không ghi toàn bộ URL vào log.
- Worker Spring hiện tại cần `WORKER_ENABLED=true` để đẩy tài liệu sang RAG. Trước Stage Pub/Sub, nếu chạy worker polling trên Cloud Run, cần ít nhất một instance và instance-based billing để CPU hoạt động ngoài request.
- Upload hiện vẫn đi qua Cloud Run. Direct upload sang R2 là bước tối ưu riêng vì cần endpoint cấp presigned PUT, CORS `PUT` và quy trình xác nhận upload.

## Tài liệu chính thức

- Cloudflare R2 S3 API: https://developers.cloudflare.com/r2/get-started/s3/
- Cloudflare R2 presigned URLs: https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- Cloudflare R2 CORS: https://developers.cloudflare.com/r2/buckets/cors/
- Cloud Run Secret Manager: https://cloud.google.com/run/docs/configuring/services/secrets
- Cloud Run quotas: https://cloud.google.com/run/quotas
