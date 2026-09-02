# Giai đoạn 3 — chuyển database RAG từ SQLite sang Neon PostgreSQL

## Phạm vi đã triển khai

Giai đoạn này chỉ chuyển metadata RAG (`documents`, `indexing_jobs`,
`math_extractions`, `audit_events`) sang PostgreSQL. FAISS, file upload,
Redis/Celery và thư mục model vẫn giữ nguyên. Vì vậy chưa nên scale RAG API hoặc
worker ra nhiều instance Cloud Run trước khi hoàn tất R2 và Qdrant.

Runtime hỗ trợ:

- local/test: `sqlite:///data/rag.db`;
- production: `postgresql+psycopg://...?...sslmode=require`;
- RAG dùng SQLAlchemy QueuePool, mặc định 4 kết nối và 2 overflow cho mỗi process;
- API, Celery worker và Celery beat phải trỏ tới cùng một Neon database.

Docker image không còn tự chạy Alembic. Local Docker Compose vẫn chạy Alembic
trước Uvicorn; production phải chạy migration đúng một lần bằng URL Neon direct.

## 1. Tạo database và hai connection string trong Neon

Tạo database riêng, ví dụ `bkquiz_rag`, và role riêng chỉ cho RAG. Trong Neon
Console, nút **Connect** cung cấp hai URL:

1. **Direct connection** (hostname không có `-pooler`): chỉ dùng cho Alembic và
   script chuyển dữ liệu.
2. **Pooled connection** (hostname có `-pooler`): dùng cho FastAPI và Celery.

Đổi scheme của URL Neon từ `postgresql://` thành
`postgresql+psycopg://`. Giữ `sslmode=require` (và `channel_binding=require` nếu
Neon cung cấp). Không commit hai URL này vào Git.

Ví dụ hình dạng, không phải credential thật:

```text
postgresql+psycopg://rag_user:PASSWORD@ep-example-pooler.ap-southeast-1.aws.neon.tech/bkquiz_rag?sslmode=require
postgresql+psycopg://rag_user:PASSWORD@ep-example.ap-southeast-1.aws.neon.tech/bkquiz_rag?sslmode=require
```

Nếu password có ký tự `@`, `:`, `/`, `?` hoặc `#`, phải URL-encode password.

## 2. Cài dependency và chạy schema migration một lần

```powershell
cd D:\BKQuiz\rag-service
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Dán URL direct vào biến của phiên PowerShell hiện tại.
$env:DATABASE_URL = '<NEON_DIRECT_SQLALCHEMY_URL>'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

Với mã nguồn hiện tại, kết quả cuối phải là `0007_qdrant_snapshots (head)`.
Không đưa lệnh Alembic vào
startup của nhiều Cloud Run instance: các instance có thể tranh migration.

## 3A. Hệ thống mới, không cần giữ SQLite cũ

Bỏ qua bước sao chép dữ liệu. Cấu hình runtime bằng URL pooled ở mục 4.

## 3B. Chuyển dữ liệu SQLite hiện có

1. Dừng RAG API, worker và beat để SQLite không còn ghi mới.
2. Sao lưu `rag.db` sau khi dừng. Nếu dùng Docker volume, export/copy database
   từ volume; không chỉ copy file chính khi WAL vẫn đang hoạt động.
3. Neon target phải vừa migration và chưa có dữ liệu trong bốn bảng RAG.
4. Chạy script bằng URL direct:

```powershell
cd D:\BKQuiz\rag-service
$env:RAG_MIGRATION_SOURCE_URL = 'sqlite:///D:/BKQuiz/rag-service/data/rag.db'
$env:RAG_MIGRATION_TARGET_URL = '<NEON_DIRECT_SQLALCHEMY_URL>'

# Nếu SQLite cũ chưa ở head, nâng schema source trước khi sao chép.
$env:DATABASE_URL = $env:RAG_MIGRATION_SOURCE_URL
.\.venv\Scripts\python.exe -m alembic upgrade head

