# Chạy v3 trên L4 / High-RAM / Python 3

**Bản sửa 22/10:** dùng `Colab_V5_L4_Stable.ipynb` cùng `colab_orchestrator_v3_l4_stable_runtime.zip`. Nếu phiên cũ đang Connecting nhưng telemetry vẫn cập nhật, xem [chẩn đoán và cách tiếp tục an toàn](CONNECTING_DIAGNOSIS_20261022.md) trước khi chạy một phiên khác. Không dùng hai phiên ghi cùng BASE.

1. Khi input đang chạy đã lưu bền vững, đóng phiên tính toán cũ. Mở `Colab_V5_L4_Stable.ipynb` thành một bản có tên riêng trên Colab; bật **Edit → Notebook settings → Omit code cell output when saving**.
2. Vào **Runtime → Change runtime type → Python 3 → L4 GPU**. Chọn **High-RAM** nếu giao diện cho chọn. L4 có thể có sẵn một cấu hình RAM duy nhất; cell kiểm tra phải xác nhận ít nhất 40 GiB RAM vật lý.
3. Thêm **`colab_orchestrator_v3_l4_stable_runtime.zip`** vào `MyDrive/BKQuiz_cpt_data` cùng 14 input hiện có. Đây là file runtime mới; không đổi tên hoặc đóng lại 14 ZIP input. Bản L4 trước sửa được giữ trong `releases/l4_before_stability_20261022`; bản trước L4 trong `releases/drive_v3_before_l4_20261021`.
4. Chạy cell 1–3. Giữ `BASE=MyDrive/BKQuiz_v5_drive_v3` để tiếp tục queue v3 hiện tại; `PREVIOUS_BASE=None` khi đã chạy v3. Cell 3 kiểm tra GPU L4, Python 3.10–3.13, RAM tổng ≥40 GiB, RAM khả dụng ≥12 GiB và VRAM trống ≥12 GiB. **Python 3** là loại runtime; không có nghĩa phải đổi sang một Python minor cụ thể.
5. Cell 4 khôi phục môi trường một lần, chạy smoke test CUDA Paddle/OCR/layout, Torch/NF4 và Docling một trang. Không cài lại CUDA toolkit hoặc đổi quantization/model chỉ vì đổi GPU. Docling dùng `BASE/docling_hf_cache_l4` riêng; lần đầu có thể tải lại trọng số. Cache cũ gây `header too large` không bị xóa/ghi đè.
6. Nếu preflight đạt, chạy cell 5. `MAX_INPUTS=1` để kiểm tra một input tiếp theo, sau đó có thể đặt `None`. Batch vẫn 20 trang để giữ tương thích checkpoint. Kết quả tải riêng bằng Google Drive từ `BASE/downloads`.

Nếu preflight lỗi, mở `BASE/preflight_runs/<lượt>/summary.json` và file `.log`/`.json` của role lỗi. Các lỗi được giữ đầy đủ; notebook dừng trước khi chạy hàng loạt. Nếu GPU không phải L4 hoặc RAM thấp, chọn lại runtime; không bỏ assert để làm kết quả trông đạt. Khi không có L4 hoặc không đủ quota, notebook không thể ép Colab cấp đúng máy.

Cell kiểm tra không thử generate Qwen 7B đầy đủ để tránh nạp model lớn hai lần; nó kiểm tra CUDA/NF4. Qwen được nạp khi có yêu cầu VLM thật, và giữ qua các input theo `KEEP_MODEL_RESIDENT=True`. Kết quả đầu ra vẫn phải theo gate kiểm duyệt v5.

`hardware_profile.json`, kết quả/traceback preflight và audit hash trọng số Docling được đưa vào ZIP xuất mới. Telemetry mới ghi thêm tên GPU, để lần kiểm tra sau phân biệt được máy đã cấp thực tế với lựa chọn trong giao diện.

Giữ BASE cũ chỉ giúp tiếp tục tiến độ và dùng lại cache. **Không tự sửa hoặc chạy lại lỗi OCR/Table/Docling đã ghi ở input 01/02**. Sửa các lỗi cũ cần một đợt chạy lại có kiểm soát, giữ nguyên kết quả gốc. Không dùng `PREVIOUS_BASE` của migration v2 để trỏ vào BASE v3.

Chi tiết kiểm tra dữ liệu có trong `RESULT_REVIEW_20261021.md`; bằng chứng số liệu ở `colab_orchestrator_v3_result/inspection/RESULT_ANALYSIS.json`. Chưa đo tốc độ và chưa xác nhận probe thành công trên L4 thật.
