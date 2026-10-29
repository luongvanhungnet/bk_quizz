# Qwen continued pretraining

Đã chọn **Qwen3 1.7B** cho đợt CPT pilot. Bộ thiết lập Google Colab Pro nằm trong [colab_qwen3_1_7b](colab_qwen3_1_7b/HUONG_DAN_COLAB.md):

- [Notebook](colab_qwen3_1_7b/Qwen3_1_7B_IT3170_CPT.ipynb)
- [Gói mã và dữ liệu để upload](colab_qwen3_1_7b/qwen3_it3170_colab.zip)
- [Hướng dẫn train, resume và kiểm tra trước/sau](colab_qwen3_1_7b/HUONG_DAN_COLAB.md)

Mặc định CPT bằng QLoRA trên 264 mẫu accepted, tokenize lại với Qwen3; không dùng file packed Qwen2.5 cũ. Chưa chạy GPU Colab trong bước thiết lập này.

Sau khi train và `EXPORT_MERGED=True` trên Colab, dùng [hướng dẫn tải về, chạy Ollama và so sánh](local_qwen3/HUONG_DAN_CHAY_VA_SO_SANH.md). Thư mục `local_qwen3` có helper import bằng tag mới, benchmark cùng sáu prompt và công cụ đọc cặp JSON trước/sau đã xuất từ Colab.

Pipeline và dữ liệu thử nghiệm từ một PDF Thuật toán ứng dụng nằm trong [data_preprocessing](data_preprocessing/README.md).

- [Báo cáo lần chạy](data_preprocessing/outputs/it3170/REPORT.md)
- [JSONL text cho CPT](data_preprocessing/outputs/it3170/cpt/train.jsonl)
- [Metadata nguồn của mẫu train](data_preprocessing/outputs/it3170/cpt/train.metadata.jsonl)
- [Dữ liệu chuẩn hóa mọi trang, có cờ chất lượng](data_preprocessing/outputs/it3170/normalized.jsonl)
- [Hàng đợi rà soát](data_preprocessing/outputs/it3170/review_queue.jsonl)

Tập train là phần đã vượt qua kiểm định. Các công thức/hình/bảng chưa xác minh vẫn được giữ để duyệt tiếp. Chưa huấn luyện model trong bước xử lý dữ liệu này.
