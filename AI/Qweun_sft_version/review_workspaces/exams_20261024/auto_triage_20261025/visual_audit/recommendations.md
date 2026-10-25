# Kiểm tra hình ảnh cho phân luồng tự động

Kiểm tra bằng hình ảnh 20 trang/tile, chọn có chủ đích theo lớp dữ liệu thay vì lấy mẫu ngẫu nhiên. Đây là kiểm tra kỹ thuật của máy, không phải sự phê duyệt của người dùng, không tạo `review_events`. Ảnh render trực tiếp từ PDF và thông tin nguồn nằm trong `sample.json`; năm contact sheet và 20 ảnh riêng được giữ lại để kiểm tra.

## Phát hiện có ảnh hưởng trực tiếp đến phân luồng

- `rp_8374eff207977acc6f1ac3fb`, AI 20171 trang 2: bảng dữ liệu A/B/C/Y là ảnh raster, chỉ chiếm **7,65%** trang. TXT có 475 ký tự nhưng thiếu toàn bộ hàng dữ liệu. Vì vậy ngưỡng `image_coverage < 0.15` không an toàn để xuất TXT.
- `rp_555292c4e9b5a556bb4550c2`, quiz An ninh mạng trang 33: câu SQL nằm trong ảnh chỉ chiếm **1,75%** diện tích; TXT thiếu truy vấn và trạng thái checkbox. Không thể coi ảnh nhỏ là trang trí khi chưa xác minh riêng.
- `rp_089039436b43b8edea853f47`, quiz thực hành trang 5: 862 ký tự native, không có raster, nhưng đáp án nằm ở các checkbox/tick và điểm số. TXT thuần không đủ khôi phục đáp án.
- `rp_59896927379c3b4eec791b2b`, AI 20241 trang 1: công thức logic với chỉ số dưới, dấu phủ định/hệ quả và đáp án tô đỏ. Phông toán + màu là lý do dùng VLM, không phải lý do bắt người dùng duyệt ảnh.
- `rp_6b615b250cb3d00a712017bb`, Công nghệ phần mềm 20191 trang 5: hai cột, lưới tô đáp án, 562 vector drawing và 80 glyph không hỗ trợ. Hình vẫn đọc rõ; chuyển VLM thay vì lấy native TXT hoặc coi là ảnh hỏng.
- `rp_2c53b1e7a73f54d297180b7c`, AI 20211 trang 12: OCR có 182 từ, confidence 95,77 và bao phủ 98,98% mực, nhưng là ảnh giao diện checkbox. Confidence/ink coverage cao không chứng minh OCR đã giữ được trạng thái lựa chọn.
- `rp_673da911ffda4a607f86cb3c`, AI 20221 trang 7: đồ thị, nút radio tô màu và nhiều screenshot ghép. 195 từ OCR không giữ hết quan hệ cạnh và dấu chọn. Hình rõ, phù hợp auto VLM.

## Khuyến nghị cho native TXT

Dùng điều kiện bảo thủ: nguồn đã trích thành công, ít nhất 300 ký tự/30 từ, không có glyph lỗi, `image_count == 0`, `drawing_count == 0`, không có phông toán, không có chữ màu hoặc dấu đáp án thị giác; không có dấu hiệu bảng/biểu đồ/công thức phụ thuộc bố cục. Kiểm tra thêm kết quả `extract_questions(text)`: `requires_vlm` phải false và câu hỏi không rỗng. Giữ ngữ cảnh, ký hiệu và thiếu đáp án như trong nguồn; không tự giải hoặc tự gán đáp án.

Các trang `rp_39515d58941b03291fa8e16c`, `rp_9977ae975f09a4ee02a96196`, `rp_25185cf3a39c0e46cda7d3c4` và `rp_8a9d15d2aa64cbf7a5741e16` cho thấy văn bản native rõ, code và đoạn văn giữ được bằng TXT. Trang cuối là phụ lục C/C++, nên việc có chữ tốt không đồng nghĩa có câu hỏi mới: parser phải nhận ra hoặc chuyển tiếp, không bịa câu hỏi.

`rp_6567b2508dff1e719e889eb4` có các phương án không gắn nhãn và câu trước vắt sang đầu trang; TXT đọc tốt nhưng cấu trúc câu/đáp án có thể mơ hồ. Parser phải giữ ngữ cảnh hoặc báo chuyển VLM.

Các trang có ít vector, như `rp_9e6dd42b95aebb2ed403bc0b` và `rp_aab7c6ef95e1a10901d519ff`, có thể chỉ có khung viền/footer. Quy tắc `drawing_count == 0` sẽ gửi thêm một số trang rõ sang VLM; điều này chấp nhận được cho mục tiêu giảm duyệt ảnh mà không làm mất dữ kiện. Chỉ nới sau khi nhận dạng được drawing trang trí bằng hình học, không nới theo số lượng đơn thuần.

Các trang chỉ tô màu tiêu đề `rp_f767000eece3b2f9439cc300`, `rp_f25bd345ca7e77831a926700` minh họa màu không luôn là đáp án. Chuyển VLM là lựa chọn bảo thủ; không cần đưa vào hàng đợi thủ công chỉ vì có màu.

## Khuyến nghị cho OCR TXT và hàng đợi thủ công

Không dùng confidence OCR như xác suất VLM thất bại. Không tự chuyển screenshot biểu mẫu/quiz, radio/checkbox, ảnh có đánh dấu, bảng hoặc hình học thành OCR TXT chỉ vì confidence và độ phủ mực cao. Ưu tiên auto VLM cho ảnh rõ thuộc các lớp đó.

Chỉ giữ thủ công khi có bằng chứng suy giảm thực sự: render không thành công sau retry; ảnh chụp màn hình có chữ rất nhỏ, nghiêng/che khuất hoặc mất nét; vùng đề bị cắt, hoặc tương phản/kích thước nguồn khiến dữ kiện không khôi phục được. Kết hợp đặc trưng, kiểm tra hình và retry OCR; số từ OCR thấp một mình không đủ.

- `rp_361502848f538439a76fbf2d`, AI 20231 trang 40: ảnh chụp màn hình monitor kèm trần nhà/bàn phím/ngón tay, câu hỏi chỉ chiếm vùng nhỏ. Phù hợp giữ thủ công vì rủi ro mất dữ kiện cao; không khẳng định VLM chắc chắn thất bại.
- `rp_ea47b2bba1c16ca5aea7a261`, AI 20181 trang 5: trang trắng thực sự trong render, native 0, độ lệch xám 0, ink 0. Có thể đánh dấu `blank` riêng, không tạo quyết định từ chối của người dùng.

Các bản OCR `sft-ocr-probe-v2` ban đầu có cấu hình TSV lỗi, nên số từ 0 của bản này **không hợp lệ làm bằng chứng phân luồng**. Agent OCR đã sửa ở `sft-ocr-probe-v3`; chỉ dùng v3 có header TSV hợp lệ. Một ví dụ v2 sai là trang rất rõ `rp_aab7c6ef95e1a10901d519ff`. Hình kiểm tra vẫn hợp lệ vì render từ PDF độc lập với OCR.

20 trang này là mẫu chủ đích để phát hiện lỗi quy tắc, không đủ đo precision, recall hoặc tỷ lệ thất bại VLM. Mục tiêu dưới 500 ảnh thủ công không phải ngưỡng sắp hạng để ép số lượng.
