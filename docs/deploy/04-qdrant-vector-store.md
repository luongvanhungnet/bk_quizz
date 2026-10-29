# Giai đoạn 4 — chuyển FAISS sang Qdrant

## Kết quả triển khai

RAG hỗ trợ hai backend vector:

- `faiss`: chỉ dành cho test/local rollback;
- `qdrant`: bắt buộc trong production.

Qdrant dùng một collection chung. Mỗi point có bộ lọc bắt buộc theo namespace,
phiên bản snapshot, owner và document. Neon giữ con trỏ `active_version` trong
bảng `vector_index_snapshots`; Qdrant ghi xong toàn bộ point trước khi Neon đổi
con trỏ, nên index chưa hoàn chỉnh không xuất hiện trong truy vấn.

Hai phiên bản gần nhất được giữ để bảo vệ request đang chạy. Phiên bản cũ hơn
được dọn best-effort sau mỗi commit. FAISS cũ không bị xóa sau migration.

Hybrid retrieval vẫn hoạt động: dense vector search chạy ở Qdrant với tenant
filter; BM25 và reranker vẫn chạy trong RAG API trên snapshot chunk đã tải.

## 1. Tạo Qdrant Cloud cluster

1. Đăng nhập Qdrant Cloud và tạo cluster gần region đang chạy RAG.
2. Trong **Database API Keys**, tạo key có quyền manage/write cho collection.
3. Ghi lại cluster URL HTTPS và API key một lần.
4. Không cần tạo collection thủ công; RAG tạo collection cùng payload indexes
   `_namespace`, `_version`, `documentId`, `ownerId` khi khởi động.

Ví dụ URL:

```text
https://example-id.region.cloud.qdrant.io:6333
```

Không dùng Cloud Management Key. Cần **Database API Key** của cluster. Qdrant
khuyến nghị gửi key qua tham số `api_key` của SDK và tạo payload index cho các
field lọc chính xác.

## 2. Chạy migration Neon mới

Dùng Neon direct URL, không dùng URL pooler:

```powershell
cd D:\BKQuiz\rag-service
$env:DATABASE_URL = '<NEON_DIRECT_SQLALCHEMY_URL>'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

Kết quả:

```text
0007_qdrant_snapshots (head)
```

Migration chỉ thêm bảng con trỏ snapshot; chưa thay đổi hoặc xóa FAISS.

## 3. Cấu hình và kiểm tra Qdrant

Trong một PowerShell mới:

```powershell
cd D:\BKQuiz\rag-service

$env:APP_ENV = 'production'
$env:DATABASE_URL = '<NEON_POOLED_SQLALCHEMY_URL>'
$env:INDEX_LOCK_MODE = 'redis'
$env:VECTOR_STORE_BACKEND = 'qdrant'
$env:QDRANT_URL = 'https://<QDRANT_CLUSTER>:6333'
$env:QDRANT_API_KEY = '<QDRANT_DATABASE_API_KEY>'
$env:QDRANT_COLLECTION = 'bkquiz_chunks'
$env:QDRANT_TIMEOUT_SECONDS = '15'
$env:QDRANT_UPSERT_BATCH_SIZE = '128'
```

Các biến Gemini, internal key và Redis vẫn phải được cấu hình như trước.
Production fail-fast nếu Qdrant dùng HTTP, thiếu API key hoặc vẫn chọn FAISS.

Kiểm tra kết nối mà không in secret:

```powershell
.\.venv\Scripts\python.exe -c "from app.core.config import Settings; from app.services.qdrant_vector_store import build_qdrant_client; s=Settings(); c=build_qdrant_client(s); print(c.get_collections()); c.close()"
```

## 4A. Hệ thống chưa có FAISS cũ

Không cần import. Khi upload/reindex tài liệu, worker sẽ ghi thẳng vào Qdrant.

## 4B. Chuyển FAISS hiện có

Thực hiện maintenance window:

1. Dừng RAG API, Celery worker và beat.
2. Sao lưu thư mục `SYSTEM_INDEX_DIR` và `USER_INDEX_DIR`.
3. Đảm bảo Neon ở migration `0007` và Qdrant chưa có active snapshot của các
   namespace cần chuyển.
4. Dùng cùng embedding model với index FAISS cũ.

```powershell
cd D:\BKQuiz\rag-service

