# Preprocessing v6 — 134 gói, giới hạn vùng và kiểm soát tiến trình

Phiên bản mới là **preprocessing 6.0.0 / orchestrator v5**, kế thừa orchestrator v4. Core v5.0.0 đã khóa giữ nguyên 48 file; các sửa đổi nằm trong adapter/runtime mới và được lưu trong ZIP kết quả. Qwen2.5-VL-7B-Instruct NF4, prompt mô tả văn bản một lượt, các gate kiểm duyệt và CPT giữ nguyên.

**Bản sửa 23/10/2026:** dùng `Colab_V6_L4_134_Units_JSONL_Fix.ipynb` cùng `colab_orchestrator_v5_v6_jsonl_runtime.zip`. Đã sửa lỗi đọc U+2028 làm gói 61 báo JSON bị cắt. Đang có phiên Colab thì sao chép `COLAB_JSONL_REPAIR_AND_RESUME.txt` vào một cell mới để vá và tiếp tục; venv và sửa crop đang có được giữ. Xem [hướng dẫn và chứng cứ](JSONL_FIX_REPORT_20261023.md). Cặp notebook/runtime ngày 22/10 vẫn được giữ để đối chiếu.

## File cần dùng

- `Colab_V6_L4_134_Units_JSONL_Fix.ipynb`: notebook mới, **Python 3 / L4 / High-RAM**.
- `colab_orchestrator_v5_v6_jsonl_runtime.zip`: runtime khóa SHA-256 theo notebook.
- Giữ nguyên **134 ZIP và UPLOAD_INDEX.json** trong `MyDrive/BKQuiz_cpt_data/inputs_134`. Không đóng gói lại input. Tổng 27 PDF, 13.314 trang; mỗi gói tối đa 100 trang, gói cuối 14 trang.
- `drive_upload/` chứa runtime mới và bản liên kết đến bộ input cũ để dùng nếu chưa upload. Nếu input đã có trên Drive, **chỉ cần upload runtime mới** vào `MyDrive/BKQuiz_cpt_data`, bên ngoài `inputs_134`.

## Những gì đã sửa

| Phần việc | Triển khai v6 | Bảo toàn dữ liệu |
|---|---|---|
| PDF native/crop | PyMuPDF duyệt mỗi ảnh hiển thị một lần; đối chiếu hash pixel và hash PDF cho nền IT4906 đã xem trực tiếp | Giữ ảnh toàn trang, native text, dấu toán học, vị trí và số lần lặp trong `region_audit` |
| Lọc nền trước OCR | Catalog chỉ chấp nhận đúng ảnh nền RGB 2×8 của đúng PDF IT4906, lặp ≥500 lần và phủ rộng slide | Không xóa mọi ảnh nhỏ; ảnh không biết nguồn không được tự coi là trang trí |
| Trang quá nhiều vùng | Tối đa 200 proposal ảnh/trang; vượt ngưỡng giữ toàn trang, giữ inventory và đánh dấu rủi ro cao | Không chọn bừa 200 vùng đầu rồi bỏ phần còn lại; OCR/layout toàn trang vẫn chạy |
| Layout overflow | Trên 200 candidate layout/trang được giữ nguyên trong audit để review | Không tạo hàng nghìn crop chuyên dụng; giữ raw output và ảnh nguồn |
| Batch model | Tối đa 20 trang, 256 request và 64 MiB crop/context riêng biệt mỗi batch | Một trang vượt budget sẽ dừng gói với lỗi rõ ràng; không đánh dấu hoàn tất hoặc tự bỏ nội dung |
| Định tuyến ảnh trùng | Tổng hợp canonical/page-set một lần cho mỗi hash; xếp hạng theo chỉ mục trang | Giữ nguyên score và ngân sách VLM của bản trước trên dữ liệu tương đương |
| Merge/layout | Chỉ mục request ID và record theo trang; cache hash archive trong một lượt gọi | Giữ logic đối chiếu vùng/nguồn, audit/snapshot và raw predictions; không sửa file core |
| Native/merge CPU | Subprocess có deadline 900 giây, báo tiến độ/RSS khoảng 15 giây | Gói dở không được ghi receipt hoàn tất; giữ traceback/log/progress |
| OCR/Docling/VLM | Deadline model batch 900 giây; Docling dừng gói ngay batch đầu lỗi | Không lặp lỗi nạp trọng số cho mọi nhóm; không giả thành công |
| Model cache | HF/Paddle/Docling nạp từ `/content/bkquiz_v6_models`; cache Docling được đóng ZIP sau smoke test và kiểm hash khi restore | Không dùng hoặc xóa các thư mục cache Docling lỗi cũ trên Drive |
| Quan sát tài nguyên | Thời gian, RAM khả dụng, RSS/swap/state và I/O theo PID, VRAM/GPU utilization, dung lượng trống và tiến độ từng stage | Log đầy đủ ở file; console chỉ hiện đoạn ngắn, không lưu output vào notebook |

