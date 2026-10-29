# Qdrant local qua Ubuntu WSL

Qdrant 1.19.0 được cài từ gói Debian chính thức của qdrant/qdrant, đã đối chiếu SHA-256 với digest GitHub release. Phiên bản khớp cấu hình Compose trước đây và qdrant-client 1.19.0 của RAG. Không dùng Docker, không import dữ liệu cũ.

- HTTP: `http://127.0.0.1:6333`, gRPC: `127.0.0.1:6334`.
- Dashboard: `http://127.0.0.1:6333/dashboard`.
- Dữ liệu: `/var/lib/qdrant/storage` trong Ubuntu, snapshots: `/var/lib/qdrant/snapshots`.
- Service: `qdrant.service`, chạy bằng user hệ thống qdrant; config `/etc/qdrant/config.yaml`.
- Chỉ bind loopback, không đặt API key cho môi trường development local. Telemetry tắt.

Khởi động sau khi restart Windows hoặc tắt WSL:

```powershell
cd D:\BKQuiz
.\infra\qdrant\start-local.ps1
```

Launcher tái sử dụng launcher Redis để giữ Ubuntu WSL chạy, rồi khởi động và kiểm tra Qdrant. Systemd service được enable khi Ubuntu boot; không tạo Windows scheduled task.

Kiểm tra và dừng:

```powershell
Invoke-RestMethod http://127.0.0.1:6333/readyz
wsl -d Ubuntu -u root -- systemctl status qdrant --no-pager
wsl -d Ubuntu -u root -- systemctl stop qdrant
```

RAG `.env` đã chọn:

```dotenv
VECTOR_STORE_BACKEND=qdrant
QDRANT_URL=http://127.0.0.1:6333
QDRANT_API_KEY=
QDRANT_COLLECTION=bkquiz_chunks_local
QDRANT_TIMEOUT_SECONDS=15
```

RAG tự tạo collection 384 chiều tương ứng model embedding hiện tại và payload indexes `_namespace`, `_version`, `documentId`, `ownerId`. Không cần tạo collection bằng tay.

RAG API, worker và beat cần chạy trong các terminal riêng sau khi bật hạ tầng:

```powershell
cd D:\BKQuiz\rag-service
.\scripts\run_local.ps1 -Service api
# Terminal khác: .\scripts\run_local.ps1 -Service worker
# Terminal khác: .\scripts\run_local.ps1 -Service beat
```

Lần kiểm tra 29/10/2026 đã khởi động cả ba process: `/health/ready` trả 200/UP với database, cacheRedis, celeryWorker, storage, vectorStore, embedding và gemini đều UP; backend `/actuator/health` cũng trả 200/UP. Trạng thái gemini ở readiness không chứng minh sinh câu trả lời thực tế đã được kiểm thử. Worker xử lý được các maintenance task do beat gửi.

Đã kiểm tra bằng SDK của ứng dụng: tạo collection tạm, tạo payload index, upsert hai vector, tìm kiếm có owner filter, restart Qdrant rồi đọc lại đủ hai point. Collection tạm đã xóa; collection ứng dụng bắt đầu rỗng.

Bằng chứng: `D:/BKQuiz/tmp/qdrant-local-validation.json`. Các kiểm tra này chưa thay thế bài kiểm tra upload/index tài liệu và sinh câu trả lời end-to-end.
