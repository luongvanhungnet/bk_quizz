# Báo cáo triển khai bộ điều phối Colab v5

Ngày: **21/10/2026**. Phiên bản điều phối: `v5-orchestrator-1`; core dữ liệu: **v5.0.0**.

## Kết quả triển khai

Đã bổ sung bộ điều phối cho 27 PDF / 13.314 trang. Kế hoạch cũ có **148 gói con**, nay được vận chuyển bằng **14 file upload**. Đây là giảm số file nhập thủ công; không cắt bớt trang hoặc giảm số gói cần theo dõi trong audit. Trong từng học phần mới, discovery được hoàn thành trước khi tạo gói inference để giữ routing budget theo toàn học phần.

Notebook có sáu bước riêng: **kết nối Drive → nhập input → xác minh mã → cài môi trường → chạy hàng đợi → tải kết quả**. Drive và upload không nằm chung cell. Có phương án nhập từ thư mục Drive và dùng lại danh sách input đã đăng ký khi tiếp tục.

## Công nghệ và phần việc

| Thành phần | Công nghệ | Phần việc |
|---|---|---|
| `build_bundles.py` | Python/ZIP/SHA-256 | Chia descriptor 148 job thành 14 nhóm, đóng PDF nguồn đúng một lần, giữ seed IT3170, đưa các engine đúng release vào gói |
| `common.py` | Streaming hash, ghi atomic, ZIP có inventory | Kiểm tra archive, chống lẫn nguồn, checkpoint delta và khôi phục |
| `env_setup.py` | uv, venv riêng, version probe, archive môi trường | Khôi phục/cài trước hàng đợi; không pip install trong vòng lặp gói |
| Native/controller | PyMuPDF, Pillow, ImageHash, Pydantic từ core v5 | Phân loại text layer, render, tọa độ, chuẩn hóa, kiểm tra schema/nguồn |
| Paddle worker thường trú | PaddleOCR, PP-StructureV3, PP-FormulaNet-S | OCR, layout, công thức và bảng; dùng lại pipeline qua các gói trong mỗi lượt engine |
| Parser worker CPU | Docling | Giữ một converter, xuất cấu trúc độc lập và đối chiếu bbox/số trang |
| VLM worker thường trú | Qwen2.5-VL-7B-Instruct NF4, Transformers/Torch | Một model nạp lười trên cache miss đầu tiên, dùng tiếp cho toàn bộ queue VLM |
| `orchestrator.py` | Subprocess thường trú, IPC JSON qua file, ledger trên Drive | Điều phối các pha, heartbeat, tiếp tục gói, giữ stack trace, tách tài nguyên GPU |
| `import_returns.py` | Hash/schema/source validation và đường merge v5 | Nhập ZIP kết quả nhiều job về Windows, giữ raw archive và lịch sử người duyệt |

Giới hạn đầu ra/prompt/model của v5 được giữ. Không đưa graph inventory hoặc JSON schema bắt buộc trở lại prompt. Việc giữ model thường trú thay vòng đời tiến trình, không tăng số bước suy luận trong một request.

## Khác với notebook từng packet

| Trước | Hiện tại |
|---|---|
| Upload từng packet tối đa 100 trang | Upload 14 container; tự tạo các packet con |
| Người dùng chuyển discovery về máy để tạo inference | Điều phối native/layout/routing/inference ngay trên Colab |
| Worker VLM mới cho mỗi packet | Một worker VLM cho toàn lượt, dùng chung model trong RAM |
| Mount Drive và nhập file chung một cell | Hai cell và hai thao tác riêng |
| Theo dõi từng ZIP bằng tay | Ledger theo job/phase/engine, cache ảnh, checkpoint run |
| Tải từng kết quả rồi merge riêng | 14 archive kết quả; importer kiểm tra và nhập nhiều job |

