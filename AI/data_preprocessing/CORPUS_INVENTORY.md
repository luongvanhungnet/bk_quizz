# Kiểm kê corpus v5 chính thức — 21/10/2026

- Phạm vi: **27 PDF, 13,314 trang** trong D:/bk_quizz_data/slide_processed/pdf.
- 27/27 nguồn đọc được và khớp SHA-256 upstream; source PDF không bị sửa.
- Kế hoạch: **148 shard**, tối đa 100 trang. IT3170 tái dùng run; 26 học phần khác cần native/render và discovery.
- Đây là kiểm kê/chuẩn bị, không phải nghiệm thu chất lượng nội dung.

| Học phần | Số trang | MiB nguồn | Trạng thái chuẩn bị |
|---|---:|---:|---|
| IT2000-Nhập môn Công nghệ thông tin và Truyền thông | 469 | 24.53 | Chờ native + discovery |
| IT3011-Cấu trúc dữ liệu và thuật toán | 478 | 4.23 | Chờ native + discovery |
| IT3070-Nguyên lý hệ điều hành | 765 | 29.17 | Chờ native + discovery |
| IT3080-Mạng máy tính | 774 | 11.81 | Chờ native + discovery |
| IT3100-Lập trình hướng đối tượng | 765 | 12.76 | Chờ native + discovery |
| IT3120-Phân tích và thiết kế hệ thống | 401 | 6.42 | Chờ native + discovery |
| IT3170-Thuật toán ứng dụng | 1060 | 27.11 | Dùng run v5/cache hiện có |
| IT3180-Nhập môn Công nghệ phần mềm | 208 | 2.27 | Chờ native + discovery |
| IT3190-Nhập môn Học máy và khai phá dữ liệu | 471 | 24.68 | Chờ native + discovery |
| IT3323-Xây dựng chương trình dịch | 346 | 5.34 | Chờ native + discovery |
| IT4025-Mật mã ứng dụng | 834 | 46.57 | Chờ native + discovery |
| IT4060-Lập trình mạng | 165 | 1.53 | Chờ native + discovery |
| IT4263-An ninh mạng | 320 | 15.10 | Chờ native + discovery |
| IT4272-Hệ thống máy tính | 229 | 8.14 | Chờ native + discovery |
| IT4410-Nhập môn tương tác người máy | 459 | 13.98 | Chờ native + discovery |
| IT4441-Giao diện và trải nghiệm người dùng | 569 | 54.90 | Chờ native + discovery |
| IT4590Q-Cơ sở lý thuyết thông tin | 110 | 5.44 | Chờ native + discovery |
| IT4593-Nhập môn kỹ thuật truyền thông | 555 | 12.77 | Chờ native + discovery |
| IT4611-Các hệ thống phân tán và ứng dụng | 522 | 28.21 | Chờ native + discovery |
| IT4653-Học sâu và ứng dụng | 645 | 127.46 | Chờ native + discovery |
| IT4785-Phát triển ứng dụng cho thiết bị di động | 822 | 21.09 | Chờ native + discovery |
| IT4788-Phát triển ứng dụng đa nền tảng | 653 | 18.48 | Chờ native + discovery |
| IT4812-Lập trình an toàn | 131 | 30.10 | Chờ native + discovery |
| IT4822-Lập trình hệ nhúng | 113 | 6.37 | Chờ native + discovery |
| IT4868-Khai phá Web | 692 | 21.28 | Chờ native + discovery |
| IT4906-Tính toán tiến hóa | 244 | 6.09 | Chờ native + discovery |
| IT4931-Lưu trữ và xử lý dữ liệu lớn | 514 | 27.12 | Chờ native + discovery |

## Phạm vi ngoài đợt này

Nguồn gốc PDF/ZIP trong slide giữ làm provenance; không nạp lại lần hai. Đề thi, thư mục không-phải-slide và _work không đưa vào corpus này. Các PDF mới thêm hoặc thay đổi phải có inventory/plan mới.

## Ngân sách VLM

Tỷ lệ tính theo trang của từng tài liệu, số crop tính riêng. Ước lượng quota chỉ phục vụ lập lịch; không phải kết quả detector hoặc bằng chứng đã hoàn tất coverage. Không ép đủ số trang nếu không có ứng viên.
Nếu đủ ứng viên, quota mục tiêu tham khảo khoảng **682 trang (5.12%)**. Tổng ngưỡng trên có làm tròn theo tài liệu là 1079 trang; đây không phải lệnh chạy VLM trên tất cả các trang đó.

## Gate trước train kết hợp

Cần hoàn tất discovery/inference, giữ deferred/lỗi, người thật duyệt VLM, rồi audit near-duplicate/split liên học phần. Chưa có combined CPT corpus được chứng nhận sạch hoặc human gold để báo Q.
