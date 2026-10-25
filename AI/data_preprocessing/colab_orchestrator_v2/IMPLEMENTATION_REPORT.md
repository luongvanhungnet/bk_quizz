# Báo cáo cân bằng 14 input và chuyển sang xử lý tuần tự

Ngày: **21/10/2026**. Core: v5.0.0, giữ nguyên release/prompt/kiểm duyệt. Lớp điều phối: **v5-orchestrator-2-sequential**.

## Kết quả đo trên file thật

Đơn vị MB ở bảng là 1.000.000 byte. Phương sai dùng phương sai tổng thể của 14 dung lượng file, không dùng sai số ước lượng hay confidence của model.

| Chỉ số | Trước | Sau |
|---|---:|---:|
| Số input | 14 | 14 |
| Nhỏ nhất | 2,26 MB | 58,48 MB |
| Lớn nhất | 401,19 MB | 104,18 MB |
| Trung bình | 63,99 MB | 64,02 MB |
| Độ lệch chuẩn | 98,29 MB | 11,21 MB |
| Phương sai | 9.661,12 MB² | 125,68 MB² |
| Hệ số biến thiên | 153,60% | 17,51% |
| Tổng dung lượng | 895,90 MB | 896,24 MB |

**Phương sai giảm 98,70%.** 13 input nằm trong khoảng **58,48–63,40 MB**. Input 02 lớn hơn vì giữ nguyên PDF nguồn lớn của IT4653; không cắt PDF hoặc thay ảnh để ép dung lượng bằng nhau. Tổng dung lượng tăng khoảng 0,34 MB do metadata/phân mảnh; mục tiêu là cân bằng việc upload, không giảm chất lượng để giảm tổng byte.

## Cách phân bổ

`build_balanced.py` dùng Longest Processing Time theo byte nén: đưa đơn vị dữ liệu lớn vào bin nhẹ nhất. Đơn vị của tài liệu mới là toàn bộ học phần và PDF tương ứng, để làm đủ layout rồi mới định tuyến inference theo toàn học phần. IT3170 đã có layout/cache nên chia thành các nhóm trang gốc; mỗi nhóm giữ nguyên record và ảnh cần thiết.

PDF IT3170 dùng chung được đặt trong input 01; cache của từng nhóm trang đến cùng hoặc trước input xử lý nhóm đó. Tài nguyên có đường dẫn dùng chung chỉ được vận chuyển một lần ở input đến trước. Thứ tự 01–14 được ràng buộc, không yêu cầu input chưa upload trong tương lai.

## Luồng notebook mới

Cell kết nối Drive và cell input được tách riêng. Cell input chỉ nhận một file. Cài môi trường nằm ngoài vòng lặp xử lý.

Trong vòng lặp: xử lý file → xuất ZIP → yêu cầu trình duyệt tải → chờ người dùng nhập **DA_TAI** → ghi xác nhận gắn với hash ZIP → mới mở upload file kế. Gõ DUNG giữ ở kết quả hiện tại; tiếp tục sau reset sẽ trả lại ZIP đã xuất thay vì sinh lại inference. Notebook không tự khẳng định đã kiểm tra thư mục Downloads.

Controller và worker VLM sống qua các lượt upload. Qwen tạm chuyển sang RAM CPU giữa các input để dành GPU cho Paddle, rồi chuyển lại GPU khi cần, giữ dtype/NF4. Có chế độ giải phóng model mỗi input nếu máy không đủ RAM hoặc không hỗ trợ di chuyển; không tự đổi chế độ âm thầm. API di chuyển được đối chiếu với mã nguồn [bitsandbytes 0.48.1](https://github.com/bitsandbytes-foundation/bitsandbytes/blob/0.48.1/bitsandbytes/nn/modules.py) và [Transformers 4.57.6](https://github.com/huggingface/transformers/blob/v4.57.6/src/transformers/modeling_utils.py); chưa kiểm chứng toàn bộ vòng di chuyển trên GPU thật.

## Kiểm tra bảo toàn và phụ thuộc trên 14 ZIP

Đã đọc và xác minh hash của mọi payload trong 14 archive:

- Đủ **148 job / 27 PDF / 13.314 trang**, không lặp hoặc mất job.
- **4.490 ảnh cache giữ nguyên byte/hash** so với bản trước.
- **2.245 record cache giữ nguyên nội dung**; đủ 1.060 trang IT3170.
- Giữ **7 VLM cache thành công** và receipt shard IT3170 trang 1–100 đã hoàn thành.
- Không có SQLite kiểm duyệt trong input; không tạo human approval.
- Runtime giống nhau giữa các file và khớp pin trong notebook.
- Mọi ảnh/PDF mà input hiện tại cần đều đã đến trong input hiện tại hoặc trước đó.
- Mỗi học phần mới có toàn bộ job của nó trong cùng input, giữ điều kiện layout/routing theo học phần.

Biên bản: [INPUT_VALIDATION_20261021.json](INPUT_VALIDATION_20261021.json). Script audit: [evidence/audit_inputs.py](evidence/audit_inputs.py). Dung lượng/hash từng input: [UPLOAD_INDEX.json](../uploads_14_sequential_20261021/UPLOAD_INDEX.json).

## Kiểm thử và giới hạn

**9/9 test đạt**, lượt cuối **13,063 giây**: chặn sai thứ tự/chưa xác nhận tải, cân bằng bin, giữ worker/model qua hai lượt, di chuyển thiết bị không khởi tạo lại, ghép cache không ghi đè candidate đã xử lý, tiếp tục sau mất runtime, xuất/nhập hai lượt và chọn snapshot tăng dần của cùng học phần dù thứ tự file nhập đảo ngược.

Các test inference dùng mô phỏng; mapping/schema/checkpoint/export/import sử dụng core v5 thật. Chưa chạy benchmark GPU Colab; chưa có số liệu tăng tốc hoặc độ chính xác dữ liệu mới. Những ảnh/cache giữ nguyên không có nghĩa các dự đoán đã được người kiểm duyệt. Bộ điều phối không xuất CPT và không bỏ qua audit dedup/split toàn corpus.

Các input, notebook và báo cáo v1 vẫn được giữ nguyên để truy vết. Hướng dẫn hiện hành: [README.md](README.md).
