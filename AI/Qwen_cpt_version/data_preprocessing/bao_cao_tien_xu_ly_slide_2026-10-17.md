# Báo cáo tiền xử lý slide SoICT - HUST

Ngày xử lý: 17/10/2026 (Asia/Bangkok).

## Kết quả và phạm vi

- Nguồn: `D:\bk_quizz_data\slide` gồm 37 file gốc: 24 ZIP và 13 PDF rời. Giải nén thành 285 PDF, 16,446 trang PDF.
- Kết quả: **32 PDF slide/bộ môn**, 15,070 trang; **23 PDF đã gán mã**, **9 bộ chưa xác minh mã**. Hai bộ Thuật toán ứng dụng được gộp chung một PDF.
- Chỉ ghi báo cáo Markdown này trong BKQuiz; các dữ liệu, công cụ xử lý và kết quả nằm ngoài BKQuiz. Không sửa mã nguồn hoặc tài liệu sẵn có của BKQuiz.
- Không trích xuất nội dung PDF thành text, không OCR, không sinh bộ dữ liệu văn bản. Chỉ giải nén ZIP, xem trang dưới dạng ảnh để nhận diện, đối chiếu danh mục học phần, so sánh ảnh render và sao chép/gộp các trang PDF.
- Giữ nguyên hình, công thức, chữ và bố cục của từng trang; không chuyển slide thành ảnh trong PDF đầu ra, không đổi cỡ trang, không tách bố cục nhiều slide/trang. Không sửa nội dung học thuật.
- Một PDF cho mỗi học phần đã nhận diện. Đây là tài liệu có trong nguồn, không phải cam kết đủ toàn bộ đề cương hoặc đủ mọi chương. Các mã suy luận và trường hợp có nguy cơ khác mã theo khóa được ghi riêng bên dưới.
- Ở thư mục cần xác minh, tiền tố `CHUA_XAC_MINH` chỉ là nhãn tạm, **không phải mã học phần**. Không tự bịa mã để đủ quy tắc đặt tên.

## Đường dẫn bàn giao

- Slide có mã: [pdf/](<D:/bk_quizz_data/slide_processed/pdf>)
- Slide chưa rõ mã: [can_xac_minh/](<D:/bk_quizz_data/slide_processed/can_xac_minh>)
- Sách, tài liệu ôn tập hoặc tài liệu khác trường: [khong_phai_slide/](<D:/bk_quizz_data/slide_processed/khong_phai_slide>)
- Danh mục CSV: [manifest.csv](<D:/bk_quizz_data/slide_processed/_audit/manifest.csv>)
- Trạng thái từng PDF đầu vào: [file_status.csv](<D:/bk_quizz_data/slide_processed/_audit/file_status.csv>)
- Truy vết nguồn/chương, số trang và SHA-256: [manifest.json](<D:/bk_quizz_data/slide_processed/_audit/manifest.json>)
- Ánh xạ từng trang đầu ra về trang gốc: [page_map.json](<D:/bk_quizz_data/slide_processed/_audit/page_map.json>)
- Kết quả kiểm tra: [validation.json](<D:/bk_quizz_data/slide_processed/_audit/validation.json>); [summary.json](<D:/bk_quizz_data/slide_processed/_audit/summary.json>)
- `_work/` là vùng trung gian và công cụ tái hiện, không phải bộ slide để nạp vào pipeline.

## Các bộ slide chưa đủ căn cứ gán mã

Các bộ dưới đây đã được gộp/sắp xếp trong phạm vi có thể xác định, nhưng được để riêng để tránh gán nhầm nhãn học phần.