Giới hạn 200/256/64 MiB là guard vận hành khởi đầu, không phải đánh giá chất lượng hoặc giới hạn của model. Những trang bị giữ lại cần xem audit và slide gốc. Có thể điều chỉnh qua một release mới sau khi đo; không làm lệch ngầm chính sách giữa các input.

## Chạy trên Colab

1. Chờ phiên cũ lưu xong gói hiện tại rồi đóng `SESSION`; không chạy hai queue cạnh tranh GPU. Mở notebook v6 thành một tài liệu riêng và dùng kernel sạch khi đã import runtime cũ.
2. Chọn Python 3, L4 và High-RAM. Bật/kiểm tra `Omit code cell output when saving`.
3. Upload runtime v6 vào `MyDrive/BKQuiz_cpt_data`. Giữ `inputs_134`, cả thư mục `precompleted_results` nếu đang dùng bộ đã chuẩn bị.
4. Chạy cell 1–4: mount Drive; kiểm SHA runtime/index; kiểm phần cứng; cài/khôi phục venv một lần; smoke test OCR/layout/Torch/Docling.
5. Lần đầu model cache local mới có thể cần tải trọng số. Nếu Docling lỗi header hoặc smoke test lỗi, notebook **dừng trước queue**. Kiểm tra log trong `preflight_runs` thay vì chạy tiếp cell 5. Cache lỗi trước đó không được tự xóa hoặc coi là hợp lệ.
6. Cell 5 nhận lại kết quả hoàn chỉnh rồi xử lý lần lượt gói thiếu. `MAX_UNITS=None` chạy liên tục; đặt `1` để thử một gói. ZIP được đóng tại `/content`, sao chép/kiểm SHA trên Drive rồi mới ghi receipt. Tải bằng giao diện Google Drive.

| Vai trò | Đường dẫn |
|---|---|
| Input giữ nguyên | `MyDrive/BKQuiz_cpt_data/inputs_134` |
| BASE v6 mới | `MyDrive/BKQuiz_v6_unit100` |
| BASE 134 gói cũ, chỉ đọc khi nhận lại kết quả | `MyDrive/BKQuiz_v5_unit100` |
| Xử lý cục bộ | `/content/bkquiz_v6_units` |
| Trọng số/cache đang dùng | `/content/bkquiz_v6_models` |
| Kết quả | `BKQuiz_v6_unit100/results/unit_XXXX/*.zip` |
| Biên nhận | `BKQuiz_v6_unit100/receipts` |
| Tiến độ/tài nguyên | `queue_state.json`, `current_attempt.json`, `telemetry/live_status.json` |
| Lỗi và traceback | `failures/unit_XXXX/`, `preflight_runs/` |

Deadline CPU và model mặc định 900 giây; lệnh controller có deadline tổng 10.800 giây. Một stage hợp lệ nhưng lâu hơn vẫn có thể bị dừng; đọc log và đo trước khi tăng các biến `BKQUIZ_*_TIMEOUT_SECONDS` trong notebook. Deadline làm lỗi rõ ràng và giới hạn phần việc mất khi ngắt; không bảo đảm sửa mọi nguyên nhân Connecting hoặc runtime termination của Colab.

