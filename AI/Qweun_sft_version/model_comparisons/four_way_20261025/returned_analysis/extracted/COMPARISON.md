# So sánh bốn phiên bản

Cùng test40; source-key agreement không phải expert accuracy. Không dùng test để chọn checkpoint.

| Phiên bản | Test NLL ↓ | PPL ↓ | Khớp đáp án nguồn | JSON + citations hợp lệ | tokens/s |
|---|---:|---:|---:|---:|---:|
| base | 0.7575 | 2.133 | 20/40 | 0/12 | 12.6 |
| cpt | 0.4869 | 1.627 | 8/40 | 0/12 | 8.0 |
| sft | 0.3565 | 1.428 | 18/40 | 4/12 | 8.1 |
| cpt_sft | 0.2549 | 1.290 | 1/40 | 2/12 | 8.4 |

NLL đo assistant theo ngữ cảnh có đáp án nguồn. MCQ đo đóng sách, giữ thứ tự phương án nguồn; có thể chịu thiên lệch vị trí.
JSON/citations chỉ là kiểm tra cấu trúc và trích dẫn nguyên văn; chưa đánh giá lời giải sâu/độ đúng học thuật. Duyệt blind_review.json trước khi mở key.
Test chỉ40 câu và có PDF cùng nguồn với train; một seed; chưa chứng minh khái quát sang giáo trình/tài liệu mới.
Các đáp án nguồn chưa được chuyên gia xác nhận. Các bản đều nạp NF4 chung; benchmark này đo adapter, không đo bản GGUF triển khai.