| Nguồn | Tên nhận diện | Trang | Điểm cần xác minh |
|---|---|---:|---|
| `drive-download-20261015T165615Z-1-001.zip` | [Linux và hệ điều hành cho hệ nhúng](<D:/bk_quizz_data/slide_processed/can_xac_minh/CHUA_XAC_MINH-Linux và hệ điều hành cho hệ nhúng.pdf>) | 361 | Có RTOS, Embedded Linux, boot, kernel, backup, log, bảo mật, Shell; chưa đủ căn cứ chọn IT4946 hay học phần hệ điều hành nhúng khác. |
| `drive-download-20261015T170540Z-1-001.zip` | [Một số vấn đề chọn lọc trong toán cho kỹ sư](<D:/bk_quizz_data/slide_processed/can_xac_minh/CHUA_XAC_MINH-Một số vấn đề chọn lọc trong toán cho kỹ sư.pdf>) | 79 | Bìa Nguyễn Linh Giang; nội dung xác suất thống kê thuộc toán chuyên đề. Không đủ căn cứ gán MI2020 hoặc IT2022 chỉ dựa vào chủ đề. |
| `drive-download-20261015T170809Z-1-001.zip` | [Trí tuệ nhân tạo](<D:/bk_quizz_data/slide_processed/can_xac_minh/CHUA_XAC_MINH-Trí tuệ nhân tạo.pdf>) | 559 | Bìa Nguyễn Nhật Quang, năm 2009-2010; không thấy mã trên bìa. Cần phân biệt IT4040, các biến thể IT4042/IT4044, và IT3160 hiện nay. |
| `drive-download-20261015T171138Z-1-001.zip` | [Cơ sở lý thuyết thông tin](<D:/bk_quizz_data/slide_processed/can_xac_minh/CHUA_XAC_MINH-Cơ sở lý thuyết thông tin.pdf>) | 110 | Bìa Phạm Hải Đăng; chưa có căn cứ chọn giữa các mã lý thuyết thông tin IT4590Q, IT4592E, IT4594 hoặc mã cũ. |
| `drive-download-20261015T171718Z-1-001.zip` | [Nhập môn chương trình dịch](<D:/bk_quizz_data/slide_processed/can_xac_minh/CHUA_XAC_MINH-Nhập môn chương trình dịch.pdf>) | 394 | Bìa Hoàng Anh Việt; chưa xác nhận mã. Không tự đồng nhất với gói Xây dựng chương trình dịch IT3323; cần xác nhận liệu là cùng học phần hay học phần khác. |
| `full cac slide tren.pdf` | [Quản trị dự án công nghệ thông tin](<D:/bk_quizz_data/slide_processed/can_xac_minh/CHUA_XAC_MINH-Quản trị dự án công nghệ thông tin.pdf>) | 363 | Tên ngoài full cac slide tren.pdf; tài liệu trộn đề cương, lập kế hoạch và quản trị dự án. Chưa có bìa xác định mã IT4240/IT4244 hoặc học phần khác; giữ nguyên thứ tự nguồn. |
| `Lap_trinh_he_nhung_1_6.pdf` | [Lập trình hệ nhúng](<D:/bk_quizz_data/slide_processed/can_xac_minh/CHUA_XAC_MINH-Lập trình hệ nhúng.pdf>) | 113 | Bìa Phạm Văn Thuận, lập trình I/O, driver, Qt trên Linux. Không tự gán IT4210 Hệ nhúng; có thể liên quan học phần Lập trình hệ thống cũ, cần xác nhận. |
| `Mật mã ứng dụng.zip` | [Mật mã ứng dụng](<D:/bk_quizz_data/slide_processed/can_xac_minh/CHUA_XAC_MINH-Mật mã ứng dụng.pdf>) | 834 | Tên gói và bìa rõ tên môn; chưa xác nhận mã bản tiếng Việt. CTĐT Cyber Security có IT4025E nhưng không đủ căn cứ tự bỏ hậu tố E hoặc gán mã đó cho bộ này. |
| `SecureProgramming.pdf` | [Lập trình an toàn](<D:/bk_quizz_data/slide_processed/can_xac_minh/CHUA_XAC_MINH-Lập trình an toàn.pdf>) | 131 | Bìa Lương Ánh Hoàng; không có mã ở phần giới thiệu. Không tự gán IT3045 vì khác bối cảnh giảng viên/mô tả, cần xác nhận mã chính xác. |

Đặc biệt: hai bộ Chương trình dịch đang được giữ tách theo tên gốc vì chưa có căn cứ xác nhận chúng là cùng một học phần. Nếu xác nhận cùng mã, cần gộp lại thành một PDF cho mã đó.

## Mã đã đặt nhưng còn cần đối chiếu phiên bản/chương trình

15 bộ sau được gán theo tên và nội dung khớp danh mục chính thức; đây là **suy luận chuẩn hóa**, không phải mã đã đọc trực tiếp trên slide. Cần đối chiếu nếu mục tiêu là giữ đúng mã của từng khóa, hệ đào tạo hoặc bản slide cũ.