## Kết quả cũ và tiếp tục khi ngắt

`PREVIOUS_BASE` mặc định đọc kết quả unit hoàn chỉnh từ BASE v4. Bản mới copy về local, kiểm mọi member/hash, lưu vào BASE v6 rồi ghi provenance. Không sửa receipt/ZIP ở BASE cũ. ZIP chẩn đoán, ZIP thiếu trang, sai hash hoặc `.partial` không được nhận. Orphan ZIP cuối đầy đủ có thể được nhận sau khi kiểm tra.

Kết quả dùng lại được ghi rõ **legacy / chưa chạy lại policy v6**, không nâng điểm chất lượng hoặc trạng thái verified. Bộ 7 kết quả/700 trang đã chuẩn bị vẫn có thể dùng lại; 134 gói mới chưa có kết quả thì chạy v6 từ đầu gói. Số input 9/14 của queue cũ không được chuyển thành một bộ đếm hoàn thành 134 gói.

Muốn chạy hoàn toàn policy v6 cho mọi trang, dùng một BASE mới khác, đặt `PREVIOUS_BASE=None` và `REUSE_PRECOMPLETED=False`; vẫn dùng nguyên 134 input. Không xóa BASE/kết quả cũ để làm việc này.

Sau khi runtime mất, chạy lại notebook với cùng BASE: kiểm ZIP đã lưu, bỏ qua gói hợp lệ, chạy lại gói dở từ input. Không phục hồi checkpoint nội bộ của gói dở và không chạy lại gói đã lưu chỉ vì giao diện Connecting.

## Nhập về máy và kiểm duyệt

CLI importer mới mặc định nhập vào `AI/data_preprocessing/workspaces/unit100_v6_20261022`, tách snapshot máy v6 khỏi các workspace cũ:

```powershell
AI\data_preprocessing\.venv\Scripts\python.exe -X utf8 AI\data_preprocessing\colab_orchestrator_v5\import_units.py --index AI\data_preprocessing\uploads_134_unit100_20261022\UPLOAD_INDEX.json --results "D:\duong_dan\unit_result.zip" --check-only
```

Bỏ `--check-only` để nhập thật; dùng `--output` để chọn workspace khác. Raw ZIP và audit được giữ, SQLite người duyệt không được ghi đè. Dùng app review v5 với run mới. Nguồn PDF/native text/công thức gốc giữ nguyên; VLM không tự viết lại nội dung hay tự tạo quyết định con người. Region overflow và câu trả lời lỗi cần review; gói xử lý xong không đồng nghĩa dataset đã được chứng nhận sạch hoặc sẵn sàng CPT.

## Bằng chứng và giới hạn đo lường

- `test_evidence_20261022.json`, `tests_20261022.txt`: kiểm thử native thực, timeout/kill, cache, ngân sách request, restart, model giả, legacy adoption và import giữ SQLite.
- `REGRESSION_METRICS.json`: kiểm tra thực trên 7 trang nền IT4906; benchmark CPU routing trước/sau với cùng đầu vào; hash 134 input không đổi.
- `RUNTIME_RELEASE.json`, `FINAL_VALIDATION_20261023.json`: pin artifact và kiểm tra nhất quán hiện hành.
- `test_jsonl_evidence_20261023.json`, `tests_jsonl_20261023.txt`: **52/52 kiểm thử** đạt; gồm cả 30 kiểm thử triển khai ban đầu, 10 kiểm thử auto-skip và 12 kiểm thử parser/vá runtime. Native và đóng gói thực trên 100 trang IT4025; GPU/Colab chưa chạy trong đợt sửa.
- Chưa chạy inference GPU/Docling thật trên Colab trong đợt triển khai. Không suy ra phần trăm tăng tốc toàn corpus, chất lượng OCR/VLM hay hết Connecting từ kiểm thử CPU/model giả.
