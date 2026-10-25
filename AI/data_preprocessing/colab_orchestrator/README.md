# Điều phối Colab cho data preprocessing v5

## Mục tiêu và phạm vi

Bộ điều phối là lớp chạy hàng đợi phía ngoài **release v5.0.0**, không thay đổi prompt, model, schema dữ liệu hoặc cổng kiểm duyệt của release. Mã v5 gốc được kiểm tra SHA-256 trước khi dùng. Qwen giữ nguyên **Qwen2.5-VL-7B-Instruct, NF4**, một lượt quan sát tự nhiên trên một ảnh.

Kế hoạch thực tế hiện có **27 PDF, 13.314 trang, 148 gói con**. Số 134 là phép chia tổng trang cho 100 có làm tròn; kế hoạch giữ ranh giới học phần nên có 148 gói. Nay người dùng nhập **14 file upload**, mỗi file chứa 10–11 descriptor gói con cùng các nguồn/cache cần thiết. Chỉ tải lên đủ 14 file một lần; các pha discovery/inference được tạo và chạy tự động, không cần một lượt upload thủ công thứ hai sau layout.

Để thực hiện được điều này, 14 file chứa PDF gốc và snapshot máy hiện có của IT3170. Với 26 học phần mới, **native extraction và render cũng chạy trên Colab**. Không cần render toàn corpus trên máy Windows trước khi upload. PDF gốc và số trang nguồn được giữ; không dùng hash PDF subset thay hash nguồn.

## File cần dùng

- Notebook: [Colab_V5_Orchestrator_14_Uploads.ipynb](Colab_V5_Orchestrator_14_Uploads.ipynb).
- Thư mục 14 gói: [uploads_14_20261021](../uploads_14_20261021).
- Danh mục hash/dung lượng từng gói: [UPLOAD_INDEX.json](../uploads_14_20261021/UPLOAD_INDEX.json).
- Báo cáo triển khai/kiểm thử: [IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md).

## Chạy trên Colab

1. Mở notebook mới trên Colab, chọn runtime GPU.
2. **Cell 1 — Drive:** kết nối Drive và chọn `BASE`. Cell này không mở hộp thoại upload.
3. **Cell 2 — input:** chọn cùng lúc 14 file `v5_upload_01_of_14.zip` … `v5_upload_14_of_14.zip`. Hoặc đặt `INPUT_DIR` trỏ đến thư mục trên Drive đã chứa đủ 14 file. Cell này không gọi `drive.mount`, không cài thư viện và không chạy model.
4. **Cell 3:** xác minh/nạp mã điều phối.
5. **Cell 4:** khôi phục hoặc cài môi trường một lần. Nếu phiên bản đã khớp thì bỏ qua cài đặt. Dùng lại archive môi trường cùng Python ABI từ `MyDrive/BKQuiz_preprocessing` nếu còn tương thích; không dùng `python -m venv` vốn đã gây lỗi ở runtime cũ.
6. **Cell 5:** chạy hàng đợi. Giữ nguyên cell cho đến khi hoàn tất hoặc runtime ngắt. Có heartbeat cho các bước dài và nhật ký riêng từng worker.
7. **Cell 6:** xem danh sách 14 ZIP kết quả trên Drive; đặt `DOWNLOAD_INDEX=1`, `2`… để tải từng file. Không phải upload lại input khi tải kết quả.

Trên Drive, mặc định dùng `MyDrive/BKQuiz_v5_orchestrator`. Không trộn một bộ input khác vào BASE đang chứa queue cũ.

## Các pha thực thi

| Pha | Cách chạy | Đối tượng lưu trong bộ nhớ |
|---|---|---|
| Kiểm tra input | SHA-256 mọi thành phần, PDF nguồn, kế hoạch, release | Không có model |
| Native/render | PyMuPDF; giữ nguyên Unicode và ký hiệu | Không có model GPU |
| OCR đầu vào | Chạy liên tiếp các gói discovery và IT3170 cần xử lý | Một pipeline OCR cho cả lượt này |
| Layout | PP-StructureV3 liên tiếp các gói; Docling trong tiến trình CPU riêng | Một pipeline layout; một converter Docling |
| Đối chiếu/routing | Nhập layout từng gói, đủ inventory toàn học phần mới tạo inference | Không lấy biểu quyết thay kiểm chứng nguồn |
| OCR vùng hình | Chỉ OCR vùng mới với học phần đã chạy discovery | Một pipeline OCR cho lượt vùng hình |
| Formula/table | Bỏ qua seed hợp lệ và vùng bị giữ do phân loại sai | Một model cho mỗi lượt chuyên gia |
| VLM | Chỉ vùng đã định tuyến; lần lượt toàn bộ gói | **Một Observer Qwen duy nhất**, nạp khi gặp cache miss đầu tiên |
| Xuất | 14 ZIP kết quả chứa gói con, raw output, manifest và snapshot run | Không xuất CPT tự động |

Paddle/Docling được đóng trước khi chạy Qwen để tránh giữ hai họ model GPU đồng thời. Qwen không bị tạo lại ở ranh giới các gói upload/gói con. Mỗi ảnh vẫn là một lần inference, không ghép hàng loạt ảnh vào một prompt. Thay đổi này giảm số lần nạp model, không đổi yêu cầu đầu ra v5.

