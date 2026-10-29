# Bắt đầu v5 — 134 gói độc lập, tối đa 100 trang/gói

Core **v5.0.0** giữ nguyên. Bộ điều phối mặc định: **v4 / unit100**, chạy **L4 GPU / High-RAM / Python 3**.

1. Dùng bộ file trong [drive_upload](colab_orchestrator_v4/drive_upload). Upload **thư mục inputs_134 bên trong** vào **MyDrive/BKQuiz_cpt_data**, tạo đường dẫn **BKQuiz_cpt_data/inputs_134**. Giữ cả thư mục con **precompleted_results**.
2. Upload [runtime ZIP](colab_orchestrator_v4/colab_orchestrator_v4_units_runtime.zip) vào **MyDrive/BKQuiz_cpt_data**, bên ngoài **inputs_134**.
3. Mở [notebook 134 gói](colab_orchestrator_v4/Colab_V5_L4_134_Units.ipynb) thành một tài liệu riêng. Chọn Python 3/L4/High-RAM, không lưu code-cell output vào notebook.
4. Chạy các cell theo thứ tự. Xem [hướng dẫn vận hành và nhập kết quả](colab_orchestrator_v4/README.md).

**133 gói × 100 trang + gói cuối 14 trang = 13.314 trang.** Gói ranh giới có thể chứa hai học phần; trang và hash nguồn vẫn riêng. PDF gốc được giữ để truy nguồn, nhưng native/render/model chỉ xử lý phạm vi trang của gói.

Kết quả từng gói được đóng trên **/content**, sao chép và kiểm hash trên Drive rồi mới ghi biên nhận. Khi khởi động lại, bỏ qua mọi gói đã lưu hợp lệ; gói thiếu/hỏng hoặc đang dở chạy lại từ input. ZIP đã lưu xong nhưng chưa ghi biên nhận được kiểm tra và nhận lại. Không replay checkpoint nội bộ hoặc suy tiến độ chỉ từ một bộ đếm.

Đã chuẩn bị **7 gói kết quả tái sử dụng / 700 trang** từ hai kết quả v3 đã kiểm hash. Sau khi nhận lại chúng, còn **127 gói / 12.614 trang**. Không tự nâng nội dung/cờ lỗi cũ thành verified. Venv cài/khôi phục một lần mỗi phiên; Qwen/Docling tái sử dụng qua các gói. **MAX_UNITS=None** xử lý liên tiếp; đặt **1** để thử một gói.

BASE mới: **MyDrive/BKQuiz_v5_unit100**. Tải kết quả trong **results/unit_XXXX/** bằng giao diện Drive. **receipts/**, **queue_state.json**, **current_attempt.json**, **telemetry/** hỗ trợ theo dõi. Không upload/download qua widget notebook và không nhập DA_TAI.

Giữ nguyên 14 input, BASE và kết quả v3. Không chạy hai phiên ghi cùng BASE và không trỏ BASE unit100 vào BASE v3. Nếu giao diện Connecting nhưng VM vẫn lưu được ZIP, file hoàn chỉnh ấy vẫn được nhận khi tiếp tục.

Các gate chất lượng, human review, khử trùng lặp/split toàn corpus và xuất CPT vẫn giữ nguyên. ZIP xử lý xong có thể chứa lỗi máy cần kiểm duyệt. Xem [kiểm tra input](colab_orchestrator_v4/INPUT_VALIDATION_20261022.json); chưa benchmark GPU Colab thật.

Các bộ [v3](colab_orchestrator_v3/README.md), [v2](colab_orchestrator_v2/README.md), [v1](colab_orchestrator/README.md) được giữ để đối chiếu.
