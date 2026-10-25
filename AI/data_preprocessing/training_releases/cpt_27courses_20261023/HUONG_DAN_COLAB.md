# Train CPT Qwen3 1.7B trên Colab — 27 học phần

1. Trong Drive **MyDrive/BKQuiz_CPT**, dùng cặp mới `BKQuiz_Qwen3_1_7B_CPT_27courses.ipynb` và `bkquiz_cpt_27courses_20261023.zip`. Gói IT3170 cũ vẫn giữ riêng; không dùng ZIP cũ cho notebook mới.
2. Mở notebook bằng Google Colab. Chọn **Runtime → Change runtime type → Python 3 / GPU**; ưu tiên L4. Chạy từng cell từ trên xuống, mount đúng Drive và chấp nhận quyền truy cập khi Colab yêu cầu.
3. Notebook kiểm hash ZIP/nội dung, tạo venv, kiểm GPU và các thư viện đã khóa, tokenize đúng revision Qwen3 rồi chạy smoke 2 bước. Nếu smoke đạt, cell CPT chạy 1 epoch từ model gốc. Không dùng adapter smoke cho train chính.
4. Kết quả ở **MyDrive/BKQuiz_CPT/runs/cpt_27courses_20261023_001/train/adapter**; checkpoint đầy đủ và optimizer ở thư mục train. Giữ `completed.json`, `environment.json`, `pip-freeze.txt` và các metrics cùng adapter.

Mất phiên: chạy lại mount/extract/install/prepare, giữ RUN_NAME, đặt `RESUME_TRAIN=True`. Trainer chọn checkpoint đầy đủ gần nhất; không đổi dữ liệu, code, config hoặc phiên bản thư viện khi resume. Đổi RUN_NAME để thử cấu hình khác. Không tái sử dụng thư mục output cũ cho một thí nghiệm mới.

Mặc định: Qwen/Qwen3-1.7B, QLoRA NF4 (chỉ train LoRA), sequence 1024, batch 1, accumulation 8, LR 2e-5, warmup 3%, cosine, 1 epoch, r8/alpha16/dropout0.05. GPU/runtime thực tế do Colab cấp; smoke mới xác nhận khả năng chạy trên phiên của bạn.

`RUN_PROBES=False` và `EXPORT_MERGED=False` mặc định. Bật probe để xuất cùng sáu tình huống IT3170 trước/sau; chúng không phải benchmark độc lập. Bật merge khi cần model HF FP16 và còn đủ RAM/Drive. Không tự upload model lên Hugging Face; chưa tạo GGUF/Ollama ở bước này.

Đọc **AUDIT_REPORT.md** trước lượt train: còn rủi ro OCR/công thức trong nhóm chấp nhận mặc định. Chỉ train một epoch đầu; loss giảm không tự chứng minh model sinh quiz tốt hơn. Khi chạy xong, ngắt runtime để dừng tiêu thụ tài nguyên.

Bản này đã kiểm CPU: 37,133 mẫu, 3,235,037 token gồm EOS, 3,160 sequence; mặc định 1 epoch tương ứng 395 optimizer steps. Số liệu này không phải kết quả train GPU.
