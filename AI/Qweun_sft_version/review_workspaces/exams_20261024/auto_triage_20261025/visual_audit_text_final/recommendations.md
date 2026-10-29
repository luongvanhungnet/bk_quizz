# Kiểm tra toàn bộ ứng viên TXT tại checkpoint

Checkpoint gồm 3.909 probe OCR v3 hợp lệ; hash và phiên bản classifier được giữ trong `checkpoint.json` và `classifier_snapshot.py`. Tại thời điểm đó có **13 native_text + 11 ocr_text**, toàn bộ 24 trang đã được render trực tiếp từ PDF ở cạnh dài 2.400 px và kiểm tra hình, TXT, parser. `sample.json` giữ từng ID, provenance, OCR gốc, TXT và câu hỏi parser. Sáu contact sheet giúp đối chiếu nhanh. Kết quả không bao gồm các probe xuất hiện sau checkpoint.

Không tạo phê duyệt, sửa review hoặc sửa dữ liệu nguồn.

## 11 ứng viên OCR đều là trắc nghiệm radio

Toàn bộ 11 OCR TXT là ảnh Microsoft Forms của `Công nghệ phần mềm - ôn tập cuối kì 20252.pdf`, có radio tròn không nhãn A/B/C/D và `(1 Point)`. OCR biến các radio thành `©`, `@`, `O`, `Ọ` hoặc bỏ chúng; parser nhận `options: []` nên phép kiểm tra “không có options tức là tự luận” không đúng. Một số trang còn chứa phương án câu trước ở đầu hoặc stem câu sau ở cuối.

Các ID phải chuyển `auto_vlm` trong checkpoint này:

- `rp_151d85e5db1140a125dc289e` — trang 7.
- `rp_021383264408303e728877af` — trang 14.
- `rp_4782d8068f03c3c8fcd99ada` — trang 18.
- `rp_65162643e29e459c20bd36c8` — trang 45.
- `rp_1905202b3384f3997e3a6557` — trang 46.
- `rp_1e15d6c7bfc106640a7c37c3` — trang 49.
- `rp_d06f5f55140ff24507e938e4` — trang 55.
- `rp_417402461d6868d5b08ba426` — trang 56.
- `rp_e7e47d9d8e31d20284b02b1b` — trang 68.
- `rp_6acb2606a10040564932e947` — trang 69.
- `rp_933f168f942df3d9aa62dd14` — trang 77.

Khuyến nghị thêm `\bPoints?\b`/`(1 Point)` vào phát hiện giao diện quiz, và phát hiện nhiều dòng bắt đầu bằng glyph radio OCR như `©/@/O/Ọ`. Cần bằng chứng dương tính về dạng tự luận, không suy ra chỉ từ việc parser không nhận được nhãn lựa chọn. Confidence/ink coverage cao không xác nhận cấu trúc lựa chọn còn nguyên.

Các ảnh này đều đọc rõ; không cần giữ duyệt ảnh thủ công.

## Các ứng viên native

