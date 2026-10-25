# Hai đợt duyệt đề thi

1. Trên web cũ, mở mục Đề thi SFT / Đợt 1, đối chiếu ảnh và chọn **Dùng ảnh này cho VLM**, **Loại ảnh** hoặc **Tạm hoãn**. Ảnh được chọn thủ công và ảnh auto_vlm theo chính sách được phép mới được xuất; native/OCR text được xử lý trực tiếp, không gửi lại cho VLM.
2. Bấm **Xuất ảnh đủ điều kiện sang Colab**. Các ZIP trong `colab/exports/` chứa ảnh và manifest đã khóa hash, mỗi gói tối đa 100 ảnh và 128 MiB. Bộ xuất ghi ZIP theo luồng, không nạp tất cả ảnh đã chọn vào RAM. Không upload `assets/` hoặc PDF gốc lên Colab.
3. Upload `sft_vlm_runtime_c0901ff84e1c1ace.zip` vào `MyDrive/BKQuiz_SFT_EXAMS`, upload các ZIP ảnh đã duyệt vào `MyDrive/BKQuiz_SFT_EXAMS/inputs`. Mở `BKQuiz_SFT_Exams_VLM_Round2.ipynb`, chọn L4 + High-RAM và chạy từng cell.
4. ZIP kết quả trong `MyDrive/BKQuiz_SFT_EXAMS/results` có dạng `sft_*_results_*.zip`. Tải ZIP về máy và bấm **Nhập ZIP kết quả VLM** ở web.
5. Đợt 2 so ảnh nguồn với câu đã tách. Chọn **Chấp nhận câu hỏi**, sửa hoặc **Loại câu hỏi**; câu không có khóa đáp án vẫn giữ trạng thái thiếu, VLM không tự giải. Chỉ câu được duyệt đợt 2 mới thuộc đầu vào xuất SFT sau này.

Nếu đổi lựa chọn ảnh sau lần xuất, hãy xuất input mới và chuyển các ZIP input đã cũ ra khỏi thư mục Colab `inputs` trước khi chạy. Không tự xóa PDF gốc hoặc lịch sử duyệt. Input là snapshot tại lúc xuất; importer sẽ từ chối kết quả của ảnh đã bị thu hồi quyết định hoặc đổi hash.

Runtime: Qwen/Qwen2.5-VL-7B-Instruct revision cc594898137f460bfe9f0759e9844b3ce807cfb5, NF4/SDPA; torch2.6.0, torchvision0.21.0, transformers4.57.6, accelerate1.12.0, bitsandbytes0.48.1, Pillow11.3.0. Đổi tác vụ từ mô tả vùng sang OCR toàn trang dùng ngân sách visual_tokens2048/max_new_tokens4096, được ghi riêng và **chưa chạy GPU để đo chất lượng/tốc độ**.

Runtime SHA-256: `066e95d468ac5a1508a02ae8d4f826cf4f4f89189d91030c72eccbefa2e688f7`. Không upload/chạy model nếu không có ảnh được phép theo quyết định thủ công hoặc chính sách định tuyến tự động đã chốt. Các API xuất/nhập không tự tạo quyết định con người. ZIP lỗi, input không biết nguồn, ảnh đổi hash hoặc ảnh không còn được duyệt sẽ bị từ chối. Kết quả máy, lỗi và raw output được lưu để đối chiếu, không ghi đè review CPT trước đây.
