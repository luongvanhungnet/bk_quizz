# Kiểm tra 25 ứng viên native_text

Chạy `classify(native, None, text)` của `auto_triage_policy.py` trên dữ liệu thật: 88 ứng viên, thuộc 10 môn và 11 nguồn. Chọn 25 trang theo môn/nguồn, khoảng cách trang trong cùng nguồn, mã chương trình, tiếng Việt và dạng câu hỏi. Đã xem đủ 25 render trong bảy contact sheet và so sánh kết quả parser lưu trong `sample.json`.

Đây là kiểm tra kỹ thuật có chủ đích, không phải phê duyệt của người dùng hoặc phép đo precision. Không tạo review event, không sửa nguồn và không sửa classifier.

## Điều kiện hình ảnh

Không thấy hình, bảng raster, checkbox hoặc dấu đáp án bằng màu bị bỏ sót trong 25 ứng viên. Kiểm tra thêm metadata toàn bộ 88 ứng viên: không có PDF annotation, widget hoặc span gắn cờ superscript. Những chặn `image_count == 0`, `drawing_count == 0`, màu/phông toán/glyph lỗi bằng 0 đang loại được các trường hợp mất dữ kiện thị giác đã thấy trong đợt trước.

Điểm còn yếu là cấu trúc câu hỏi sau khi tách TXT, chủ yếu do câu vắt trang và các định dạng chưa hỗ trợ. TXT vẫn giữ ký tự nguồn nhưng trường `prompt`, `options`, `answer` không đúng hoặc nhận một trang hướng dẫn làm câu hỏi.

## Các lớp cần chuyển VLM hoặc sửa parser trước khi nhận native_text

1. **Trọng số đáp án `[0]`/`[100]`.** 47/88 ứng viên thuộc ngân hàng Android. Ví dụ `rp_8b5ec7184688a1c05bf66c9d` (trang 11), `rp_1f28675ca97d3f6873ac3142` (57), `rp_e48f8984f2a5d254aa836bbd` (34), `rp_02576e57e4f531071fd542c1` (46). Parser tạo `options: []`, answer missing dù nguồn có trọng số rõ. Phần đáp án của câu từ trang trước còn được chép làm ngữ cảnh cho mọi câu mới. Khuyến nghị tạm chuyển VLM khi có dòng bắt đầu `[0]`/`[100]`; hoặc hỗ trợ đầy đủ định dạng, không chỉ nhận diện chuỗi.

2. **Đáp án `Sol:` và phương án không nhãn.** 15 ứng viên thuộc nguồn Khoa học dữ liệu. `rp_682bc765492c66779b6383d8` (trang 18) có `Sol: chọn a.ko` bị nối vào phương án B, còn đáp án câu trước `Sol: chọn A.có` xuất hiện trong prompt của tất cả câu mới. `rp_5c12a128786d9035cf42248d` (101), `rp_d678b6eb61af2933f40265c3` (59), `rp_4e137a455dc4baa9432092f7` (40) có phương án không nhãn hoặc lời giải câu trước bị trộn. Khuyến nghị tạm chuyển VLM khi gặp `^Sol:` hoặc dạng đáp án này chưa được parser hỗ trợ.

3. **Trang không có câu hỏi độc lập nhưng fallback vẫn tạo một câu.** `rp_9cabdc78659dd3e0e9a40da4` (dàn ý cấu trúc thi), `rp_6ed1c7232ad11fd977d95311` (ngữ cảnh payroll vắt trang), `rp_abc83506aa1cbe6ddb28d947` (đoạn mã tiếp nối), `rp_4d275a97a140a9ad1bad21e3` và `rp_d45d4c4a1fffe6a82572ad82` (hướng dẫn thi), `rp_8a9d15d2aa64cbf7a5741e16` (phụ lục C/C++), `rp_c423fd2beea739fcaff9ac2a` (mục lục). Tất cả có `unsegmented_page_text`. Có thể chuyển VLM để xác định nội dung/không có câu hỏi, hoặc giữ như ngữ cảnh tài liệu riêng; không coi fallback là bằng chứng đã tách được một câu hỏi.

4. **Đề lập trình dùng `Bài`, không dùng `Câu`.** `rp_bcfa6238f6b7793cb472d2f0` (trang 1), `rp_05dca03b7fdde254262ae99a` (5), `rp_26c79e0f4b3636304288cd19` (4) của Nhập môn lập trình. Nhiều bài và dữ liệu input/output bị gộp nguyên trang, có bài kéo sang trang kế. Cần parser hỗ trợ `Bài`/ngữ cảnh nhiều trang hoặc chuyển VLM.

5. **Preamble là phương án của câu trước.** `rp_ba9c43cfc981d49efa27fb46` (Lập trình mạng trang 65) bắt đầu bằng `C. LIST / D. GET`. Parser chép hai dòng này vào prompt của cả câu 7, 8, 9, 10. Nên chuyển VLM khi preamble trông như phương án/đáp án câu trước, thay vì nhân lên làm ngữ cảnh chung. Một số trang OS như `rp_3aae2d499790d6b13b84b1da` (32), `rp_0e3d5231a6c31322f847cc71` (63) có phần câu trước ở đầu bị bỏ khỏi kết quả; không gây gán nhầm cho câu mới nhưng không được gọi là đã khôi phục toàn trang.

6. **Câu cuối thiếu phương án do ngắt trang.** `rp_d6403910844cf72e928aa327` (Lập trình mạng trang 13) tách tốt câu 7–9, nhưng câu 10 chỉ có stem `Sau khi gọi select() thành công, các tập fd_set có:` và footer trang. Parser tạo freeform không phương án. Câu cuối trang `rp_ba9c43cfc981d49efa27fb46` cũng chỉ có A/B trong khi các câu lân cận có A–D. Cần cờ khả năng vắt trang và ghép nguồn kế tiếp, hoặc để VLM gắn cờ câu thiếu; không tự tạo các lựa chọn còn lại.

Các trường hợp trên phù hợp auto VLM vì hình đọc rõ; chúng không cần tăng hàng đợi duyệt ảnh thủ công.

## Trường hợp tốt trong mẫu

`rp_a90c57caa8e58bc503d523cb` (Lập trình mạng trang 42) có sáu câu và phương án A–D rõ, không có đáp án in trên trang; parser giữ missing đúng. `rp_e0744b33f7bd93aea2b2a9aa` (OS trang 52) tách được các câu/đáp án `ANSWER:`; câu cuối chưa có đáp án phải tiếp tục giữ missing. `rp_120acd9dfadd0efb640d5557` (Mạng máy tính trang 18) là một câu tự luận với lời đáp, TXT giữ được, nhưng do không có nhãn câu nên vẫn cần xử lý fallback cẩn thận.

Kết luận thực thi: thêm chặn cấu trúc có thể làm số native_text giảm mạnh, nhưng số ảnh thủ công không tăng vì chuyển sang auto VLM. Chất lượng khôi phục câu nhiều trang vẫn cần được giải quyết ở bước VLM/duyệt đợt 2; không nên suy ra native TXT đầy đủ đồng nghĩa các câu đã đầy đủ.
