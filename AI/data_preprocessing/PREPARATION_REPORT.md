# Báo cáo chốt v5 và chuẩn bị corpus — 21/10/2026

**v5.0.0 đã là phiên bản mặc định chính thức.** `CURRENT.json` trỏ tới snapshot `region_preprocessing_v5_official`; launcher kiểm checksum 48 file trước khi chạy. Mã VLM, prompt, model revision và cấu hình suy luận khớp lượt pilot v5 đã đo. Các bộ v1–v4, run/cached result v5 và lịch sử duyệt IT3170 được giữ.

## Đã hoàn thành

| Hạng mục | Kết quả |
|---|---|
| Đặc tả chính thức | `SPEC_V5_OFFICIAL.md` |
| Hướng dẫn thực thi | `RUNBOOK_CORPUS.md` |
| Kiểm kê | **27 PDF / 13.314 trang / 621.755.869 byte** |
| Kiểm tra nguồn | **27/27 SHA khớp upstream**, đọc được, không cần password |
| Kế hoạch | **148 shard**, tối đa 100 trang/shard |
| Tái sử dụng | IT3170, 1.060 trang, giữ run và cache |
| Học phần mới | 26 môn / 12.254 trang, cần native/render/discovery |
| Hai pha cloud | 137 shard discovery mới + 148 shard inference khi đạt gate |
| Notebook corpus | Tự nhận discovery/inference; chọn packet theo hash, không dùng nhầm ZIP Drive cũ |
| Routing | Giữ 56/1.060 trang VLM cho IT3170; với tài liệu mới nhắm 5%, chặn vượt quota cấu hình, giữ deferred |
| Human Review | Chỉ VLM thành công; ←/→ chuyển, ↑ chấp nhận, ↓ loại, nút Sửa |
| Kiểm thử | **167 test engine/batch + 4 test registry/config đạt** |
| Preflight | Đạt source/page coverage/disk; `preparation_ready=true` |

Phần điều phối corpus bổ sung việc materialize vùng từ Docling/PP-Structure, source-page mapping khi chia packet, ID riêng cho ảnh dùng chung nhiều vị trí và chặn nguồn/config đổi âm thầm. Không đổi nhiệm vụ VLM thành JSON hoặc nhiều bước. Lỗi specialist cũ với crop không đổi được giữ deferred để tránh chạy lại mù quáng.

## Gói khởi đầu có thể chạy ngay

Đã đóng gói **IT3170 trang 1–100** từ cache: **154 request**, gồm 95 text, 5 code, 38 formula, 4 table, 12 vùng hình; chỉ **1 request VLM** theo routing. ZIP khoảng **41,10 MiB**, CRC và mọi input/runtime hash đạt. Đây là một shard, không phải toàn bộ 56 trang VLM của học phần.

Xem [START_HERE.md](START_HERE.md) để mở packet/notebook và dùng đúng lệnh nhập kết quả. Bằng chứng máy ở `PREPARATION_REPORT.json`, checksum release ở `CURRENT.json`, preflight ở `plans/corpus_20261021/preflight.json`.

## Chưa thực thi và các gate còn lại

Chưa render mới 12.254 trang của 26 môn khác, chưa chạy Colab toàn corpus, chưa xác minh toàn bộ nội dung và chưa tạo combined CPT train-ready. Mỗi môn mới phải xong discovery/layout trước inference; sau đó người thật duyệt VLM. Trước huấn luyện kết hợp cần audit near-duplicate/split giữa các học phần. Chưa có human gold để báo CER/WER/Q toàn corpus.

Đây là trạng thái **đã chốt phiên bản và chuẩn bị thực thi**, không phải tuyên bố toàn bộ 13.314 trang đã được làm sạch.