| Mã đã đặt | Môn | Ghi chú |
|---|---|---|
| IT3011 | Cấu trúc dữ liệu và thuật toán | Chuẩn hóa theo CTĐT KHMT; slide 2013-2014 không ghi mã tại trang bìa, cần đối chiếu mã cũ IT3010 với IT3011. |
| IT3323 | Xây dựng chương trình dịch | Bìa có tên môn; đối chiếu danh mục thư viện và lịch thi HEDSPI. Chưa xác nhận biến thể cũ IT3322 trên chính slide. |
| IT3100 | Lập trình hướng đối tượng | Đối chiếu tên và nội dung Java/OOP với CTĐT KHMT; slide không ghi mã ở bìa đã xem. Có biến thể IT3103 theo chương trình. |
| IT4788 | Phát triển ứng dụng đa nền tảng | Nội dung Dart, Flutter, React Native; khớp mô tả IT4788 trong CTĐT KHMT. Danh mục thư viện còn dùng tên cũ Công cụ lập trình tiên tiến. |
| IT2000 | Nhập môn Công nghệ thông tin và Truyền thông | Bìa và tên môn khớp IT2000 trong CTĐT; không thấy mã ở bìa. Gói nguồn không có Bài 3. |
| IT4868 | Khai phá Web | Tên và nội dung khai phá Web khớp lịch thi chính thức IT4868; danh mục thư viện còn liệt kê IT4435. Cần xác nhận phiên bản gốc nếu yêu cầu mã theo khóa. |
| IT3170 | Thuật toán ứng dụng | Đối chiếu CTĐT KHMT. Gộp hai bộ bài giảng cùng tên: Phạm Quang Dũng và bộ PDF tên ngoài ghi Bùi Quốc Trung; cần xác nhận tác giả bộ thứ hai. |
| IT3080 | Mạng máy tính | Tên môn khớp CTĐT KHMT; nhiều bìa ghi HEDSPI/Ngô Hồng Sơn, cần đối chiếu mã IT3080 với IT3084 nếu giữ mã riêng của chương trình. Nguồn không có Chương 9. |
| IT3180 | Nhập môn Công nghệ phần mềm | Bìa tên môn khớp CTĐT KHMT; cần đối chiếu nếu tài liệu thuộc học phần cũ IT4080. |
| IT4906 | Tính toán tiến hóa | Bìa Evolutionary Computing, Huỳnh Thị Thanh Bình; tên và nội dung khớp CTĐT KHMT. Chưa có mã in ở bìa. |
| IT4441 | Giao diện và trải nghiệm người dùng | Tên gói và nội dung UI/UX khớp CTĐT và lịch thi IT4441; bản thân trang giới thiệu đã xem không ghi mã. |
| IT3070 | Nguyên lý hệ điều hành | Bìa Đỗ Quốc Huy, Nguyên lý các hệ điều hành; đối chiếu CTĐT KHMT. Cần đối chiếu IT3074 nếu thuộc chương trình riêng. |
| IT4593 | Nhập môn kỹ thuật truyền thông | Bìa Tạ Hải Tùng và tên môn khớp mã IT4593 trong lịch thi chính thức; chưa thấy mã trên bìa. |
| IT4060 | Lập trình mạng | Bìa Lương Ánh Hoàng; đối chiếu tên với danh mục thư viện. Chưa xác nhận biến thể IT4060/IT4062 theo chương trình. |
| IT4263 | An ninh mạng | Bộ 12 bài khớp cấu trúc trên trang chính thức IT4263 của Bùi Trọng Tùng (mạng, hạ tầng, dịch vụ, DoS, Web, giao thức mật mã, phòng chống tấn công). Cần đối chiếu phiên bản vì IT4260 cũng dùng chung một số bài. |

## Mã có căn cứ trực tiếp trên tài liệu

| Mã | Môn | Căn cứ |
|---|---|---|
| IT4272 | Hệ thống máy tính | Trang 5 có đường dẫn bài giảng IT4272; bìa Nguyễn Kim Khánh, CS-HEDSPI2019. |
| IT4611 | Các hệ thống phân tán và ứng dụng | Chân trang chương 1 ghi IT4611. |
| IT3120 | Phân tích và thiết kế hệ thống | Tên và mã IT3120 in trên bìa các bài. |
| IT4410 | Nhập môn tương tác người máy | Bìa SV-TTNM_00.pdf ghi IT4410. Giữ mã này, không đổi sang IT4441. |
| IT3190 | Nhập môn Học máy và khai phá dữ liệu | Trang 2 L0-intro.pdf ghi IT3190. |
| IT4653 | Học sâu và ứng dụng | Trang 2 bài 1 ghi IT4653. |
| IT4931 | Lưu trữ và xử lý dữ liệu lớn | Trang 3 chương 1 có bảng tên học phần và mã IT4931. |
| IT4785 | Phát triển ứng dụng cho thiết bị di động | Bìa ConstraintLayout và ConstraintLayout-Lab ghi IT4785. Tên thư mục ghi Nguyễn Hồng Quang nhưng trang giới thiệu ghi Hoàng Văn Hiệp; cần xác nhận tác giả. |