Môi trường tách biệt: controller Python, Paddle, Docling và VLM. Các phiên bản GPU kế thừa notebook chính thức đã dùng: PaddleOCR 3.7.0/PaddleX 3.7.2/Paddle GPU 3.2.2; Torch 2.6.0/Transformers 4.57.6/bitsandbytes 0.48.1; Docling 2.140.0. MinerU không được bật thêm trong lớp điều phối này.

## Tiếp tục sau khi runtime ngắt

- Giữ cùng `BASE` và cùng 14 file.
- Kết nối Drive ở cell 1. Đặt `REUSE_REGISTERED=True` trong cell 2, rồi chạy tiếp các cell.
- `queue_state.json` ghi riêng trạng thái gói/pha/engine. Gói thành công không tự chạy lại.
- Raw output từng vùng nằm trên Drive ngay khi được ghi; nếu ngắt giữa một stage, worker đọc lại cache/fingerprint trước khi xử lý phần còn thiếu.
- Các run native/layout có checkpoint dạng ZIP delta: ảnh bất biến chỉ lưu lần đầu, các revision/metadata mới lưu nối tiếp. Khôi phục kiểm tra hash trước khi dùng.
- Cache VLM theo ảnh, crop, context, model revision và cấu hình. Kết quả thành công cũ được dùng lại, gồm các quan sát IT3170 đã có.
- **Model trong RAM không tồn tại qua reset runtime.** Một phiên runtime mới phải nạp model lại một lần cho phần còn thiếu. Archive môi trường giúp giảm cài lại, không lưu RAM/GPU.
- Các stage đã trả lỗi được giữ làm diagnostics, không tự retry vô hạn. Xem `summary.json`, `queue_state.json`, `logs/` và `raw_results/`. Học phần thiếu layout thành công cho toàn bộ trang bị giữ lại, không tự nhận là hoàn tất.

Một shard IT3170 1–100 đã nhập thành công trước đây được nhận bằng receipt/hash và giữ ở trạng thái completed; không chạy lại cả shard chỉ để phục vụ đóng gói.

## Nhập kết quả về Windows

Tải 14 file `v5_results_upload_XX_*.zip` của **cùng một lần export** vào một thư mục, ví dụ `D:\BKQuiz\AI\data_preprocessing\colab_returns`. Không chọn lẫn hai lần export có snapshot khác nhau. Trước hết kiểm tra:

```powershell
Set-Location D:\BKQuiz
$py = 'AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe'
$returned = @(Get-ChildItem -LiteralPath 'AI\data_preprocessing\colab_returns' -Filter 'v5_results_upload_*.zip' | ForEach-Object { $_.FullName })
& $py -X utf8 AI\data_preprocessing\colab_orchestrator\import_returns.py `
  --plan AI\data_preprocessing\plans\corpus_20261021 `
  --bundle-index AI\data_preprocessing\uploads_14_20261021\UPLOAD_INDEX.json `
  --results $returned --check-only
```

Khi kiểm tra đạt, nhập bằng cùng lệnh và bỏ `--check-only`:

```powershell
& $py -X utf8 AI\data_preprocessing\colab_orchestrator\import_returns.py `
  --plan AI\data_preprocessing\plans\corpus_20261021 `
  --bundle-index AI\data_preprocessing\uploads_14_20261021\UPLOAD_INDEX.json `
  --results $returned
```

Importer giữ ZIP gốc trong audit, kiểm tra nguồn/ảnh/số trang/schema, khôi phục run mới và dùng đường nhập chính thức cho run đã tồn tại. Không ghi đè SQLite kiểm duyệt, không tự thêm approval, không xuất CPT. Nếu bản máy mới làm revision đã duyệt thay đổi, quy tắc stale review của v5 vẫn áp dụng; lịch sử quyết định cũ được giữ.

Mở kiểm duyệt cho học phần mong muốn:

```powershell
& $py -X utf8 AI\data_preprocessing\manage.py review `
  --plan AI\data_preprocessing\plans\corpus_20261021 --document IT3170 --port 8765
```

Web giữ scope chỉ các đầu ra VLM thành công. Dùng ←/→ chuyển, ↑ chấp nhận, ↓ loại bỏ, nút Sửa để chỉnh nội dung. CER/WER/độ chính xác vẫn cần ground truth; chạy xong hàng đợi không đồng nghĩa dữ liệu đã đạt chất lượng để CPT.

## Xây dựng lại input cho một kế hoạch mới

Không sửa gói input đã upload. Với thay đổi nguồn/kế hoạch/runtime, tạo thư mục bundle mới, build notebook lại và chạy:

```powershell
& $py -X utf8 AI\data_preprocessing\colab_orchestrator\build_notebook.py
& $py -X utf8 AI\data_preprocessing\colab_orchestrator\build_bundles.py `
  --plan AI\data_preprocessing\plans\corpus_20261021 `
  --config AI\data_preprocessing\production.json `
  --out AI\data_preprocessing\uploads_14_NEW_RUN --count 14
```

Gói upload tổng hợp có định dạng riêng; không áp dụng giới hạn 512 MiB của từng packet xử lý nội bộ lên file tổng hợp. Packet con vẫn chịu giới hạn cũ. Trước khi mở rộng, đối chiếu dung lượng đĩa runtime và Drive với danh mục thực tế; không có giới hạn giả định về thời lượng Colab được dùng làm tiêu chí thành công.
