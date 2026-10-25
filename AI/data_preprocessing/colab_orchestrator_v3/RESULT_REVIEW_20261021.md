# Kiểm tra kết quả v3 và cấu hình L4 High-RAM

Nguồn kiểm tra: `D:\BKQuiz\AI\data_preprocessing\colab_orchestrator_v3\colab_orchestrator_v3_result`.

## Kết luận

Hai ZIP tải từ Google Drive chứa **kết quả input 01 và 02**, không phải hai mảnh cần nối byte. Cả hai đã hoàn tất thực thi các job và xuất file. Tuy nhiên `all_stages_successful=false`, `quality_certified=false`: dữ liệu chưa được chứng nhận sạch và chưa xuất CPT. Kết quả của IT4272 ở ảnh chụp lần trước không nằm trong hai return này, nên chưa thể kết luận nguyên nhân lần mất kết nối đó.

Đã đọc và kiểm tra SHA-256 của **5.720 object**, kiểm tra liên kết nguồn/ảnh của **3.406 record**. `latest_index.json` khớp hash và số byte của input 02. Các file tải xuống gốc không được chỉnh sửa; dữ liệu kiểm tra nằm trong `colab_orchestrator_v3_result/inspection`.

## Số liệu thực thi

| Chỉ số | Input 01 | Input 02 |
|---|---:|---:|
| Phạm vi | IT3170 trang 101–200 và IT3180 208 trang | IT4653 645 trang |
| Job hoàn tất | 4/4 | 7/7 |
| Stage có lỗi trong chính input | 7 | 22 |
| OCR: yêu cầu thành công / tổng | 430/444 | 3.746/4.060 |
| Structure: record thành công / tổng | 208/208 | 1.276/1.276 |
| Formula: yêu cầu thành công / tổng | Không chạy mới; dùng seed khi có | 248/248 |
| Table: yêu cầu thành công / tổng | 6/7 | 11/17 |
| VLM: quan sát trả về thành công / tổng | 14/14 | 68/68 |
| VLM cache hit | 4 | 42 |
| Trang có VLM, tính theo cặp tài liệu–trang | 13/308 = 4,22% | 33/645 = 5,12% |
| Dung lượng ZIP cuối | 365.615.385 byte | 1.900.806.479 byte |

Các tỷ lệ trên đo **thành công thực thi**, không đo độ chính xác nội dung. 68 quan sát VLM của IT4653 nằm trên 33 slide, không phải 68 slide. Số record Structure có thể vượt số trang vì nhiều yêu cầu ảnh có cùng phạm vi full-page; chưa thay đổi routing này trong bản cấu hình L4.

`summary.json` input 02 ghi 29 stage lỗi vì mã cũ đếm cả 7 lỗi của input 01. Kiểm tra theo job của input 02 cho thấy **22 lỗi hiện tại + 7 lỗi lịch sử**. Bản cập nhật tách `stages_with_errors` của input hiện tại, `historical_stages_with_errors` của các job trước và `cumulative_stages_with_errors` tổng cộng; không sửa ngược các file kết quả cũ.

## Nguyên nhân lỗi tìm thấy

**Docling:** cả 3 stage của IT3180 và 7 stage của IT4653 lỗi khi nạp layout model từ cache:

```text
models--docling-project--docling-layout-heron/snapshots/8f39ad3c0b4c58e9c2d2c84a38465abf757272d8
Error while deserializing header: header too large
```

Đây là lỗi đọc trọng số/cache, không phải bằng chứng thiếu VRAM. Chưa có file trọng số gốc trong các return để phân biệt file hỏng, sai định dạng hay header vượt giới hạn. Notebook L4 dùng cache Docling riêng và kiểm tra chuyển đổi một PDF một trang trước khi chạy hàng đợi. Cache cũ được giữ nguyên; không tuyên bố đã sửa được trọng số trước khi probe thực tế thành công.

**OCR:** input 01 có 14 và input 02 có 314 yêu cầu báo `Paddle produced no spatial candidates`. Cần phân biệt vùng không có chữ với chữ bị bỏ sót; không tự chuyển các record này thành thành công. Số lỗi là số yêu cầu vùng ảnh qua các phase, không phải số trang sai. OCR smoke test trong notebook mới giúp phát hiện sớm lỗi môi trường trên ảnh chữ biết trước; không thay thế kiểm tra dữ liệu thật.

**Table:** 1 và 6 crop báo `PP-StructureV3 found no nonempty table in the classified table crop`. Có thể liên quan vùng được gán table nhưng không có bảng nhận dạng được, crop hoặc nhận dạng cấu trúc; chưa đủ chứng cứ quy về GPU. Không thấy `KeyError: doc_preprocessor_res` trong các lỗi record được kiểm tra của hai return này.

