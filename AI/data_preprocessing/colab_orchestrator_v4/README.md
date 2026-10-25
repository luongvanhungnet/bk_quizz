# Preprocessing v5: 134 gói độc lập, tối đa 100 trang xử lý/gói

Core vẫn là **v5.0.0**. Bộ điều phối mới là **v4 / unit100**, dùng **Python 3, L4 GPU, High-RAM**. Cách tiếp tục được đơn giản hóa theo yêu cầu: chỉ ZIP kết quả hoàn chỉnh đã lưu và kiểm tra trên Drive mới là tiến độ bền vững. Phần xử lý dở trong một gói sẽ chạy lại từ đầu gói.

## File sử dụng

- Notebook: `Colab_V5_L4_134_Units.ipynb`.
- Runtime: `colab_orchestrator_v4_units_runtime.zip`, được notebook khóa SHA-256.
- Bộ upload sạch: **`drive_upload/`**. Chỉ chứa file cần đưa lên Drive; không có thư mục build, ảnh tạm hoặc metadata dựng gói.
- Kế hoạch/index gốc mới: `../uploads_134_unit100_20261022/UPLOAD_INDEX.json` và `plan/`.

Corpus có **27 PDF / 13.314 trang**:

| Đơn vị | Số lượng |
|---|---:|
| Gói đủ 100 trang | 133 |
| Gói cuối | 14 trang |
| Tổng input ZIP | 134 |
| Thành phần theo PDF trong các gói | 158 |

Gói đi qua ranh giới học phần có thể có hai thành phần, tổng vẫn không quá 100 trang. Không thay số trang nguồn, hash PDF, group học phần hoặc split. Mỗi trang xuất hiện đúng một lần trong phạm vi xử lý của kế hoạch.

**PDF gốc được giữ nguyên trong input để bảo toàn hash và khả năng truy nguồn.** Vì vậy, mở PDF bên trong ZIP có thể thấy toàn bộ học phần; native/render/parser/OCR/VLM chỉ nhận các trang được chỉ định trong manifest, tối đa 100 trang cộng lại. Đây là giới hạn công việc, không phải cắt lại và đổi hash PDF gốc. Bộ input hiện chiếm khoảng **4,32 GiB**, gói lớn nhất **148,72 MiB**; việc lặp lại PDF gốc giữa các gói làm tăng dung lượng so với 14 gói trước. Không dựng một ZIP tổng để upload qua kernel.

## Đưa lên Drive và chạy

1. Nếu phiên cũ còn chạy, chờ kết quả hiện tại lưu bền vững rồi dừng phiên đó trước khi dùng bộ mới. Không chạy hai queue cùng ghi một BASE hoặc cạnh tranh GPU.
2. Trong **Google Drive → MyDrive → BKQuiz_cpt_data**, upload **thư mục `drive_upload/inputs_134`**. Kết quả phải là `BKQuiz_cpt_data/inputs_134/UPLOAD_INDEX.json` và các ZIP cùng cấp. Giữ nguyên thư mục con `precompleted_results`.
3. Upload `drive_upload/colab_orchestrator_v4_units_runtime.zip` vào **BKQuiz_cpt_data**, bên ngoài `inputs_134`.
4. Mở notebook mới trên Colab thành một tài liệu riêng. Chọn **Python 3 → L4 GPU → High-RAM** nếu có tùy chọn. Notebook kiểm tra GPU/RAM thực tế; metadata không ép được Colab cấp máy.
5. Bật/kiểm tra **Edit → Notebook settings → Omit code cell output when saving**. Notebook đã đặt metadata tương ứng và chỉ hiển thị log ngắn.
6. Chạy cell 1–6 theo thứ tự. Cell 1 chỉ mount Drive. Cell 2 kiểm runtime và index. Cell 3 kiểm phần cứng/input. Cell 4 cài/khôi phục môi trường một lần và smoke test. Cell 5 đối chiếu kết quả rồi xử lý lần lượt gói thiếu.