## Làm sạch trùng lặp và thứ tự

- Không có cặp PDF đầu vào nào trùng toàn bộ byte SHA-256.
- **Dữ liệu lớn:** bỏ bản `Big Data final.pdf` 514 trang khỏi phép gộp vì trùng đúng chuỗi 14 file chương theo thứ tự. Đã so sánh ảnh render của **toàn bộ 514 cặp trang ở chiều rộng 1024 px, không có sai khác**. Dùng 14 chương gốc, kết quả 514 trang.
- **Cơ sở lý thuyết thông tin:** dùng CH1 → CH5, tổng 110 trang. Không đưa thêm `Tài liệu thầy Phạm Hải Đăng (1).pdf` (110 trang, bản gộp lại) và `(2).pdf` (28 trang, bố cục 4 slide/trang). Bản gộp 110 trang đã đối chiếu từng trang với 5 chương: sai số màu tuyệt đối trung bình 0,208/255, lớn nhất 1,881/255; đã xem các cặp sai số lớn, nội dung tương ứng. Đây là đối chiếu hình ảnh, không phải so sánh byte; các bản thay thế vẫn còn nguyên trong nguồn và bản giải nén.
- **Mạng máy tính:** dùng bản `Chuong 7-0 - Tang ung dung.pdf` làm phần chính, nối các trang khác biệt của `Chuong 7 - Tang ung dung.pdf` thành phần bổ sung. Bỏ 16 trang trùng ảnh đã xác nhận ở 1024 px: 3, 4, 8, 9, 12, 13, 16–23, 25, 26 (số trang trong file cũ). Kết quả môn: 774 trang.
- **Nhập môn kỹ thuật truyền thông:** dùng `Bài 6 new.pdf` làm phần chính, giữ phần khác biệt của `Bài 6.pdf`. Bỏ 15 trang trùng ảnh đã xác nhận ở 1024 px: 5, 8, 11, 12, 13, 15, 25–29, 31, 35, 37, 38. Có 6 ứng viên trùng ở 256 px nhưng khác ở 1024 px nên vẫn giữ. Kết quả môn: 555 trang.
- Các trang bổ sung được giữ theo thứ tự tương đối của file gốc. Không loại trang chỉ vì nội dung gần giống, không xóa các bước xuất hiện dần của hiệu ứng trình chiếu hoặc các trang bìa lặp giữa chương.
- Sắp xếp theo số chương/bài, bao gồm phần thập phân và phần bổ sung; sửa thứ tự boot/kernel của bộ Linux theo tên file; đặt phần cơ bản trước phần Deque/RMQ/Tarjan; đặt Layout trước ConstraintLayout và bài lab; đặt Bài 9 trước Bài 9.2.
- Hai bộ Thuật toán ứng dụng được đặt trong cùng một PDF IT3170: bản tổng hợp tên ngoài Bùi Quốc Trung trước, rồi bộ chương của Phạm Quang Dũng. Giữ nội dung của cả hai vì là các cách giảng/phiên bản khác nhau.
- Bản tổng hợp quản trị dự án chưa có căn cứ xác định thứ tự chương; giữ nguyên thứ tự trang nguồn, không đoán để đảo trang.
- Không đổi những PDF 2/4 slide trên một trang thành từng slide riêng vì sẽ cần can thiệp bố cục và có thể cắt mất nội dung.

## Thiếu hụt, tên tác giả và các điểm chất lượng cần lưu ý

