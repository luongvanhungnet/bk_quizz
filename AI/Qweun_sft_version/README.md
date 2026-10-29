# SFT Qwen3 cho BKQuiz

[Báo cáo lịch sử tiền xử lý SFT](BAO_CAO_LICH_SU_TIEN_XU_LY_SFT.md), cập nhật ngày 28/10/2026: tổng hợp từng phiên bản, các nhánh thử nghiệm, số liệu và thay đổi đến SFT-v2 curated.

Bản native chỉ giữ trang đã hoàn tất: **361 câu từ 181 trang đã hoàn tất**, loại toàn bộ trang còn cần LLM/VLM/duyệt. Input có sẵn adapter CPT27 và tokenizer; notebook SFT không có bước sinh dữ liệu. Xem [hướng dẫn](datasets/sft_completed_native_20261025/HUONG_DAN_COLAB.md), [notebook Colab](https://colab.research.google.com/drive/1Xg2pD1lRbMSlzQoh6MgiOtm3tnSct6W7) và [thư mục Drive](https://drive.google.com/drive/folders/1diXskMkNTK2yAIKUsAusawSJGH8OTmFi). Gói chia 281train/40validation/40test, tiếp tục chính adapter Qwen3-1.7B CPT27.

Pipeline mới **lý thuyết → câu hỏi mới + lời giải sư phạm bằng Qwen2.5-7B-Instruct** nằm trong [pedagogy_tools/README.md](pedagogy_tools/README.md). Web duyệt: http://127.0.0.1:8765/sft/pedagogy/ . Teacher giữ riêng với student Qwen3-1.7B + CPT27; chỉ các kết quả được người dùng chấp nhận mới xuất SFT.

Bộ xử lý đề thi ngày 24/10/2026 nằm trong `data_preparation/`; dữ liệu, nguồn gốc và báo cáo nằm trong `datasets/sft_exams_20261024/`.

Đọc `datasets/sft_exams_20261024/DATASET_CARD.md` trước khi sử dụng. Tập chính chuyển Q&A tham chiếu có đáp án thành quiz JSON có trích dẫn; `rationale_core/` là tập pilot nhỏ có giải thích. `document_holdout/` giữ cách chia độc lập theo PDF. Câu thiếu đáp án, phụ thuộc hình, lỗi PDF hoặc nhãn sai đã phát hiện được lưu riêng.

Đích tương thích là Qwen3 1.7B tiếp nối adapter CPT 27 môn; đây là bước chuẩn bị dữ liệu, chưa chạy SFT hoặc thay model đang phục vụ. Dữ liệu tự động dựa trên khóa đáp án nguồn chưa được chuyên gia xác minh toàn bộ. Xem `MODEL_PROVENANCE.json`, `validation_report.json` và `audit/` trong release để phân biệt kiểm tra kỹ thuật, đối chiếu mẫu và xác minh kiến thức.
