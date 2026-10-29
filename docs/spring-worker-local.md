# Spring worker local

Spring worker là JobWorker chạy trong cùng ứng dụng Spring Boot. Nó poll bảng jobs trong PostgreSQL, heartbeat vào job_worker_heartbeats, nhận job bằng cơ chế claim của ứng dụng. Đây là worker khác với Celery worker của RAG.

## Cách mặc định: một process API và worker

```powershell
cd D:\BKQuiz
.\backend\run-local.ps1
```

Launcher nạp backend/.env.local, bật WORKER_ENABLED=true, chạy Spring Boot trực tiếp bằng Maven Wrapper. Cấu hình local hiện dùng cổng 8080, poll 2 giây, heartbeat 10 giây. Không cần container hoặc process Spring thứ hai. Nếu backend đã chạy tại 8080, dùng process đó hoặc dừng nó trước khi chạy launcher.

## Tùy chọn: tách API và worker

Terminal API:

```powershell
D:\BKQuiz\backend\run-local.ps1 -Mode Api
```

Terminal worker:

```powershell
D:\BKQuiz\backend\run-local.ps1 -Mode Worker
```

Process worker dùng cổng 8081 cho health HTTP; API dùng 8080. Hai process cùng nạp backend/.env.local và có working directory là backend, nên dùng chung PostgreSQL và cùng thư mục storage mặc định backend/data/uploads, backend/data/tmp. Nếu cấu hình LOCAL_STORAGE_ROOT/LOCAL_STORAGE_TEMP riêng, cả hai phải trỏ cùng nơi. Mode chỉ ghi đè biến môi trường của terminal, không sửa file .env.local.

## Phụ thuộc

- PostgreSQL local đã migrate, Redis local nếu dùng các tính năng cần cache/rate limit.
- RAG API 8090 cùng Celery worker/beat, Qdrant cho indexing/sinh quiz.
- Resend API token và APP_MAIL_FROM hợp lệ: worker kiểm tra sự hiện diện cấu hình lúc startup. Kiểm tra này không chứng minh gửi email thành công.

Launcher không tạo Windows service hoặc scheduled task. Sau reboot cần chạy lại. Dừng bằng Ctrl+C.

## Kết quả kiểm tra 29/10/2026

- Worker chạy chung API 8080 cập nhật heartbeat PostgreSQL bình thường.
- Dùng teacher@bkquiz.test tạo topic `Local Spring worker smoke test` và nguồn văn bản `spring-worker-smoke.txt` qua API thật; giữ fixture này để người dùng xem trong giao diện.
- SOURCE_INGESTION và RAG_INDEX_POLL đều SUCCEEDED, attempts=1, không error_code. RAG/Celery ghi index Qdrant rồi Spring đồng bộ 2 chunk về PostgreSQL; source READY, progress=100 sau khoảng 10,69 giây tính từ lúc bắt đầu poll.
- Launcher `-Mode Worker` khởi động được process 8081, readiness trả 200/UP. Đã dừng process kiểm thử riêng; giữ process API+worker 8080 chạy.
- Bằng chứng: `D:/BKQuiz/tmp/spring-worker-local-validation.json`; log launcher riêng: `D:/BKQuiz/tmp/spring-worker-separate-smoke.log`.
- Chưa thử gửi email Resend, sinh quiz/chat bằng AI, tình huống crash/reclaim hoặc tải dài hạn trong lượt kiểm tra này.
