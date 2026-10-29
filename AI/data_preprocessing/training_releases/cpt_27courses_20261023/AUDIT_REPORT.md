# Kiểm tra và xuất CPT 27 học phần — 23/10/2026

Đã kiểm tra ngẫu nhiên phân tầng **24 vùng**: 6 VLM đã chấp nhận, 6 text mặc định, 4 OCR vùng ảnh, 4 bảng/công thức và 4 VLM đã loại. Seed **20261023** được khóa trước khi đọc mẫu. Chọn bằng SHA-256 của seed/nhóm/học phần/ID, không thay mẫu sau khi thấy lỗi. Đã đối chiếu crop và ảnh trang; 72 tham chiếu ảnh của mẫu khớp SHA-256.

Trong 20 ứng viên train: **10 mẫu không thấy lỗi đáng kể, 4 mẫu dùng được nhưng còn nhiễu định dạng hoặc mô tả đơn giản, 6 mẫu không phù hợp**. Sáu mẫu gồm OCR/font hỏng (S08), trang logo (S12), mất/sai ký hiệu toán (S14/S17/S19/S20). Đã cách ly sáu ID cùng bản trùng chính xác về nội dung; tổng vùng cách ly do audit: **30**. Bốn mẫu VLM bị chủ dữ liệu loại vẫn bị loại. Mô tả S24 có phần khớp nguồn nhưng không đảo quyết định loại đã lưu.

Đây là kiểm tra nhỏ có phân tầng, không phải lấy mẫu đại diện để ước lượng độ chính xác toàn corpus. Không suy ra mọi công thức/OCR còn lại đều đúng. Việc duyệt VLM đã chặn nhiều mô tả yếu, nhưng không làm sạch hết text, công thức hoặc logo chưa duyệt. Dữ liệu mặc định vẫn có rủi ro nhiễu; đợt train đầu nên dùng 1 epoch và so kết quả trước/sau trước khi mở rộng.

## Lịch sử và chính sách chấp nhận

- 68,412 vùng / 27 học phần / 13.314 trang; 1,684 sự kiện duyệt.
- 1,667 VLM có quyết định hiện hành, khớp đầy đủ identity; 855 chấp nhận, 812 loại bỏ, không có stale.
- Chỉ thị chủ dữ liệu: các kết quả chưa từng kiểm tra mặc định đạt. Export gắn `owner_default_pass`, `human_verified=false`; không tạo sự kiện giả vào SQLite.
- Trước khử trùng: 53,700 ứng viên train = 845 VLM chấp nhận thuộc train + 52,855 vùng mặc định có nội dung thuộc train.
- Giữ ngoài train 129 vùng development, 262 vùng holdout; 13,510 vùng train rỗng; 811 quyết định reject thuộc train. Một reject và 10 approve còn lại nằm trong split bảo vệ, không xuất train.
- Snapshot SQLite nằm trong `snapshots/`; máy nguồn và lịch sử duyệt không bị sửa. `selection.jsonl` giữ nguồn đầy đủ tại máy; ZIP chỉ chứa text và metadata rút gọn, không chứa PDF/ảnh hay SQLite.

## Bộ dữ liệu cuối

**37,133 mẫu / 27 học phần / 10,787,454 ký tự**. Số mẫu là số vùng text, không phải số trang, không tuyên bố bao phủ toàn bộ tri thức của PDF.

Phân loại sau lọc: `{"kept_review_approve": 839, "exact_duplicate": 16428, "kept_owner_default_pass": 36294, "protected_exact_text": 75, "audit_quarantine": 30, "protected_same_page_image": 8, "protected_near_duplicate": 26}`.

Đã kiểm SHA-256 **66,101 đối tượng ảnh nguồn khác nhau** của các mẫu được giữ. Dedup ưu tiên văn bản có quyết định duyệt; khử trùng văn bản NFC, giữ nguyên chữ hoa/thường và khoảng trắng bên trong để bảo toàn ý nghĩa code/công thức. Loại trùng với split bảo vệ bằng text chính xác, render trang giống hệt và kiểm gần trùng pHash <=4 + Jaccard trigram >=0,85 (ít nhất 20 từ). Đây không phải kiểm trùng ngữ nghĩa toàn diện; không dùng bộ split trang cũ để tuyên bố có đánh giá tổng quát hóa độc lập.

Train là causal next-token loss trên text và EOS, không phải ảnh hoặc dữ liệu hỏi–đáp sinh thêm. Metadata có ID học phần/vùng, trang, hash nguồn, acceptance và review ID để truy nguyên. Email được che theo quy tắc exporter cũ; không tuyên bố đã phát hiện mọi thông tin cá nhân.

## Chi tiết mẫu