- IT2000: nguồn có Bài 1, 2, 4–14; **không có file Bài 3**.
- IT3080: nguồn có chương 1–8 và 10–13; **không có file Chương 9**. Các chương an toàn thông tin và multimedia có tên tác giả khác trong cùng gói; giữ theo cấu trúc gói, chưa chứng minh toàn bộ là cùng một phiên bản đề cương.
- IT3170: bộ Phạm Quang Dũng bắt đầu ở Chương 2, không có Chương 1 riêng trong gói đó. Bản tổng hợp khác vẫn được giữ. Tên ngoài ghi Bùi Quốc Trung chưa được coi là bằng chứng chắc chắn về tác giả bên trong.
- IT4785: thư mục ghi Nguyễn Hồng Quang nhưng trang giới thiệu ghi **Hoàng Văn Hiệp**. Các bìa ConstraintLayout có mã IT4785; không dùng tên thư mục để gán tác giả cho toàn bộ bộ slide. Các số chương không liên tục (ví dụ không có 5.1 và 6); chưa khẳng định đây là thiếu file hay cách đánh số của giảng viên.
- IT4931: tên file có các nhánh 3.1, 3.3, 4.1, 4.2, 4.3, 4.6; số trên bìa không luôn trùng số tên file. Không tự kết luận thiếu nội dung chỉ từ khoảng trống số.
- IT4410: có cả trang đơn lẫn handout nhiều slide/trang, một số nội dung giữa file có thể giao nhau; không tự xóa vì khác bố cục và chưa đủ căn cứ chứng minh trùng toàn bộ.
- Các PDF tên Full/full không bảo đảm đầy đủ đề cương. Việc kiểm tra render bảo đảm trang nhập được giữ nguyên hình thức, không xác nhận tính đúng/sai hoặc mức cập nhật của bài giảng.

## Tài liệu không đưa vào tập slide

| Nguồn | Trang | Lý do |
|---|---:|---|
| [123doc-cau-hoi-on-tap-mon-hoc-it4460-phan-tich-cac-yeu-cau-phan-mem-docx.pdf](<D:/bk_quizz_data/slide_processed/khong_phai_slide/123doc-cau-hoi-on-tap-mon-hoc-it4460-phan-tich-cac-yeu-cau-phan-mem-docx.pdf>) | 76 | Bộ câu hỏi ôn tập, không phải slide; mã IT4460 chỉ có trong tên file ngoài, chưa xác minh. |
| [bài giảng Kiến trúc máy tính - TS.Hoàng Xuân Dậu.pdf](<D:/bk_quizz_data/slide_processed/khong_phai_slide/bài giảng Kiến trúc máy tính - TS.Hoàng Xuân Dậu.pdf>) | 93 | Bìa ghi Học viện Công nghệ Bưu chính Viễn thông, tác giả Hoàng Xuân Dậu; là bài giảng dạng giáo trình, không phải slide HUST. |
| [Giáo trình cơ sở an toàn thông tin - thầy Nguyễn Khanh Văn.pdf](<D:/bk_quizz_data/slide_processed/khong_phai_slide/Giáo trình cơ sở an toàn thông tin - thầy Nguyễn Khanh Văn.pdf>) | 226 | Sách giáo trình Cơ sở An toàn Thông tin của Nguyễn Khanh Văn, không phải slide. |
| [Giáo trình toán rời rạc - Nguyễn Đức Nghĩa.pdf](<D:/bk_quizz_data/slide_processed/khong_phai_slide/Giáo trình toán rời rạc - Nguyễn Đức Nghĩa.pdf>) | 298 | Sách giáo trình Toán rời rạc, Nguyễn Đức Nghĩa - Nguyễn Tô Thành, không phải slide. |

Không xóa những tài liệu này. File gốc được giữ nguyên; một bản sao nằm trong `khong_phai_slide/` để tiện kiểm tra. Vì tập trả về là slide, chưa có PDF slide riêng cho Toán rời rạc, Cơ sở An toàn thông tin hoặc Phân tích yêu cầu phần mềm từ các sách/tài liệu ôn tập này.

## Danh mục PDF đầu ra

