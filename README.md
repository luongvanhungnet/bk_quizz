# BKQuiz

## Local storage, avatar và Admin

- `STORAGE_PROVIDER=local` là mặc định. File được lưu dưới `LOCAL_STORAGE_ROOT`; PostgreSQL chỉ giữ đường dẫn tương đối, metadata và SHA-256.
- Docker gắn volume `bkquiz-uploads` cho cả API và worker nên restart container không làm mất file. MinIO/S3 vẫn được giữ để tương thích dữ liệu cũ.
- Avatar dùng `POST /api/users/me/avatar`, tối đa 5 MB, chỉ JPEG/PNG/WebP; backend kiểm MIME thực, quét virus và chuẩn hóa ảnh.
- Người dùng đổi `STUDENT`/`TEACHER` tại Profile sau khi nhập lại mật khẩu. Không endpoint nào cho phép tạo hoặc nâng quyền `ADMIN`.
- Admin đăng nhập bằng tài khoản bootstrap và được chuyển tới `/admin` để quản lý user, nội dung/lớp, file, job và audit.

BKQuiz là monorepo gồm frontend React/Vite và backend Spring Boot/PostgreSQL dùng để tạo, quản lý và làm quiz từ tài liệu.

## Cấu trúc

- `frontend/`: React 18, Vite và TypeScript.
- `backend/`: Java 17, Spring Boot 4.1, Spring Security, JPA, Flyway và Spring AI.
- `docker-compose.yml`: PostgreSQL/pgvector, MinIO, ClamAV, API và worker.

## Chạy bằng Docker

1. Sao chép `.env.example` thành `.env` và thay toàn bộ secret mặc định.
2. Chạy `docker compose up --build`.
3. API: `http://localhost:8080/api`, Swagger: `http://localhost:8080/api/docs`.
4. MinIO console: `http://localhost:9001`.

Gemini được tắt mặc định. Để bật, đặt `AI_ENABLED=true`, `AI_CHAT_PROVIDER=google-genai` và `GEMINI_API_KEY`.

Email tài khoản chỉ được gửi qua Resend. Đặt `RESEND_API_KEY` và `APP_MAIL_FROM`; địa chỉ gửi phải
thuộc domain đã xác minh trong Resend. Origin đầu tiên trong `FRONTEND_ORIGINS` được dùng để tạo link
xác minh, đặt lại mật khẩu và hủy xóa tài khoản. Worker sẽ từ chối khởi động nếu thiếu cấu hình Resend.
Khi chạy `backend/mvnw spring-boot:run`, Spring tự đọc `.env` ở thư mục gốc; đặt `WORKER_ENABLED=true`
để process local xử lý hàng đợi email. Docker vẫn tách API (`WORKER_ENABLED=false`) và worker
(`WORKER_ENABLED=true`) thành hai container độc lập.

## Chạy phát triển

Backend:

```powershell
cd backend
$env:DATABASE_MIGRATION_USERNAME="bkquizadmin"
$env:DATABASE_MIGRATION_PASSWORD="<mật khẩu migration local>"
.\mvnw.cmd spring-boot:run
```

Flyway dùng tài khoản migration để thay đổi schema; kết nối JPA/Hikari vẫn dùng
`DATABASE_USERNAME` và `DATABASE_PASSWORD`. Trong Docker, nếu không khai báo tài khoản migration
riêng thì Flyway dùng cùng tài khoản PostgreSQL của service.

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

## Classroom và realtime chat

- Giáo viên tự đăng ký bằng `accountType=TEACHER`, sau đó xác minh email trước khi tạo lớp hoặc chia sẻ tài nguyên.
- REST API nằm dưới `/api/classrooms`; STOMP dùng endpoint `/ws`, topic `/topic/classrooms/{classroomId}` và Bearer token trong frame `CONNECT`.
- Ảnh/file lớp học nằm trong S3/MinIO private. Link truy cập có chữ ký hết hạn sau 5 phút; upload chưa gắn tin nhắn được dọn tự động.
- Frontend cung cấp `/classrooms`, `/classrooms/:classroomId`, `/join-class/:joinCode` và `/quizzes/:quizId/analytics`.
- Migration V7 bổ sung chat, attachment, Topic share và chính sách Assignment mà không sửa V1–V6.

## Kiểm thử

```powershell
cd backend
.\mvnw.cmd verify

cd ..\frontend
npm run lint
npm run typecheck
npm test -- --run
npm run build
```

## Bootstrap admin

Khởi động backend một lần với `ADMIN_BOOTSTRAP_ENABLED=true` cùng `ADMIN_BOOTSTRAP_EMAIL`, `ADMIN_BOOTSTRAP_USERNAME` và `ADMIN_BOOTSTRAP_PASSWORD`. Lệnh idempotent: tài khoản hiện có sẽ được xác minh và nâng thành `ADMIN`. Tắt cờ ngay sau lần chạy.

## Bảo mật

- Access token JWT ngắn hạn; refresh token opaque được hash trong DB và đặt trong cookie HttpOnly.
- Mật khẩu dùng BCrypt strength 12; API không trả password/token hash.
- Email chưa xác minh không được gọi AI, publish hoặc tham gia lớp.
- Tệp nguồn nằm trong bucket private; chỉ cấp URL tải có thời hạn sau khi kiểm tra quyền.
- Mọi lỗi hướng người dùng và validation message đều dùng tiếng Việt; log không ghi secret/token.
