# BKQuiz: bộ SFT chỉ gồm trang native đã hoàn tất

Lấy một tập con nguyên vẹn từ release đề thi 742 câu, loại toàn bộ câu chạm bất kỳ trang nào
còn trong luồng LLM/VLM/duyệt thủ công, xét mọi nguồn của câu. Không dùng các câu TXT đang
chờ duyệt, đầu ra teacher, ảnh cần xử lý thêm hoặc dữ liệu CPT dạng văn bản thô làm nhãn SFT.
Quyết định loại là chính sách của chủ dữ liệu, không tạo phê duyệt giả và không xóa nguồn gốc.

Giữ nguyên messages, đáp án, giải thích đã hoàn tất, nhóm câu hỏi và train/validation/test cũ.
Tập này huấn luyện chuyển Q&A có đáp án thành quiz JSON có căn cứ; chưa dạy đầy đủ khả năng
đọc giáo trình rồi tự sáng tạo câu hỏi mới. Lời giải dẫn đáp án nguồn còn ngắn. Các lời giải
Codex có căn cứ đã hoàn tất trước đây được giữ nguyên và đánh dấu đúng nguồn gốc; không gọi LLM mới.
human_verified/expert_semantically_verified được giữ nguyên; đáp án nguồn chưa phải expert gold.

Chỉ token assistant content và EOS im_end chịu loss; prompt, think-prefix và padding là -100.
Không truncate, không packing các mẫu chat; tokenizer Qwen3 chính xác theo SHA256 release gốc.
Tệp PDF có thể dùng chung giữa split, nhưng nhóm câu hỏi không chồng split. Đây không phải
phép đo tổng quát hóa trên tài liệu chưa thấy. Không dùng test để chọn checkpoint/hyperparameter.

Student: Qwen3-1.7B đúng revision cùng adapter CPT27 đã kiểm tra hash. Notebook train tiếp
chính adapter đó với QLoRA. Kết quả adapter cuối chứa CPT+SFT; nạp cùng base, không chồng lại
adapter CPT ban đầu. Không có teacher7B/VLM hoặc bước sinh dữ liệu trong notebook này.
Huấn luyện GPU chưa được chạy tại máy chuẩn bị; người dùng tự chạy Colab.