- **Mục lục thành bảy câu giả:** `rp_c423fd2beea739fcaff9ac2a`, Lập trình mạng trang 1. Parser nhầm các dòng `1. Nội dung 1...`, `2. Nội dung 2...` làm câu. Điều kiện loại `unsegmented_page_text` chưa chặn được mục lục này. Cần chặn cấu trúc mục lục hoặc chuyển VLM.
- **Phương án câu trước bị nhân vào prompt:** `rp_8ae070579652c0acf8d5f48e` (trang 12) mở đầu `D. Đặt timeout...`; `rp_ba9c43cfc981d49efa27fb46` (65) mở đầu `C. LIST / D. GET`. Các dòng đó bị chép vào mọi prompt của câu mới. Phải đánh dấu preamble là phương án rời/chuyển VLM, không coi ngữ cảnh chung.
- **Câu cuối thiếu phương án do vắt trang:** `rp_d6403910844cf72e928aa327` (trang 13) kết thúc ở stem câu 10; trang 14 chứa A–D. `rp_fec85741b57c22f5e64a28b3` (OS trang 56) kết thúc ở stem “Số hiệu cluster bắt đầu là”; trang 57 chứa A–D/ANSWER. Không tự tạo phương án. Cần ghép nguồn kế tiếp hoặc VLM gắn cờ partial.
- **Một phần phương án nằm ở trang kế:** `rp_3aae2d499790d6b13b84b1da` (OS trang 32) có câu cuối chỉ A/B/C; trang 33 bắt đầu D)4 và ANSWER:A. `rp_ba9c43cfc981d49efa27fb46` (Lập trình mạng trang 65) có A/B của câu 10, trang 66 chứa C/D. So với stem-only, thiếu một phần lựa chọn khó phát hiện hơn; không coi số options hiện có là đầy đủ.
- **Đáp án nằm ở trang sau:** `rp_e0744b33f7bd93aea2b2a9aa` (OS trang 52) giữ được stem và A–E, nhưng ANSWER:C nằm ở đầu trang 53. Missing answer trong kết quả là trung thực theo phạm vi trang; muốn khôi phục đầy đủ phải ghép trang, không giải bài thay nguồn.
- **Footer số trang vào nội dung lựa chọn:** `rp_8ae070579652c0acf8d5f48e`, `rp_44834148ff6ecc84ca53ccc9`, `rp_2cbbf7383cac3c6a2978b02b`, `rp_a04ccb98fc27155fe3dc7c09`, `rp_22d5a1b5128edcdc2d51d3f7`, `rp_0276b6578760f7fd8e7bc12d`, `rp_ba9c43cfc981d49efa27fb46`. Parser nối footer 12/49/50/56/57/58/65 vào phương án cuối. Các trang 49, 50, 56, 57, 58 nhìn chung có đầy đủ câu/option; có thể giữ native TXT sau khi bỏ footer bằng vị trí hình học đã xác minh. Không xóa mọi số ở cuối trang theo regex chung vì có thể là dữ kiện/đáp án thật.
- **OS trang cuối `rp_0e3d5231a6c31322f847cc71`:** đầu trang là phương án/ANSWER của câu trước và parser bỏ phần đó. Ba câu mới còn lại được tách đúng theo hình. Đánh dấu orphan context để không báo đã khôi phục toàn bộ câu nguồn; ba câu mới có thể giữ TXT ở trạng thái chờ duyệt đợt 2.

Không thấy dữ kiện hình ảnh bị mất trong 13 native candidates; vấn đề chủ yếu ở cấu trúc và ranh giới trang. Việc chuyển auto VLM không tự sửa câu nhiều trang: prompt VLM phải giữ cờ thiếu dữ kiện, và bước nhập/duyệt phải không phát minh phần vắng mặt.

## Khuyến nghị áp dụng

Chặn OCR quiz `(Point)` và dấu radio trước. Chặn mục lục, preamble dạng lựa chọn, stem-only giữa các câu trắc nghiệm; giữ rõ các fragment ở mép trang. Bỏ footer bằng metadata hình học hoặc chuyển các trang đó sang VLM. Những ảnh đều rõ nên các điều chỉnh này không tăng hàng đợi duyệt ảnh thủ công. Kết quả chỉ là kiểm tra kỹ thuật của máy; tất cả câu nhập vào vẫn phải chờ người dùng duyệt đợt 2.

## Đối chiếu sau khi bổ sung guard

`guard_recheck.json` đối chiếu lại đúng 24 ứng viên bằng classifier SHA `1ef0a10bb235ca1562ddfbea393a4c38a8d9f16ae08a6459791fe53a49cbb854`: 11 OCR đã chuyển auto VLM; 9 native còn lại. Guard mục lục chưa chặn trang không có chữ “Mục lục”, chính là `rp_c423fd2beea739fcaff9ac2a`; cần nhận dạng các dòng `1. Nội dung 1...`, `2. Nội dung 2...` và chỉ mục con kèm số trang.

Năm native Lập trình mạng trang 49/50/56/57/58 chỉ còn vấn đề footer. Ba native OS còn lại là trang 32 (thiếu phương án ở trang sau), 52 (đáp án câu cuối ở trang sau), 63 (ba câu mới đầy đủ; phần câu trước ở đầu bị parser bỏ). Không có ứng viên OCR nào trong checkpoint này còn được nhận TXT sau guard mới. Dữ liệu OCR đến sau checkpoint phải kiểm tra riêng.
