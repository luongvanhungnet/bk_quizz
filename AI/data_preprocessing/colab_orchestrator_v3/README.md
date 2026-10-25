# Điều phối Colab v3 cho preprocessing v5

Ngày triển khai: **21/10/2026**. Core preprocessing vẫn là **v5.0.0**; lớp vận hành mới là **v5-orchestrator-3-drive**. Qwen2.5-VL-7B, prompt một ảnh/một mô tả, hạn mức VLM và human review giữ nguyên.

**Bản sửa L4 ngày 22/10:** dùng `Colab_V5_L4_Stable.ipynb` và `colab_orchestrator_v3_l4_stable_runtime.zip`. Xem [chẩn đoán Connecting/autosave](CONNECTING_DIAGNOSIS_20261022.md), [hướng dẫn L4/High-RAM/Python 3](L4_SETUP.md) và [báo cáo input 01/02](RESULT_REVIEW_20261021.md). Bản L4 trước sửa ở `releases/l4_before_stability_20261022`, bản trước L4 ở `releases/drive_v3_before_l4_20261021`.

## Các file cần dùng

- `Colab_V5_L4_Stable.ipynb`: notebook L4 mới; hai tên notebook trước là alias cùng nội dung.
- `colab_orchestrator_v3_l4_stable_runtime.zip`: runtime L4 sửa ngày 22/10, được notebook khóa SHA-256.
- **Giữ nguyên** 14 file trong `D:\BKQuiz\AI\data_preprocessing\uploads_14_sequential_20261021`, tên `v5_sequential_XX_of_14.zip`. Không đóng lại ZIP, không thay runtime bên trong chúng. Runtime v3 được nạp từ ZIP riêng.

## Cách chạy

1. Qua **giao diện Google Drive**, đặt 14 ZIP input và `colab_orchestrator_v3_l4_stable_runtime.zip` vào **MyDrive/BKQuiz_cpt_data**. Nếu 14 input đã có ở đó, chỉ thêm runtime ZIP mới. Không đặt nhiều bản của cùng chỉ số input trong thư mục này hoặc thư mục con.
2. Mở notebook mới trên Colab, chọn Python 3/L4 GPU/High-RAM nếu có tùy chọn riêng. Cell 1 chỉ kết nối Drive, không có hộp upload.
3. Cell 2 kiểm tra ZIP runtime và từng file Python theo hash đã khóa.
4. Cell 3 kiểm kê input, kiểm tra đủ chỉ số và cùng plan. Mặc định `BATCH_PAGES=20`, `MAX_INPUTS=1` để chạy thử một input; đổi `MAX_INPUTS=None` để chạy toàn bộ phần còn lại. `KEEP_MODEL_RESIDENT=True` giữ Qwen qua các input; dùng `False` khi RAM không đủ. Không cần cài lại môi trường khi chọn False.
5. Cell 4 cài/khôi phục các môi trường **một lần**, rồi smoke test Paddle CUDA/OCR/layout, Torch/NF4 và Docling. Nếu lỗi, dừng và lưu chẩn đoán trước hàng đợi. Docling dùng cache riêng, không ghi đè cache lỗi trước.
6. Cell 5 lấy input từ Drive, xử lý trên `/content`, đóng ZIP tại đó, sao chép lên Drive và kiểm tra SHA-256. Không nhập `DA_TAI`. Chỉ chuyển input sau khi kết quả đã được lưu bền vững.
7. Tải kết quả bằng **Google Drive → BKQuiz_v5_drive_v3 → downloads**. Tải độc lập với phiên tính toán, có thể tải sau khi xử lý xong nhiều input.

Các đường dẫn mặc định:

| Vai trò | Đường dẫn |
|---|---|
| Input | `/content/drive/MyDrive/BKQuiz_cpt_data` |
| Công việc cục bộ | `/content/bkquiz_v5_drive_v3` |
| State/checkpoint/kết quả | `/content/drive/MyDrive/BKQuiz_v5_drive_v3` |
| ZIP cuối | `BKQuiz_v5_drive_v3/downloads/v5_drive_results_*.zip` |
| Thống kê file cuối | `BKQuiz_v5_drive_v3/downloads/latest_index.json` |
| Đo thời gian/tài nguyên | `BKQuiz_v5_drive_v3/telemetry/events_*.jsonl` |