# Giữ nguyên các biến DATABASE_URL/QDRANT ở mục 3.
$env:SYSTEM_INDEX_DIR = 'D:\BKQuiz\rag-service\data\indexes\system'
$env:USER_INDEX_DIR = 'D:\BKQuiz\rag-service\data\indexes\users'

# Chỉ liệt kê namespace và số chunk.
.\.venv\Scripts\python.exe scripts\migrate_faiss_to_qdrant.py --dry-run

# Upload vector/chunk và tạo active pointer trong Neon.
.\.venv\Scripts\python.exe scripts\migrate_faiss_to_qdrant.py
```

Script không gọi embedding/Gemini: nó đọc trực tiếp vector FAISS hiện có, upload
theo batch, giữ UUID chunk và kiểm tra lại số chunk. Nếu namespace đã có active
snapshot, script dừng; chỉ dùng `--replace` khi chủ động muốn thay snapshot đó.

## 5. Chạy local bằng Docker

Từ root repository:

```powershell
cd D:\BKQuiz
docker compose --profile rag up --build
```

Hoặc chỉ RAG:

```powershell
cd D:\BKQuiz\rag-service
docker compose up --build
```

Compose chạy Qdrant local tại `http://127.0.0.1:6333`, Redis, API, worker và
beat. Metadata local vẫn có thể dùng SQLite; production mới bắt buộc Neon.

Kiểm tra:

```powershell
Invoke-RestMethod http://127.0.0.1:6333/readyz
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

Readiness phải có:

```text
checks.vectorStore = UP
vectorStoreBackend = qdrant
```

Sau đó smoke test upload → worker index → search → sinh quiz → reindex.

## 6. Secret Manager và runtime cloud

Lưu API key, không lưu URL/collection nếu không cần:

```powershell
gcloud secrets create bkquiz-qdrant-api-key --replication-policy=automatic
$key = '<QDRANT_DATABASE_API_KEY>'
$key | gcloud secrets versions add bkquiz-qdrant-api-key --data-file=-
Remove-Variable key
```

Các service RAG API và worker phải dùng cùng:

```text
VECTOR_STORE_BACKEND=qdrant
QDRANT_URL=https://...
QDRANT_COLLECTION=bkquiz_chunks
QDRANT_API_KEY=<secret>
```

Không đưa `QDRANT_API_KEY` xuống React hoặc Spring frontend contract.

## 7. Rollback

Nếu Qdrant cutover lỗi:

1. Dừng API/worker để không ghi thêm snapshot.
2. Không xóa collection Qdrant hoặc bảng `vector_index_snapshots`.
3. Local có thể đặt `APP_ENV=development`, `VECTOR_STORE_BACKEND=faiss` và dùng
   lại thư mục FAISS đã sao lưu.
4. Production phải rollback về image Giai đoạn 3, vì image hiện tại cố ý từ
   chối FAISS trong production.
5. Sửa cấu hình/Qdrant, chạy script với `--replace` nếu namespace Qdrant đã có
   snapshot không mong muốn, rồi chuyển lại image Giai đoạn 4.

## Giới hạn còn lại

- Original RAG upload được chuyển sang R2 trong Giai đoạn 5. Reindex từ thư
  mục local vẫn không dành cho runtime Cloud Run.
- BM25 vẫn được dựng trong RAM từ chunk payload, chưa dùng sparse vector Qdrant.
- Celery/Redis, Upstash và Ably chưa nằm trong giai đoạn này.

Tham khảo chính thức: [Qdrant Cloud authentication](https://qdrant.tech/documentation/cloud/authentication/),
[Qdrant filtering](https://qdrant.tech/documentation/search/filtering/),
[Qdrant payload](https://qdrant.tech/documentation/concepts/payload/) và
[Qdrant Cloud quickstart](https://qdrant.tech/documentation/cloud/quickstart-cloud/).