| Mẫu | Học phần / trang | Kết luận | Xử lý / chứng cứ |
|---|---|---|---|
| S01 | IT4593 / 6 | minor | retain: Nhãn input/transmitter/channel/receiver và các phổ khớp ảnh; câu mô tả biến đổi Fourier đơn giản hóa cách biểu diễn miền tần số. |
| S02 | IT3190 / 87 | pass | retain: Ba bước làm sạch, tích hợp, chuyển đổi và các số khớp ảnh vùng; đây là mô tả vùng, không phải toàn bộ slide. |
| S03 | IT4931 / 205 | pass | retain: N=3, B lỗi, replica chuyển E và trả B khi phục hồi đều có trong slide. |
| S04 | IT4788 / 342 | pass | retain: Scaffold widget và khung hiển thị khớp nội dung slide; không coi là transcript đầy đủ đoạn code. |
| S05 | IT4868 / 237 | pass | retain: Trục unit price/items sold và xu thế tăng rồi giảm đều hiện trong scatter plot. |
| S06 | IT3190 / 182 | pass | retain: Đã xem crop riêng: đúng danh sách thư mục; crop không bao gồm biểu đồ SVM ở phần khác của slide. |
| S07 | IT3011 / 237 | minor | retain: Dãy preorder khớp nguồn; native text mất khoảng trắng và dính footer. Giữ với ghi nhận lỗi định dạng. |
| S08 | IT4025 / 171 | fail | exclude: Lỗi font tiếng Việt và chuỗi hex/mảnh bảng không tái hiện được phép biến đổi affine ngược trong slide. |
| S09 | IT4868 / 166 | minor | retain: Nội dung Ward/centroid và ưu nhược điểm khớp nguồn; có dính từ/ký hiệu p2 do chuẩn hóa text. |
| S10 | IT4788 / 602 | pass | retain: Mục lục đủ sáu mục, không thấy sai nội dung. |
| S11 | IT4931 / 311 | pass | retain: Đầu vào và đầu ra MapReduce theo nhân viên khớp slide; vùng text không tuyên bố tái hiện bảng hình. |
| S12 | IT4653 / 73 | nonacademic | exclude: Trang chỉ có logo và kỷ niệm 25 năm; OCR tạo mảnh rời, không có nội dung học phần để CPT. |
| S13 | IT3100 / 735 | pass | retain: Bốn mục nội dung OOP khớp slide. |
| S14 | IT4653 / 147 | fail | exclude: Crop cho thấy delta có chỉ số l/l+1 và trọng số có chỉ số; OCR làm mất các chỉ số, đổi ý nghĩa công thức backprop. |
| S15 | IT4785 / 422 | minor | retain: Sáu loại input control và vai trò khớp nguồn; có số trang 8 chen vào dòng cuối. |
| S16 | IT3070 / 56 | pass | retain: Crop chỉ chứa phần đầu slide về an toàn: câu dữ liệu/chương trình phải được bảo vệ đúng vùng nguồn. |
| S17 | IT4025 / 696 | fail | exclude: Ảnh ghi y^2=x^3-3x+3 trên R; output thêm +tan và dấu gạch chéo, làm sai phương trình. |
| S18 | IT4785 / 39 | pass | retain: Bốn hàng Marshmallow/Nougat/Oreo/Pie và version/ngày/API đều khớp bảng. |
| S19 | IT3070 / 290 | fail | exclude: Crop ghi R1 & R2 }; output mất dấu & và chèn R, mất toán tử của biểu thức. |
| S20 | IT3323 / 275 | fail | exclude: Crop ghi E.place=id.place và E.code=""; output tách sai id.place và biến chuỗi rỗng thành số mũ u. |
| S21 | IT3170 / 1049 | reject_supported | keep_rejected: Mô tả gọi DFS là duyệt sâu rộng và nói các nút từ 1 đến 10; thiếu chính xác với cây DFS và num/low trong ảnh. |
| S22 | IT3080 / 600 | reject_supported | keep_rejected: Mô tả chỉ đoán từ rời, không mô tả sơ đồ trao đổi thông điệp D/E/F. |
| S23 | IT4593 / 82 | reject_supported | keep_rejected: Mô tả gọi cực đại là -V và bỏ qua hai tín hiệu đối pha của 2-PSK. |
| S24 | IT4593 / 492 | reject_preserved | keep_rejected: Mô tả nêu đúng tên eye diagram nhưng giải thích mơ hồ; giữ quyết định loại của chủ dữ liệu, không tự đảo quyết định. |

Ảnh đối chiếu: `audit/contact_01.png` đến `audit/contact_06.png`; danh sách khóa trước khi đọc: `audit/sample.json`; kết luận có hash ảnh: `audit/findings.json`.

## Training

Dùng cấu hình Qwen3 1.7B đã có của dự án, revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`; không đổi sang bản Base. QLoRA NF4 r=8, sequence 1024, batch 1, accumulation 8, LR 2e-5, cosine/warmup 3%, 1 epoch. Checkpoint 25 bước, giữ 2 bản; smoke 2 bước nằm riêng.

Đã kiểm CPU việc xuất dữ liệu, hash, cú pháp notebook, Unicode, token packing và checkpoint selection. Chưa chạy backward/GPU Colab hoặc đo cải thiện model trong lượt đóng gói này. Loss chẩn đoán của notebook đo cùng tối đa 64 sequence train trước/sau, không phải validation loss. Quiz probe tùy chọn giữ riêng và không vào train.

Nguồn kỹ thuật: [model Qwen](https://huggingface.co/Qwen/Qwen3-1.7B), [Trainer 4.57](https://huggingface.co/docs/transformers/v4.57.1/en/main_classes/trainer), [PEFT quantization](https://huggingface.co/docs/peft/developer_guides/quantization).


## Kiểm thử token thực tế trên CPU

Đã chạy đúng Transformers 4.57.6 và tokenizer Qwen3 tại revision khóa trên toàn bộ 37,133 mẫu: **3,235,037 token gồm EOS / 3,160 sequence**. Với batch 1, accumulation 8, 1 epoch: **395 optimizer steps**. Hash toàn luồng token trước/sau packing giống nhau; mọi source span, labels và attention mask đều được kiểm tra. 25 kiểm thử kỹ thuật đạt; 27 file records và 1.684 sự kiện duyệt nguồn giữ nguyên. Chưa thực thi GPU/Colab trong lượt đóng gói này.