Input, ảnh nguồn và PDF không đi qua `files.upload()`; kết quả không đi qua `files.download()`. Google Drive mount vẫn cần hoạt động để lưu checkpoint/kết quả. Việc này giảm phụ thuộc vào truyền file qua giao diện notebook, không bảo đảm Colab không bao giờ ngắt runtime.

## Tiếp tục tiến độ v2 đã chạy

Đóng phiên xử lý cũ trước khi chuyển phiên bản. Giữ nguyên **BASE v2**, các input, cache và kết quả; không xóa các checkpoint cũ.

Ở cell 3 đặt:

```python
PREVIOUS_BASE = Path('/content/drive/MyDrive/BKQuiz_v5_sequential')
```

Migration chỉ tạo state/index mới trong BASE v3 và giữ tham chiếu tới checkpoint/result v2 đã có. Nó kiểm tra plan, hash input và kết quả; không sửa BASE cũ, không tạo phê duyệt. Những stage v2 đã chạy nhưng chưa merge được đọc lại từ dữ liệu thô cũ. File kết quả hoàn thành trước khi mất kết nối được dùng lại, kể cả khi chưa xác nhận tải. Tiến độ v3 vẫn tiếp tục được nếu bạn đã nhập `DA_TAI` ở v2 dù chưa tải thành công, miễn ZIP trên Drive còn nguyên hash.

Migration là tùy chọn, mặc định `PREVIOUS_BASE=None`. Không dùng BASE v2 làm BASE ghi của v3. Nếu migration báo nguồn đang thay đổi hoặc thiếu dữ liệu, xử lý chẩn đoán trước; không tự xóa state để chạy lại. Các kết quả cũ có thể vẫn nằm trong thư mục downloads của BASE v2; `finished_inputs` ghi đường dẫn của chúng.

## Nhóm trang nhỏ và khôi phục

- Native extraction/render/crop đi theo nhóm tối đa 20 trang, ghi metadata/record nhóm xuống ổ cục bộ, giải phóng các đối tượng ảnh/text của nhóm rồi checkpoint delta lên Drive.
- Các job gốc tối đa 100 trang vẫn giữ ID và phạm vi. OCR/layout/formula/table/Docling/VLM chạy trên các gói con tối đa 20 trang; nhóm không có yêu cầu cho specialist/VLM được bỏ qua.
- Đối với Docling, số trang trong PDF con được ánh xạ lại về PDF của job gốc trước merge. Đối với VLM, envelope được liên kết với manifest cha; đầu ra thô và manifest con vẫn được giữ. Đây là sửa metadata liên kết, không sửa nội dung model và không xác nhận tính đúng của mô tả.
- Coverage Docling chỉ tính các trang của nhóm thành công, không coi một nhóm thành công là đã xử lý toàn job 100 trang. Các trang structure thành công vẫn được cộng độc lập; layout thiếu giữ trạng thái partial và chặn inference khi cần.
- Giữ discovery của **toàn tài liệu** trước định tuyến inference, để hạn mức VLM không bị nhân lên theo nhóm nhỏ.
- Mỗi nhóm model hoàn thành có checkpoint riêng. Reset runtime khôi phục nhóm đã lưu; nhóm bị gián đoạn trước khi lưu bền vững có thể phải chạy lại.
- Sau khi ZIP cuối được lưu và xác minh, dọn dữ liệu cục bộ có thể tái tạo. Chỉ xóa run của học phần khi không còn job tương lai của học phần đó. Cache IT3170 nhận theo nhiều input vẫn được giữ cho đến khi đủ.
- Sau reset chạy lại các cell với cùng BASE, input và `BATCH_PAGES`. Nếu cần đổi batch size, dùng queue mới hoặc hoàn tất queue hiện tại.

Các phép merge/cross-validation/routing của core v5 vẫn đọc metadata/records toàn tài liệu; không khẳng định toàn bộ RAM đã bị chặn tuyệt đối ở 20 trang. Nội dung ảnh, native page blocks và đầu ra parser nặng được chia nhóm. RAM giữ model vẫn là khoản riêng cần đo.

## Giảm dung lượng gói xuất

Return v3 dùng `objects/<sha256>` và `logical_files` trong `return.json`: cùng byte chỉ lưu một lần, importer khôi phục lại đường dẫn logic và kiểm tra hash. Các packet được lưu dạng file thành phần, tránh mang thêm một ZIP input đầy đủ có cùng ảnh với snapshot. Các ZIP kết quả/raw audit còn cần cho chứng cứ được giữ, cùng mọi revision và receipt; không xóa nội dung lịch sử chỉ để giảm dung lượng.

