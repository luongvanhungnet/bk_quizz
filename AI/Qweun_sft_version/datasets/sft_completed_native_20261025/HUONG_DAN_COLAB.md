# Chạy SFT trên Colab

Hai tệp cần dùng: bkquiz_completed_sft_20261025.zip và BKQuiz_Qwen3_1_7B_Completed_SFT.ipynb.
Đặt cả hai trong MyDrive/BKQuiz_CPT/SFT_COMPLETED_NATIVE_20261025.
Mở notebook, chọn Runtime > Change runtime type > T4 GPU rồi Run all.
Notebook tự kiểm tra ZIP, dữ liệu, các trang bị loại, tokenizer và adapter CPT27 trước khi tải base model.
Không có bước xử lý VLM, OCR, teacher hoặc duyệt thủ công.

Dataset có361câu thuộc8môn:281train,40validation,40test; nguồn181trang đã hoàn tất.
Bộ dữ liệu học biên soạn Q&A có đáp án thành quiz JSON; không phải bộ theory-to-new-quiz có lời giải sâu.
Giữ nguyên các lời giải đã hoàn tất và cờ nguồn gốc. Phần lớn lời giải là dẫn đáp án nguồn.

Mặc định1epoch, LR2e-5, batch1, accumulation8; train tiếp adapter CPT27 cùng pinnedQwen3-1.7B.
Loss chỉ trên assistant và EOS, không trên prompt/padding. T4 dùngFP16. Test mặc định không đánh giá.
RUN_SMOKE=False; có thể bật kiểm tra2steps trong thư mụcsmoke riêng nếu cần.
Giữ RUN_NAME và RESUME_TRAIN=True khi chạy lại cùng dữ liệu/code/thư viện để tiếp tục checkpoint.
Nếu ngắt trước checkpoint đầu tiên hoặc đổi cấu hình, chọn RUN_NAME mới.
Kết quả nằm trong Drive/runs/RUN_NAME/train, ZIP sft_completed_adapter.zip tự tải về ở ô cuối.
Đây là adapter hoàn chỉnh CPT+SFT: nạp một lần lên đúng base, không chồng lại adapter CPT cũ.
Chưa có lượt trainGPU được chạy khi chuẩn bị gói này.