**Formula:** 248 yêu cầu mới của IT4653 trả về `ok`, nhưng **35 record có cờ LaTeX mất cân bằng ngoặc**. IT3170 còn 6 record seed có lỗi cấu trúc công thức cũ. Vì vậy 248/248 không phải Formula Exact Match 100%.

**VLM:** 82 quan sát trả về thành công, không có record được đánh dấu human/semantic verified. Chưa có ground truth để chấm nhãn node/cạnh, CER/WER, Formula Exact Match, groundedness hay điểm tổng hợp Q.

## Trạng thái chất lượng của snapshot

| Tài liệu | Record trong return | trusted | uncertain | critical |
|---|---:|---:|---:|---:|
| IT3170, phần 100 trang đã nhận | 259 | 0 | 253 | 6 |
| IT3180 | 299 | 0 | 290 | 9 |
| IT4653 | 2.848 | 0 | 2.606 | 242 |

`uncertain` không có nghĩa toàn bộ nội dung sai. Các quy tắc ghi nhận thiếu xác nhận transcript độc lập, khác biệt số/ký hiệu giữa extractor và nội dung rủi ro cần duyệt. 242 critical của IT4653 gồm 207 record `no_usable_extraction` và 35 record lỗi cấu trúc công thức. Docling chưa hoạt động làm mất một nguồn đối chiếu; chưa thể quy mọi disagreement thành lỗi OCR hay lỗi native.

Tất cả 3.406 record kiểm tra được đều nối tới hash ảnh crop/context/render có trong return, nhưng traceability đúng không chứng minh nội dung dự đoán đúng. Human review VLM và các gate xuất CPT vẫn được giữ.

## Thời gian và bộ nhớ

Thời gian worker của input 01 khoảng **12 phút 22 giây**; VLM chiếm 7 phút 38 giây, gồm khởi tạo/nạp model và cache. Input 02 có khoảng **27 phút 09 giây** worker: OCR 9 phút 19 giây, Structure 7 phút 15 giây, VLM 7 phút 13 giây, các nhánh khác khoảng 3 phút 22 giây.

Telemetry input 02 là tích lũy cả phiên. Lấy chênh lệch với snapshot input 01 cho thấy native prepare của input 02 khoảng **10 phút 04 giây**, packaging khoảng **6 phút 47 giây**, merge khoảng **6 phút 43 giây**. Không cộng mọi span vì nhiều span lồng nhau. Snapshot nằm trong ZIP chốt trước khi đóng/truyền chính ZIP đó; chưa có đầy đủ thời gian xuất cuối input 02.

RAM vật lý ghi nhận **13.605.830.656 byte ≈12,67 GiB**, GPU tổng 15.360 MiB. Tính đến snapshot input 02:

- Tổng RSS cây tiến trình cao nhất khoảng **9,88 GiB**; tổng RSS có thể đếm lặp bộ nhớ dùng chung.
- RAM khả dụng thấp nhất khoảng **2,60 GiB**.
- VRAM được lấy mẫu cao nhất **8.449 MiB ≈8,25 GiB**.

Chưa thấy chứng cứ OOM trong những file này; lấy mẫu khoảng 15 giây có thể bỏ lỡ đỉnh ngắn. High-RAM giúp tăng khoảng trống bộ nhớ, nhưng không chứng minh sẽ hết `Connecting`. L4 không tự sửa cache Docling, công thức sai cấu trúc hoặc crop không phải bảng. Native, packaging và merge còn dùng CPU/I/O nên không thể suy ra toàn pipeline tăng tốc theo tỷ lệ tốc độ GPU.

## Bản notebook đã chuẩn bị

`Colab_V5_L4_HighRAM.ipynb` và `colab_orchestrator_v3_l4_runtime.zip` dùng cùng core v5.0.0, Qwen2.5-VL-7B NF4, prompt và budget 512/512. Không tăng batch size âm thầm: giữ 20 trang để tương thích checkpoint hiện có.

Notebook yêu cầu chọn Python 3/L4 và kiểm tra GPU thực tế, RAM ≥40 GiB, dung lượng bộ nhớ còn trống; chạy CUDA Paddle/OCR/layout, Torch/NF4 và Docling một trang trước hàng đợi. Đây là ngưỡng vận hành do dự án đặt ra, không phải lời hứa Colab sẽ cấp tài nguyên. Theo [mã CLI chính thức của Colab](https://github.com/googlecolab/google-colab-cli/blob/main/src/colab_cli/commands/session.py), L4 có một machine shape; tùy chọn High-RAM riêng có thể không xuất hiện/không áp dụng, nên cần kiểm tra RAM thực tế.

Phiên bản L4 đã được kiểm tra logic trên máy hiện tại, chưa chạy probe hoặc benchmark trên L4 thật. Khi người dùng chạy, probe thành công/thất bại và traceback được lưu trong `BASE/preflight_runs`. Đổi GPU không tự chạy lại những lỗi đã cache ở input 01/02; giữ dữ liệu và audit cũ để mở đợt sửa riêng.
