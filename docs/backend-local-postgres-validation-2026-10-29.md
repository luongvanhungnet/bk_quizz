# Kiểm tra backend với PostgreSQL local — 29/10/2026

## Môi trường và thay đổi

- Spring Boot chạy trực tiếp bằng Maven Wrapper, dùng `backend/.env.local`.
- PostgreSQL 17.4 tại `localhost:5432/bkquiz`; runtime và Flyway dùng tài khoản `postgres` hiện có.
- Khởi động thật đã validate 28 migration và nâng schema từ V12 lên V28; không có migration thất bại. Hibernate validate schema thành công, Hikari tạo được connection pool.
- Không phục hồi dữ liệu Docker, không xóa các tài khoản đã tồn tại.

## Tài khoản mẫu

Tạo 7 tài khoản local, email thuộc miền `.test`: STUDENT, TEACHER, SUPPORT, ANALYST, MODERATOR, ADMIN và OWNER. Tất cả active, có email_verified_at và preferences; password được hash BCrypt cost 12, mỗi tài khoản có mật khẩu ngẫu nhiên riêng.

Thông tin đăng nhập nằm ở `D:/BKQuiz/tmp/local-test-accounts.md` và JSON cùng tên. Thư mục tmp bị Git ignore; mật khẩu không được đưa vào tài liệu theo dõi trong Git.

Seed chỉ tạo baseline USER. OWNER được cấp bằng AdminBootstrapRunner của ứng dụng; SUPPORT/ANALYST/MODERATOR/ADMIN được OWNER cấp qua REST API, có audit/outbox theo logic dự án. Không gửi email xác minh cho tài khoản mẫu.

## Lỗi phát hiện và sửa

Bootstrap OWNER thất bại trên PostgreSQL thật vì `JdbcTemplate.update` truyền trực tiếp `java.time.Instant`. Đổi tham số sang `java.sql.Timestamp.from(Instant.now())`.

Kiểm thử hồi quy chứng minh lỗi trước sửa (1/4 test thất bại), sau sửa 4/4 đạt. Bootstrap thật hoàn tất và lưu trạng thái INITIAL_OWNER. Bộ test backend sau sửa: 182 test, 0 failure/error, 24 skipped do thiếu Docker; 158 test thực sự chạy đạt.

## Kiểm tra API và phạm vi

- Login và `/api/auth/me` đạt cho cả 7 tài khoản; xác nhận đúng ID và emailVerified.
- `/api/admin/users`: SUPPORT, MODERATOR, ADMIN, OWNER nhận 200; STUDENT, TEACHER, ANALYST nhận 403.
- `/api/admin/summary`: ANALYST, ADMIN, OWNER nhận 200; STUDENT, TEACHER, SUPPORT, MODERATOR nhận 403.
- `/api/health` trả 200; `/actuator/health/readiness` trả 200/UP.
- `/actuator/health` trả 503/DOWN vì Redis localhost:6379 chưa chạy; log RAG cũng báo không kết nối được API 8090. Kết quả database không đồng nghĩa toàn hệ thống đã sẵn sàng.
- Lượt kiểm tra hàng loạt ban đầu chạm giới hạn login 5 lần/15 phút. Tạm dùng biến môi trường `BKQUIZ_RATE_LIMIT_ENABLED=false` trong tiến trình kiểm thử; không sửa cấu hình trên đĩa.
- Kiểm tra `/api/auth/me` qua backend/JPA: 120 request với 8 luồng đồng thời, tiếp theo 60 request cách nhau khoảng 1 giây. Tổng 180/180 đạt, không lỗi; thời gian đợt đo 60,65 giây, median 10,07 ms, p95 19,37 ms, max 27,94 ms. PostgreSQL ghi nhận 5 kết nối JDBC idle sau lượt chạy, không có transaction treo trong snapshot đó.
- Sau đo đã restart backend về cấu hình gốc: readiness UP; STUDENT, TEACHER, OWNER đăng nhập/đọc hồ sơ lại thành công; OWNER vẫn truy cập được quản trị. Header login xác nhận giới hạn mặc định 5 đã bật lại. Backend được giữ chạy tại cổng 8080; tiến trình bootstrap cổng 8082 đã dừng, bootstrap không được bật trong cấu hình lưu trên đĩa.

Chi tiết kết quả và số đo đợt kiểm tra API nằm ở `D:/BKQuiz/tmp/backend-local-validation.json`; log startup/migration ở `D:/BKQuiz/tmp/backend-local-validation.log`, log kiểm tra tải ở `D:/BKQuiz/tmp/backend-local-stability.log`.

Đây là kiểm tra chức năng và tải ngắn trên máy local, không phải chứng nhận độ ổn định dài hạn hoặc benchmark production. Kiểm thử tích hợp Docker chưa chạy trong đợt này.