Manifest ghi `logical_bytes`, `unique_bytes`, `duplicate_bytes_avoided`. Đây là số byte trùng chính xác tránh lưu, **không phải** phần trăm chất lượng hay cam kết mức giảm kích thước ZIP nén. PNG/JPEG/PDF/ZIP được lưu không nén lại trong ZIP ngoài, giữ nguyên byte ảnh, ký hiệu và hash.

Return v3 cần **importer v3**. Giải nén thủ công bằng Explorer chỉ thấy kho object và không khôi phục cấu trúc run đầy đủ. Importer này cũng đọc được return v2. Không chọn hai kết quả khác nhau cho cùng chỉ số input nếu snapshot thay đổi.

## Xem thời gian và tài nguyên

Telemetry ghi:

- `stage_start/stage_end`: native, package, model batch, merge, checkpoint, hashing, đóng ZIP, truyền file.
- `resources`: RAM khả dụng/toàn VM, RSS từng tiến trình controller/kernel/worker, tổng RSS cây tiến trình, VRAM theo GPU và PID, GPU utilization, dung lượng ổ trống.
- `transfer_progress/transfer_complete`: byte đã truyền, tổng byte, phần trăm, hash đích sau kiểm tra.
- `archive_progress/export_size`: tiến độ đóng gói, số byte ZIP và phần trùng tránh lưu.

Lấy mẫu tài nguyên khoảng **15 giây**, đồng bộ telemetry lên Drive khoảng **60 giây** và khi đóng phiên. RSS cộng có thể đếm lặp vùng nhớ dùng chung; dùng thêm RAM khả dụng để phân tích OOM. Khi không có `nvidia-smi` hoặc dữ liệu hệ thống, trường tương ứng để trống; không suy ra số đo GPU từ test CPU. Các span lồng nhau có thể chồng thời gian, không cộng mọi dòng thành wall time.

Sau khi lấy các file telemetry về máy:

```powershell
$py = 'D:\BKQuiz\AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe'
$events = @(Get-ChildItem -LiteralPath 'D:\BKQuiz\AI\data_preprocessing\colab_returns\telemetry' -Filter '*.jsonl' | ForEach-Object { $_.FullName })
& $py -X utf8 D:\BKQuiz\AI\data_preprocessing\colab_orchestrator_v3\summarize_telemetry.py @events
```

Cuối gói, telemetry trên Drive có thể đầy đủ hơn bản trong ZIP: các sự kiện hoàn tất đóng ZIP/truyền chính ZIP đó xảy ra sau thời điểm snapshot log. Client giữ con trỏ log xuyên các lệnh và đọc từng phần giới hạn; không in lại toàn bộ lịch sử.

## Nhập kết quả về máy

```powershell
$py = 'D:\BKQuiz\AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe'
$returned = @(Get-ChildItem -LiteralPath 'D:\BKQuiz\AI\data_preprocessing\colab_returns' -Filter 'v5_drive_results_*.zip' | ForEach-Object { $_.FullName })
& $py -X utf8 D:\BKQuiz\AI\data_preprocessing\colab_orchestrator_v3\import_returns.py `
  --plan D:\BKQuiz\AI\data_preprocessing\plans\corpus_20261021 `
  --bundle-index D:\BKQuiz\AI\data_preprocessing\uploads_14_sequential_20261021\UPLOAD_INDEX.json `
  --results @returned --check-only
```

Sau khi kiểm tra đạt, dùng cùng lệnh và bỏ `--check-only`. Nếu migration có kết quả v2, thêm các ZIP v2 cần thiết vào `$returned`. Không nhập các file `v5_drive_diagnostics_*.zip` như kết quả hoàn thành. SQLite kiểm duyệt tại máy được giữ; VLM vẫn cần người xác nhận; không tự xuất CPT.

## Giới hạn đã biết

Chưa benchmark trên GPU Colab hoặc Drive thật. Đã kiểm thử logic bằng PDF và core v5 thật, inference mô phỏng. Phiên bản này sửa vận hành/I/O/chia nhóm, **không tuyên bố đã sửa** lỗi model Docling `header too large` trong cache hoặc mọi lỗi OCR/Table đã ghi ở lần trước. Lỗi vẫn có traceback và xuất diagnostics/quality flags. Môi trường và cache trọng số HF/Paddle vẫn dùng vị trí Drive cũ; nạp model lần đầu có thể còn chậm. Qwen ở CPU giữa input vẫn tiêu thụ RAM nếu giữ model resident.