| Mã/nhãn | Môn | Trang PDF | Nguồn | File |
|---|---|---:|---|---|
| IT4272 | Hệ thống máy tính | 229 | G03 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT4272-Hệ thống máy tính.pdf>) |
| IT3011 | Cấu trúc dữ liệu và thuật toán | 478 | G04 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT3011-Cấu trúc dữ liệu và thuật toán.pdf>) |
| IT4611 | Các hệ thống phân tán và ứng dụng | 522 | G05 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT4611-Các hệ thống phân tán và ứng dụng.pdf>) |
| IT3323 | Xây dựng chương trình dịch | 346 | G06 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT3323-Xây dựng chương trình dịch.pdf>) |
| CHUA_XAC_MINH | Linux và hệ điều hành cho hệ nhúng | 361 | G07 | [Mở PDF](<D:/bk_quizz_data/slide_processed/can_xac_minh/CHUA_XAC_MINH-Linux và hệ điều hành cho hệ nhúng.pdf>) |
| IT3100 | Lập trình hướng đối tượng | 765 | G08 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT3100-Lập trình hướng đối tượng.pdf>) |
| IT4788 | Phát triển ứng dụng đa nền tảng | 653 | G09 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT4788-Phát triển ứng dụng đa nền tảng.pdf>) |
| CHUA_XAC_MINH | Một số vấn đề chọn lọc trong toán cho kỹ sư | 79 | G10 | [Mở PDF](<D:/bk_quizz_data/slide_processed/can_xac_minh/CHUA_XAC_MINH-Một số vấn đề chọn lọc trong toán cho kỹ sư.pdf>) |
| IT3120 | Phân tích và thiết kế hệ thống | 401 | G11 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT3120-Phân tích và thiết kế hệ thống.pdf>) |
| IT4410 | Nhập môn tương tác người máy | 459 | G12 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT4410-Nhập môn tương tác người máy.pdf>) |
| CHUA_XAC_MINH | Trí tuệ nhân tạo | 559 | G13 | [Mở PDF](<D:/bk_quizz_data/slide_processed/can_xac_minh/CHUA_XAC_MINH-Trí tuệ nhân tạo.pdf>) |
| IT2000 | Nhập môn Công nghệ thông tin và Truyền thông | 469 | G14 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT2000-Nhập môn Công nghệ thông tin và Truyền thông.pdf>) |
| IT3190 | Nhập môn Học máy và khai phá dữ liệu | 471 | G15 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT3190-Nhập môn Học máy và khai phá dữ liệu.pdf>) |
| IT4868 | Khai phá Web | 692 | G16 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT4868-Khai phá Web.pdf>) |
| CHUA_XAC_MINH | Cơ sở lý thuyết thông tin | 110 | G17 | [Mở PDF](<D:/bk_quizz_data/slide_processed/can_xac_minh/CHUA_XAC_MINH-Cơ sở lý thuyết thông tin.pdf>) |
| CHUA_XAC_MINH | Nhập môn chương trình dịch | 394 | G18 | [Mở PDF](<D:/bk_quizz_data/slide_processed/can_xac_minh/CHUA_XAC_MINH-Nhập môn chương trình dịch.pdf>) |
| IT3170 | Thuật toán ứng dụng | 1060 | G19, G36 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT3170-Thuật toán ứng dụng.pdf>) |
| IT3080 | Mạng máy tính | 774 | G20 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT3080-Mạng máy tính.pdf>) |
| IT4653 | Học sâu và ứng dụng | 645 | G21 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT4653-Học sâu và ứng dụng.pdf>) |
| CHUA_XAC_MINH | Quản trị dự án công nghệ thông tin | 363 | G22 | [Mở PDF](<D:/bk_quizz_data/slide_processed/can_xac_minh/CHUA_XAC_MINH-Quản trị dự án công nghệ thông tin.pdf>) |
| IT3180 | Nhập môn Công nghệ phần mềm | 208 | G23 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT3180-Nhập môn Công nghệ phần mềm.pdf>) |
| IT4906 | Tính toán tiến hóa | 244 | G24 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT4906-Tính toán tiến hóa.pdf>) |
| IT4441 | Giao diện và trải nghiệm người dùng | 569 | G25 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT4441-Giao diện và trải nghiệm người dùng.pdf>) |
| CHUA_XAC_MINH | Lập trình hệ nhúng | 113 | G28 | [Mở PDF](<D:/bk_quizz_data/slide_processed/can_xac_minh/CHUA_XAC_MINH-Lập trình hệ nhúng.pdf>) |
| IT4931 | Lưu trữ và xử lý dữ liệu lớn | 514 | G29 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT4931-Lưu trữ và xử lý dữ liệu lớn.pdf>) |
| CHUA_XAC_MINH | Mật mã ứng dụng | 834 | G30 | [Mở PDF](<D:/bk_quizz_data/slide_processed/can_xac_minh/CHUA_XAC_MINH-Mật mã ứng dụng.pdf>) |
| IT3070 | Nguyên lý hệ điều hành | 765 | G31 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT3070-Nguyên lý hệ điều hành.pdf>) |
| IT4593 | Nhập môn kỹ thuật truyền thông | 555 | G32 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT4593-Nhập môn kỹ thuật truyền thông.pdf>) |
| IT4785 | Phát triển ứng dụng cho thiết bị di động | 822 | G33 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT4785-Phát triển ứng dụng cho thiết bị di động.pdf>) |
| CHUA_XAC_MINH | Lập trình an toàn | 131 | G34 | [Mở PDF](<D:/bk_quizz_data/slide_processed/can_xac_minh/CHUA_XAC_MINH-Lập trình an toàn.pdf>) |
| IT4060 | Lập trình mạng | 165 | G35 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT4060-Lập trình mạng.pdf>) |
| IT4263 | An ninh mạng | 320 | G37 | [Mở PDF](<D:/bk_quizz_data/slide_processed/pdf/IT4263-An ninh mạng.pdf>) |

