# Redis local qua Ubuntu WSL

Redis đã cài bằng Ubuntu APT, chạy bằng systemd, bind loopback, protected-mode bật, AOF bật. Dữ liệu ở `/var/lib/redis` trong Ubuntu WSL; không dùng Docker volumes.

Từ PowerShell, chạy sau khi khởi động Windows hoặc sau khi tắt WSL:

```powershell
cd D:\BKQuiz
.\infra\redis\start-local.ps1
```

Launcher khởi động Redis và giữ WSL chạy bằng một process `sleep infinity` ẩn. PID của process WSL được lưu trong `tmp/redis-wsl-keeper.pid`; chạy lại launcher sẽ tái sử dụng process còn sống. Không cài startup task cho Windows.

Kiểm tra:

```powershell
wsl -d Ubuntu -u root -- redis-cli ping
```

Kết quả mong đợi: `PONG`. Backend và RAG dùng `redis://127.0.0.1:6379/0`; RAG cache dùng cùng địa chỉ và provider redis. Restart các process RAG đã chạy trước lúc đổi cấu hình để chúng nạp lại `.env`.

Dừng Redis:

```powershell
wsl -d Ubuntu -u root -- systemctl stop redis-server
```

Đây là broker/cache local. Chưa chứng minh Celery worker đang xử lý job chỉ bằng kết quả kết nối Redis.