Với 26 tài liệu mới, native/render được chuyển sang Colab trong luồng điều phối để không cần vòng upload bổ sung. IT3170 giữ snapshot máy và specialist cache cũ. Các xác nhận của người dùng nằm trong SQLite tại máy; file đó không được đưa vào upload hoặc ghi đè khi nhập.

## Kiểm chứng đã thực hiện

**14/14 test đạt trên máy hiện tại**, thời gian lượt cuối **16,557 giây**:

- 148 job được chia đúng 14 nhóm, không mất hoặc lặp job.
- Archive sai hash/path bị từ chối trước khi trích xuất payload; checkpoint chỉ ghi phần thay đổi và khôi phục đúng hash.
- Hai packet VLM khác nhau dùng **một lần khởi tạo model giả lập** qua hàm chạy VLM thật của v5; replay tiếp theo đọc cache, không thêm inference.
- Pipeline Paddle được giữ qua hai packet; seed chuyên gia/vùng phân loại sai được bỏ qua.
- Đổi config VLM giữa queue bị từ chối; lỗi khởi tạo không gây lặp tải model cho mọi ảnh.
- IPC giữ traceback đầy đủ và đóng đúng worker do điều phối tạo.
- Stage đã hoàn thành không được gọi lại.
- Tích hợp PDF hai trang với engine giả lập chạy qua **native → discovery → materialize layout → inference → checkpoint → export → import** bằng mã mapping/schema thực của v5.
- Nhập lần hai không merge lại kết quả đã có và không thay đổi file audit kiểm duyệt sẵn có trong fixture.
- Tất cả cell notebook compile; mount Drive, upload và setup được tách riêng.

Lệnh kiểm thử:

```powershell
AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe -X utf8 -m unittest discover -s AI\data_preprocessing\colab_orchestrator -p 'test_*.py' -v
```

Đây là kiểm chứng điều phối trên CPU với inference giả lập, **chưa phải benchmark GPU/độ chính xác của toàn corpus**. Không có CER/WER/Q mới và không khẳng định phần trăm tăng tốc thực nghiệm. Số lần khởi tạo trên GPU thật sẽ được ghi trong stage response `model_initializations` và worker log khi người dùng chạy notebook.

## Dữ liệu và điều kiện vận hành

- Receipt/hash của shard IT3170 1–100 đã hoàn thành được giữ để bỏ qua toàn shard; các quan sát VLM thành công cũ được đưa vào cache.
- Core release chính thức giữ nguyên; lớp điều phối nằm riêng trong `AI/data_preprocessing/colab_orchestrator`.
- Kết quả VLM vẫn là dữ liệu chưa xác minh cho đến khi con người duyệt. Bộ điều phối không tạo approval, không gọi CPT exporter và không mở cổng bỏ qua dedup/split audit toàn corpus.
- Sau reset runtime, model RAM/GPU cần nạp lại; checkpoint/cache giúp không sinh lại kết quả đã hoàn thành.
- Lỗi engine được ghi và giữ; học phần thiếu layout bị chặn inference thay vì bỏ qua trang. Lỗi đã ghi không tự retry vô hạn.
- Đã kiểm tra toàn bộ **14 archive / 148 job / 27 PDF / 13.314 trang**, tổng **854,39 MiB**, file nhỏ nhất **2,15 MiB**, lớn nhất **382,61 MiB**. Mọi hash thành phần đạt; mã runtime khớp notebook và giống nhau giữa 14 gói. Có 7 cache VLM thành công và 1 shard hoàn thành được nhận bằng receipt. Không có SQLite kiểm duyệt trong upload. Xem [biên bản kiểm tra input](INPUT_VALIDATION_20261021.json).
- Xem danh sách dung lượng/hash thực tế của 14 file trong [UPLOAD_INDEX.json](../uploads_14_20261021/UPLOAD_INDEX.json). Phân bố source/cache khiến dung lượng các file không đồng đều; chia 14 file là yêu cầu vận chuyển, không phải 14 tiến trình chạy đồng thời.

Hướng dẫn chạy và nhập kết quả: [README.md](README.md).