Mặc định `MAX_UNITS=None`: tự xử lý liên tiếp các gói còn thiếu. Đặt `MAX_UNITS=1` để chạy thử một gói mới. Không upload từng file bằng widget, không nhập DA_TAI, không gọi `files.download()`.

| Vai trò | Đường dẫn |
|---|---|
| Input | `/content/drive/MyDrive/BKQuiz_cpt_data/inputs_134` |
| BASE mới | `/content/drive/MyDrive/BKQuiz_v5_unit100` |
| Tính toán/đóng ZIP | `/content/bkquiz_v5_units` |
| ZIP kết quả | `BKQuiz_v5_unit100/results/unit_XXXX/` |
| Biên nhận hoàn thành | `BKQuiz_v5_unit100/receipts/unit_XXXX.json` |
| Tổng hợp tiến độ | `BKQuiz_v5_unit100/queue_state.json` |
| Lượt đang chạy / lỗi | `current_attempt.json`, `failures/unit_XXXX/` |
| Tài nguyên và bước đang chạy | `telemetry/live_status.json`, `telemetry/events_*.jsonl` |

BASE v3, 14 input, cache và các kết quả trước được giữ nguyên. Không trỏ BASE mới vào BASE v3: đây là kế hoạch và cơ chế tiếp tục khác.

## Nhận lại kết quả đã làm trước

Đã kiểm tra hai ZIP kết quả v3 trên máy và tạo **7 kết quả gói tái sử dụng / 700 trang**, không suy luận model mới:

- `unit_0049`: IT3180.
- `unit_0096`–`unit_0101`: IT4653.

Chúng nằm trong `drive_upload/inputs_134/precompleted_results`. Khi chạy lần đầu, hệ thống kiểm hash, lưu chúng vào BASE mới và tạo biên nhận. Sau đó còn **127 gói / 12.614 trang** cần xử lý.

Hai kết quả cũ phủ 953 trang; chỉ 700 trang tạo thành các gói mới được phủ trọn. **253 trang còn lại nằm trong gói có phần chưa làm**, nên không được dùng để đánh dấu cả gói hoàn tất. Gói đó có thể phải chạy lại theo đơn vị giao dịch mới. Không giả lập tiến độ từ số input của kế hoạch 14 gói. Những kết quả cũ mới hơn chưa được cung cấp trên máy chưa được tự động nhận vào bộ tái sử dụng này.

Kết quả tái sử dụng giữ nguyên nội dung máy trả về và các lỗi/cờ cần kiểm duyệt. `legacy_provenance.json` lưu hash ZIP gốc và snapshot nguồn. Các ZIP v3 gốc vẫn được giữ. Hoàn thành xử lý không đồng nghĩa dữ liệu đã sạch hoặc đã được con người xác nhận.

## Khi mất kết nối hoặc khởi động lại

Chạy lại notebook với **cùng BASE, index và bộ input**:

1. Đọc biên nhận từng gói, kiểm tra file ZIP thực tế và SHA-256.
2. Bỏ qua mọi gói hợp lệ, kể cả khi danh sách có khoảng trống. Không dùng một biến “đến gói N” làm bằng chứng duy nhất.
3. Nếu ZIP đã lưu xong nhưng VM ngắt trước khi ghi biên nhận, kiểm tra nội dung ZIP và nhận lại nó, không chạy model lại.
4. Nếu thiếu ZIP, sai hash, sai nguồn/kế hoạch, chỉ có `.partial`/`.next` hoặc ZIP chẩn đoán, gói vẫn chưa hoàn thành.
5. Dọn phần công việc cục bộ do bộ điều phối tạo của gói dở, rồi chạy lại từ input gói đó. Không replay checkpoint nội bộ từ các gói trước. Không xóa kết quả/biên nhận hợp lệ trên Drive.

Quét hash nhiều ZIP đã lưu có thể mất thời gian đọc Drive; console hiển thị `CHECK SAVED`. Đây không phải chạy lại inference. Nếu chỉ giao diện báo Connecting mà VM vẫn lưu được ZIP, ZIP ấy vẫn được nhận khi chạy lại. Không cần chủ động làm mất kết quả đang lưu chỉ vì giao diện ngắt.