## Đối chiếu gói nguồn

| ID | File/gói gốc | PDF con | Trang trước xử lý |
|---|---|---:|---:|
| G01 | `123doc-cau-hoi-on-tap-mon-hoc-it4460-phan-tich-cac-yeu-cau-phan-mem-docx.pdf` | 1 | 76 |
| G02 | `bài giảng Kiến trúc máy tính - TS.Hoàng Xuân Dậu.pdf` | 1 | 93 |
| G03 | `CS-HEDSPI-2019.pdf` | 1 | 229 |
| G04 | `drive-download-20261015T165413Z-1-001.zip` | 6 | 478 |
| G05 | `drive-download-20261015T165430Z-1-001.zip` | 8 | 522 |
| G06 | `drive-download-20261015T165542Z-1-001.zip` | 13 | 346 |
| G07 | `drive-download-20261015T165615Z-1-001.zip` | 10 | 361 |
| G08 | `drive-download-20261015T165857Z-1-001.zip` | 12 | 765 |
| G09 | `drive-download-20261015T170316Z-1-001.zip` | 11 | 653 |
| G10 | `drive-download-20261015T170540Z-1-001.zip` | 2 | 79 |
| G11 | `drive-download-20261015T170630Z-1-001.zip` | 10 | 401 |
| G12 | `drive-download-20261015T170720Z-1-001.zip` | 7 | 459 |
| G13 | `drive-download-20261015T170809Z-1-001.zip` | 11 | 559 |
| G14 | `drive-download-20261015T170826Z-1-001.zip` | 13 | 469 |
| G15 | `drive-download-20261015T170914Z-1-001.zip` | 14 | 471 |
| G16 | `drive-download-20261015T170942Z-1-001.zip` | 14 | 692 |
| G17 | `drive-download-20261015T171138Z-1-001.zip` | 7 | 248 |
| G18 | `drive-download-20261015T171718Z-1-001.zip` | 7 | 394 |
| G19 | `drive-download-20261015T171736Z-1-001.zip` | 8 | 306 |
| G20 | `drive-download-20261015T171748Z-1-001.zip` | 18 | 790 |
| G21 | `drive-download-20261015T172002Z-1-001.zip` | 12 | 645 |
| G22 | `full cac slide tren.pdf` | 1 | 363 |
| G23 | `Full slide.pdf` | 1 | 208 |
| G24 | `full.pdf` | 1 | 244 |
| G25 | `giao diện và trải nghiệm người dùng.zip` | 11 | 569 |
| G26 | `Giáo trình cơ sở an toàn thông tin - thầy Nguyễn Khanh Văn.pdf` | 1 | 226 |
| G27 | `Giáo trình toán rời rạc - Nguyễn Đức Nghĩa.pdf` | 1 | 298 |
| G28 | `Lap_trinh_he_nhung_1_6.pdf` | 1 | 113 |
| G29 | `lưu trữ và xử lý dữ liệu lớn.zip` | 15 | 1028 |
| G30 | `Mật mã ứng dụng.zip` | 12 | 834 |
| G31 | `NGuyen li he dieu hanh full.pdf` | 1 | 765 |
| G32 | `nhap mon kỹ thuật truyền thông.zip` | 15 | 570 |
| G33 | `phat trien ung dung cho thiet bi di dong.zip` | 24 | 822 |
| G34 | `SecureProgramming.pdf` | 1 | 131 |
| G35 | `Slides.pdf` | 1 | 165 |
| G36 | `Thầy Bùi Quốc Trung - Thuật toán ứng dụng.pdf` | 1 | 754 |
| G37 | `Thầy Bùi Trọng Tùng-20261015T165529Z-1-001.zip` | 12 | 320 |

