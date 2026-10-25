# Báo cáo dữ liệu CPT Thuật toán ứng dụng

Ngày: 17/10/2026 (Asia/Bangkok).

Đầu vào là **một PDF IT3170**, gồm hai bộ bài giảng đã gộp. File nguồn được giữ nguyên. Mã học phần kế thừa từ manifest với trạng thái suy luận (`inferred`).

## Kết quả thực tế

| Hạng mục | Kết quả |
|---|---:|
| Trang PDF được trích xuất và chuẩn hóa | 1,060 |
| Trang chạy mô-đun layout/công thức Paddle | 1,060 |
| Trang chạy PP-StructureV3 đầy đủ | 86 |
| Trang đủ điều kiện trước loại trùng | 288 |
| Mẫu CPT sau loại trùng | 264 |
| Trang cần rà soát | 753 |
| Trang logo/bìa/cảm ơn đã xem và loại khỏi train | 19 |
| Bản trùng chính xác bỏ khỏi train | 24 |
| Cặp gần trùng, giữ cùng split | 62 |
| Bản ghi vùng công thức (gồm ứng viên chưa xác minh) | 1,038 |
| Bản ghi bảng (gồm ứng viên chưa xác minh) | 18 |
| Trang được Codex kiểm tra ảnh trực tiếp | 26 |
| Token sau thêm EOS | 29,771 |
| Chuỗi packed, tối đa 2048 token | 15 |

Tokenizer: `Qwen/Qwen2.5-7B`. Revision đã phân giải: `d149729398750b98c0af14eb82c78cfe92750796`. EOS: `<|endoftext|>` / ID `151643`. Không tải trọng số hay huấn luyện model ở bước này.

Tệp dùng huấn luyện: [cpt/train.jsonl](cpt/train.jsonl) hoặc [cpt/train.packed.jsonl](cpt/train.packed.jsonl). Metadata nguồn: [cpt/train.metadata.jsonl](cpt/train.metadata.jsonl). Dataset đầy đủ trạng thái: [normalized.jsonl](normalized.jsonl).

## Độ bao phủ và giới hạn

**Chưa phải toàn bộ 1.060 trang đều được chuyển thành dữ liệu train đã sạch.** Tất cả trang vẫn có trong lớp chuẩn hóa. Các mẫu chứa hình/công thức/bảng hoặc glyph chưa xác minh được giữ trong [review_queue.jsonl](review_queue.jsonl).

Người dùng chọn Qwen2.5 Base và chưa có endpoint VLM. Các ví dụ hình/bảng đã kiểm tra gồm trang 20 (số mũ và tràn số), 49/51 (bảng SMS), 300 (hướng cung), 500 (trọng số/cạnh đỏ của Kruskal), 753 (khung văn bản bị detector nhầm thành bảng), 800 (code). Những kiểm tra này do Codex đọc ảnh, không phải bộ gold được chuyên gia/người độc lập gán nhãn. Các hình khác giữ trạng thái pending.

Tập này chỉ có train. Validation/test rỗng theo đơn vị tài liệu để tránh chia các phiên bản gần trùng sang hai tập. Cần nguồn đánh giá độc lập trước khi báo cáo chất lượng model.

## Chất lượng và kiểm tra

- Source Traceability theo ánh xạ trang: 100.00%.
- Duplicate Rate trong các mẫu đủ điều kiện: 8.33% trước khử trùng lặp; train sau xử lý không có bản text trùng chính xác.
- CER/WER toàn tập, Formula Accuracy, Diagram Fact Precision, Information Coverage: chưa đo vì chưa có ground truth độc lập. Không thay bằng điểm tự đánh giá của model.
- QA phụ: hai trang 20 và 100 được chép từ ảnh bởi Codex, so với native text trước khi ghi đè annotation; xem [qa/reference_metrics.json](qa/reference_metrics.json). Kết quả chỉ áp dụng cho hai trang này.
- Kiểm tra tính toàn vẹn: **PASS**, xem [validation.json](validation.json). Bao gồm SHA-256 PDF/ảnh, số trang, metadata, PII email, cổng chất lượng, split, labels và đối chiếu tất cả token sau packing.

Các nguyên nhân cần rà soát:

| Cờ | Số trang |
|---|---:|
| `corrupt_glyphs` | 47 |
| `formula_prediction_requires_verification` | 143 |
| `math_requires_verification` | 337 |
| `no_text_pending_OCR_or_vision` | 1 |
| `sparse_page_needs_visual_review` | 57 |
| `table_requires_verification` | 16 |
| `visual_requires_interpretation` | 605 |

Một trang có thể mang nhiều cờ. Điểm confidence không được hiệu chuẩn được để null; điểm detector/OCR do backend trả về được lưu riêng.

## Phát hiện kỹ thuật

- Khoảng trắng tiếng Việt được phục hồi từ khoảng cách ký tự: `Sửdụng` → `Sử dụng`.
- Chỉ số trên được giữ: `1018` trong bản text thô → `10^{18}` khi PDF xác nhận baseline/cờ superscript. Những trường hợp chưa chắc vẫn cần đối chiếu.
- Ghép các dòng code bị chia block và giữ thụt lề. Dự đoán công thức chồng lên vùng native code được ghi nhận là ứng viên bị bỏ qua.
- PP-StructureV3 nhận dạng đúng hai công thức ở ví dụ trang 20, nhưng có lỗi ở công thức trang 650 và từng nhầm code trang 800 là toán. Vì vậy không đưa mọi LaTeX OCR vào train tự động.
- Dùng PaddlePaddle 3.2.2 sau khi gặp lỗi oneDNN/PIR trên 3.3.1; các mô-đun được thực thi trên CPU.
- Alphabet thực tế của model Latin OCR thiếu một số chữ tiếng Việt có dấu; xem [ocr_capabilities.json](ocr_capabilities.json). Không dùng đầu ra OCR này thay chữ nguồn trong train khi chưa đối chiếu.

Nhãn layout phát hiện (số **vùng**, không phải số trang):

| Nhãn | Số vùng |
|---|---:|
| `abstract` | 1 |
| `algorithm` | 151 |
| `chart` | 58 |
| `chart_title` | 58 |
| `doc_title` | 40 |
| `figure_title` | 3 |
| `footer` | 950 |
| `footer_image` | 649 |
| `footnote` | 4 |
| `formula` | 245 |
| `header` | 1 |
| `image` | 229 |
| `number` | 740 |
| `paragraph_title` | 426 |
| `seal` | 1 |
| `table` | 19 |
| `text` | 1753 |

Cách cài đặt, chạy lại, duyệt thêm mẫu và dùng dữ liệu: [README](../../README.md).
