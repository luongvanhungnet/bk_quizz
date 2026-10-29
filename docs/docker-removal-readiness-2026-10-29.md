# Kiểm tra khả năng vận hành khi bỏ Docker

Ngày kiểm tra: 29/10/2026. Phạm vi: mã nguồn, cấu hình hiện có và kiểm thử trực tiếp trên Windows; chưa xóa Docker, chưa đổi database hoặc triển khai dịch vụ.

## Kết luận

Kiến trúc cho phép chạy không cần Docker, nhưng cấu hình hiện tại chưa đủ để xác nhận toàn bộ ứng dụng vận hành. Xóa Dockerfile/Compose ngay sẽ làm hỏng các bước CI/phát hành còn tham chiếu chúng. Chạy ứng dụng trực tiếp và loại bỏ hoàn toàn container khỏi quy trình phát hành là hai phạm vi cần xử lý riêng.

## Phát hiện thực tế

| Hạng mục | Bằng chứng | Tác động và việc cần làm |
|---|---|---|
| PostgreSQL | Windows service `postgresql-x64-17` đang chạy, cổng 5432; `backend/.env.local` trỏ cổng 5433 và kết nối bị từ chối | Chọn đúng instance/database và tài khoản runtime/migration. Không chỉ đổi cổng khi chưa xác định dữ liệu đích. Kiểm tra Flyway và các extension pgcrypto, citext, pg_trgm. |
| Địa chỉ RAG | `.env` gốc trỏ `http://rag-api:8000`, tên máy không phân giải ngoài Compose | Đổi cấu hình chạy trực tiếp sang `http://127.0.0.1:8090`; đồng bộ secret nội bộ hai service. |
| Redis | `.env` RAG trỏ localhost:6379; không có listener và kết nối bị từ chối | Chế độ local mặc định dùng Celery cần Redis chạy ngoài Docker hoặc endpoint Redis được cấp sẵn. Lock local không thay thế broker Celery. |
| Qdrant | Không có listener local 6333 | Chỉ cần nếu chọn backend qdrant. RAG hỗ trợ FAISS cho development; phải xác định backend thực tế và giữ dữ liệu index tương ứng. |
| Spring worker | `WORKER_ENABLED=true` trong cấu hình local | Cần cấu hình Resend hợp lệ để khởi động worker; nếu tách worker, phải chạy process riêng và dùng chung thư mục lưu file. |
| Tệp và model | Compose dùng named volumes; Dockerfile RAG tải model ONNX trong lúc build | Xác định dữ liệu thực trong volume trước khi gỡ Docker, sao lưu/khôi phục DB, uploads, RAG metadata/index và model nếu đang dùng. Kiểm tra đường dẫn native, quyền ghi và model ONNX. |
| MinIO/ClamAV | Storage local được hỗ trợ; ClamAV local đang tắt | MinIO không bắt buộc với storage local, nhưng dữ liệu S3 cũ vẫn cần nơi phục vụ. Nếu bật ClamAV, cần daemon và địa chỉ truy cập hợp lệ. |
| Frontend production | `npm run build` thất bại vì `/api` chưa đáp ứng hợp đồng cấu hình production | Cấu hình URL API HTTPS hoặc reverse proxy thật cùng `VITE_API_SAME_ORIGIN_PROXY=true`; Vite dev proxy không phục vụ bản build production. |
| Kiểm thử backend | `mvnw.cmd test -q`: 181 test, 0 lỗi/thất bại, 24 skipped; Testcontainers báo thiếu Docker | 157 test đạt chưa chứng minh migration và API tích hợp chạy được. Cần database test riêng ngoài Docker và sửa harness đang dùng PostgreSQLContainer. |
| CI RAG | `.github/workflows/rag-ci.yml` gọi docker build và docker compose | Thay bằng runtime Python và các dịch vụ test ngoài Docker trước khi xóa các file liên quan. |
| Phát hành | `.github/workflows/release.yml` build image bằng Cloud Build; có migration image riêng | Xóa Dockerfile làm quy trình hiện tại mất đầu vào build. Nếu giữ Cloud Run, cần đường build image khác; nếu bỏ toàn bộ container, phải thiết kế đích phát hành và quản lý process mới. |
| Hướng dẫn local | `docs/deploy/11-cach-chay-du-an.md` mục 1.2 vẫn dùng Compose cho hạ tầng | Viết lại phần cài/chạy PostgreSQL, Redis và Qdrant tùy cấu hình; bổ sung startup, shutdown, log, restart và backup. |

## Thứ tự chuyển đổi đề xuất

Kết quả kiểm thử bổ sung:

- Frontend: TypeScript đạt; Vitest đạt 36 file / 94 test. Build production thất bại do cấu hình URL API như bảng trên.
- RAG: lần chạy đầu dừng vì `GEMINI_CONFIG_CONFLICT` giữa biến môi trường process và `.env`. Sau khi bỏ biến `GEMINI_API_KEY` cũ **chỉ trong process kiểm thử**, 197 test đạt, 4 test bị loại bởi bộ lọc `not integration and not evaluation`. Không sửa secret trong file hoặc môi trường hệ thống. Khi chạy thực tế, dùng launcher nạp `.env` hoặc xử lý xung đột tương tự.
- Không có Spring/RAG API đang lắng nghe trên các cổng local đã kiểm tra. Chưa chạy smoke test nghiệp vụ với database và broker thật.

1. Kiểm kê và sao lưu dữ liệu đang nằm trong Docker volumes; xác định database chính xác cần dùng.
2. Chuẩn hóa cấu hình native: backend 8080, RAG 8090, frontend 5173; database đúng cổng; Redis truy cập được. Giữ cùng giá trị secret nội bộ và cấu hình mail.
3. Chạy migration trên database đích đã xác định, chuẩn bị model và các thư mục lưu trữ bền vững.
4. Chạy Spring API/worker, RAG API, Celery worker/beat và frontend bằng launcher sẵn có. Windows Celery launcher đã dùng pool solo, concurrency 1.
5. Kiểm tra readiness, đăng ký/xác minh/đăng nhập, upload/download, indexing RAG, sinh quiz, email job và realtime; kiểm tra sau restart.
6. Chuyển integration tests, CI và quy trình release sang phương án đã chọn. Chỉ xóa file Docker sau khi các bước thay thế chạy đạt.

Chưa xác nhận end-to-end, hiệu năng hoặc khả năng bảo toàn dữ liệu sau chuyển đổi. Không dùng kết quả unit test để thay thế các kiểm tra này.