.\.venv\Scripts\python.exe scripts\migrate_sqlite_to_postgres.py --dry-run
.\.venv\Scripts\python.exe scripts\migrate_sqlite_to_postgres.py
```

Script từ chối target không rỗng, giữ nguyên UUID và kiểm tra số bản ghi sau
commit. Nó không sao chép file upload hay FAISS index; các thư mục đó vẫn phải
còn nguyên tại đường dẫn cũ.

## 4. Biến môi trường runtime

Áp dụng cho RAG API và Celery worker/beat:

```text
APP_ENV=production
DATABASE_URL=<NEON_POOLED_SQLALCHEMY_URL>
DATABASE_POOL_SIZE=4
DATABASE_MAX_OVERFLOW=2
DATABASE_POOL_TIMEOUT_SECONDS=10
DATABASE_POOL_RECYCLE_SECONDS=300
DATABASE_CONNECT_TIMEOUT_SECONDS=10
INDEX_LOCK_MODE=redis
```

`APP_ENV=production` sẽ fail-fast nếu database là SQLite hoặc URL PostgreSQL
không có `sslmode=require|verify-ca|verify-full`. Health readiness trả
`checks.database` và `databaseBackend=postgresql`.

Nếu lưu URL bằng Google Secret Manager:

```powershell
gcloud secrets create bkquiz-rag-database-url --replication-policy=automatic
$url = '<NEON_POOLED_SQLALCHEMY_URL>'
$url | gcloud secrets versions add bkquiz-rag-database-url --data-file=-
Remove-Variable url
```

Khi triển khai RAG Cloud Run ở giai đoạn sau, gắn secret bằng
`--set-secrets DATABASE_URL=bkquiz-rag-database-url:latest`. Không đặt direct URL
vào runtime service.

## 5. Xác minh

```powershell
cd D:\BKQuiz\rag-service
$env:DATABASE_URL = '<NEON_POOLED_SQLALCHEMY_URL>'
$env:APP_ENV = 'production'
$env:INDEX_LOCK_MODE = 'redis'

.\.venv\Scripts\python.exe -c "from app.core.config import Settings; from app.db.database import Database; s=Settings(); d=Database.from_settings(s); d.validate_migrated(); print(d.backend); d.dispose()"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m mypy
```

Sau khi khởi động API, kiểm tra:

```powershell
Invoke-RestMethod http://127.0.0.1:8090/health/ready
```

Sau đó smoke test upload → worker index → search → sinh quiz. Readiness chỉ UP
khi database, Redis, Celery worker, storage và embedding đều sẵn sàng.

## 6. Rollback

Nếu cutover lỗi:

1. Dừng API/worker/beat để không phát sinh ghi ở cả hai database.
2. Giữ Neon để điều tra, không chạy script ngược tự động.
3. Khởi động lại bản local với `APP_ENV=development` và
   `DATABASE_URL=sqlite:///data/rag.db` từ bản sao lưu trước cutover.
4. Giữ nguyên Redis queue chỉ khi SQLite backup chứa đúng các job tương ứng;
   nếu không, dừng worker và đối chiếu job trước khi resume.
5. Sửa lỗi, tạo Neon database/branch sạch, chạy Alembic và migrate lại.

Không ghi đồng thời vào SQLite và Neon. Script hiện tại là one-way, cố ý không
merge vào database đã có dữ liệu để tránh document/job trùng.

## Rủi ro còn lại sau giai đoạn 3

- File upload và FAISS vẫn phụ thuộc filesystem bền vững, chưa phù hợp với nhiều
  Cloud Run instance.
- Celery/Redis vẫn là broker hiện tại; Pub/Sub/Cloud Tasks chưa triển khai.
- Redis cache/lock/rate-limit chưa chuyển Upstash.
- SQLite source không tự đồng bộ tiếp sau cutover; phải có maintenance window.

Tài liệu tham khảo: [Neon connection pooling](https://neon.com/docs/connect/connection-pooling),
[Neon Python connection](https://neon.com/docs/guides/python), và
[SQLAlchemy psycopg dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg).