Mỗi ZIP được đóng trên `/content`, sao chép sang Drive qua file tạm, kiểm hash đích rồi đổi tên cuối; sau đó mới ghi biên nhận. Vẫn có thể phải chạy lại gói hiện tại nếu VM mất trước khi ZIP cuối hoàn chỉnh. Tải kết quả bằng **giao diện Google Drive**, độc lập với kernel.

## Môi trường, model và dữ liệu

- Giữ PyMuPDF, PaddleOCR/PP-StructureV3, PP-FormulaNet-S, Docling và **Qwen2.5-VL-7B-Instruct NF4** theo các phiên bản đã khóa của v3. Không đổi prompt sang JSON phức tạp.
- Venv được cài/khôi phục một lần trong mỗi phiên Colab. Phiên VM mới vẫn cần khôi phục môi trường; bộ điều phối không thể giữ RAM của VM đã mất.
- Qwen và Docling dùng worker thường trú qua các gói. Qwen được chuyển về RAM CPU khi Paddle cần GPU. Các worker Paddle đóng sau từng role để tránh giữ nhiều model GPU cùng lúc.
- Native chỉ render phạm vi gói; các bước model chia nhóm tối đa 20 trang trong bộ nhớ. Các file trung gian chỉ ở `/content`. Chỉ kết quả gói cuối là điểm tiếp tục trên Drive.
- Phân bổ ngân sách VLM mục tiêu 5% theo tổng số trang mỗi gói, chia cho thành phần PDF. Vùng chưa được chọn vẫn được giữ; không tự bỏ thông tin vì ít chữ. Ngân sách gói nhỏ có làm tròn. Kết quả cũ được tái sử dụng giữ chính sách routing cũ, không giả vờ đã chạy lại theo routing mới.
- Quan sát VLM thành công có trong seed được dùng lại khi khớp chính xác cache key của ảnh, crop, bbox, ngữ cảnh, prompt, model/config và nguồn. Không sửa nội dung hoặc nâng trạng thái verified.
- Dataset/CPT, dedup toàn corpus, split audit và human review vẫn là các gate riêng. ZIP hoàn thành có thể chứa lỗi OCR/table/formula hoặc quan sát chưa chắc chắn.

## Nhập kết quả về máy

Tải ZIP của các gói từ Drive. Dùng importer mới vì snapshot các gói là độc lập:

```powershell
AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe -X utf8 AI\data_preprocessing\colab_orchestrator_v4\import_units.py --index AI\data_preprocessing\uploads_134_unit100_20261022\UPLOAD_INDEX.json --results "D:\duong_dan\ket_qua_1.zip" "D:\duong_dan\ket_qua_2.zip" --check-only
```

Bỏ `--check-only` để nhập thật. Importer kiểm nguồn/hash, giữ ZIP gốc, gộp record theo học phần/trang, giữ nguyên SQLite human review và từ chối ghi đè record/asset xung đột. Không yêu cầu snapshot sau chứa toàn bộ snapshot trước. Kết quả vào `AI/data_preprocessing/workspaces/unit100_20261022/runs/<document_id>`; dùng app review v5 với run tương ứng. Không tự xuất CPT hay tự phê duyệt VLM.

## Bằng chứng

- `INPUT_VALIDATION_20261022.json`: hash/inventory của 134 ZIP, đủ 13.314 trang, không trùng/thiếu và kiểm tra 7 kết quả tái sử dụng.
- `test_evidence_20261022.json`, `tests_20261022.txt`: kiểm thử ngắt phiên, ZIP trước biên nhận, khoảng trống tiến độ, hỏng/mất file, scoped native/layout, cache VLM, worker thường trú và nhập dữ liệu giữ SQLite.
- `RUNTIME_RELEASE.json`: pin runtime và notebook.
- Chưa chạy GPU Colab thật trong đợt triển khai này; kiểm thử model dùng backend giả, còn native/PDF/hash/import dùng code thực. Không kết luận hết Connecting hoặc chất lượng toàn corpus đã đạt.