## Kiểm chứng bàn giao

- Mở lại và render **toàn bộ 15,070 trang đầu ra** ở chiều rộng 256 px; đối chiếu với đúng trang nguồn: **0 sai khác**.
- Đối chiếu thêm **834 cặp trang ở chiều rộng 1024 px**, gồm đầu/giữa/cuối từng phần nhập: **0 sai khác**.
- Trang PDF được nhập trực tiếp vào PDF mới hoặc sao chép nguyên file khi chỉ có một nguồn; hình ảnh preview chỉ phục vụ kiểm tra, không dùng làm nội dung PDF.
- Kiểm tra SHA-256 và số lượng của cả 37 file gốc trước/sau: **giữ nguyên**. Các ZIP gốc không bị ghi đè.
- Cân bằng số trang: **16.446 = 15.070 trang slide đầu ra + 693 trang sách/tài liệu loại khỏi tập slide + 652 trang bản tổng hợp trùng + 31 trang trùng giữa các phiên bản**.
- Mọi trang bị bỏ giữa các phiên bản có bản ghi nguồn/trang thay thế trong `_audit/duplicate_page_confirmation.json`. Không có nội dung nào bị xóa khỏi nguồn gốc.

## Nguồn chính thức dùng đối chiếu mã

Các nguồn sau chỉ dùng kiểm chứng tên/mã học phần, không tải thêm slide vào tập dữ liệu. Mã trên chính slide được ưu tiên hơn tên danh mục hiện tại.

- [CTĐT cử nhân Khoa học máy tính do SoICT công bố](https://soict.hust.edu.vn/wp-content/uploads/CTDT-CN.KHMT-K70-V2025.03.28.pdf): đối chiếu nhóm cơ sở, học máy, học sâu, UI/UX, đa nền tảng, mobile, dữ liệu lớn và tính toán tiến hóa. Tên file có K70/2025 nhưng phần bìa nội dung ghi chương trình 2017 kèm cập nhật; không coi tên file là bằng chứng về mã của các slide cũ.
- [Danh mục tài liệu theo học phần của Thư viện HUST](https://library.hust.edu.vn/vi/node/779): kiểm tra các biến thể mã; một số tên cũ/khác còn cùng tồn tại, nên chỉ dùng như nguồn hỗ trợ.
- [IT4263 - trang học phần chính thức của Bùi Trọng Tùng](https://users.soict.hust.edu.vn/tungbt/it4263/): đối chiếu bộ An ninh mạng; [IT4260](https://users.soict.hust.edu.vn/tungbt/it4260/) dùng để nhận biết phiên bản khác.
- [Lịch thi chính thức 2022.1, HUST](https://ctt.hust.edu.vn/Upload/Nguyen%20Quoc%20Dat/files/DTDH_Lichthi/2022-2023/LTCK-20221-AB-B-03022023.pdf): đối chiếu IT4868 - Khai phá Web.
- [Lịch thi chính thức 2025.1, HUST](https://ctt.hust.edu.vn/Upload/Nguy%E1%BB%85n%20Qu%E1%BB%91c%20%C4%90%E1%BA%A1t/files/DTDH_Lichthi/2025-2026/LTCK-ky%2020251-26122025.pdf): đối chiếu IT4593 - Nhập môn kỹ thuật truyền thông.
- [Lịch thi VN/ICT chính thức 2025.1](https://ctt.hust.edu.vn/Upload/Nguy%E1%BB%85n%20Qu%E1%BB%91c%20%C4%90%E1%BA%A1t/files/DTDH_Lichthi/2025-2026/LTCK-VN-ICT%20ky%2020251-24122025.pdf): đối chiếu IT3323 - Xây dựng chương trình dịch.
- [CTĐT An toàn Không gian số do SoICT công bố](https://soict.hust.edu.vn/wp-content/uploads/CNTT-Chu%CC%9Bo%CC%9Bng-tri%CC%80nh-da%CC%80o-ta%CC%A3o-An-toa%CC%80n-Kho%CC%82ng-gian-so%CC%82%CC%81-Cyber-Security_v30032025.pdf): chỉ xác nhận có mã IT4025E - Mật mã ứng dụng trong chương trình tiếng Anh; chưa gán mã này cho bộ slide tiếng Việt.
