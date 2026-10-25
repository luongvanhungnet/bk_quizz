# Báo cáo điều phối v3 cho preprocessing v5

Bản cấu hình hiện hành là **L4/High-RAM/Python 3**, xem `L4_SETUP.md`, `RESULT_REVIEW_20261021.md` và `test_evidence_l4_20261021.json`. Các số đo kiểm thử/ZIP ở phần triển khai ban đầu bên dưới là của bản trước L4; runtime hiện tại có release/hash mới. Bản trước được giữ trong `releases/drive_v3_before_l4_20261021`.

Thực hiện ngày 21/10/2026 trong `D:\BKQuiz\AI\data_preprocessing\colab_orchestrator_v3`. Core v5.0.0 đóng băng, 14 ZIP v2 và quyết định kiểm duyệt được giữ.

| Yêu cầu | Triển khai |
|---|---|
| Tách tải kết quả khỏi tính toán | Notebook không gọi upload/download widget, không chờ DA_TAI; chỉ commit sau khi Drive có ZIP đúng hash |
| Đọc input từ Drive | `drive_inputs.py` kiểm kê `MyDrive/BKQuiz_cpt_data`, phát hiện thiếu/trùng chỉ số và trộn plan |
| Xử lý/đóng ZIP trên /content | Native, packet con, raw outputs, IPC, log, VLM prediction cache, archive được xử lý trên WORK cục bộ; chỉ chuyển bản checkpoint/ZIP hoàn chỉnh lên Drive |
| Bảo toàn khi truyền | `copy_verified`: copy theo khối 4 MiB, ghi `.partial`, kiểm SHA-256 đích rồi đổi tên; thất bại không công bố file cuối |
| Giảm dữ liệu lặp | Kho SHA-256 trong return, packet dạng file thành phần, importer khôi phục đường dẫn; giữ raw audit, snapshot, receipt và PDF nguồn |
| Chia nhóm và giải phóng | Native/parser/specialist tối đa 20 trang mặc định, gc giữa nhóm; checkpoint theo nhóm; dọn local sau durable commit |
| Không mất ngữ cảnh hoặc sai trang | Crop/context v5 giữ nguyên; page_map của PDF con được đưa về job cha, lưu cả manifest/raw con; không tính toàn job đã có layout khi chỉ một nhóm Docling thành công |
| Đo hiệu năng | JSONL stage spans, RAM VM/RSS PID, VRAM/GPU PID, ổ trống, số byte và tiến độ; bộ tổng hợp không cộng chồng span |
| Không in lặp log | Client dùng một cursor xuyên session, đọc tối đa 64 KiB mỗi lượt, drain khi có response |
| Không lãng phí kết quả cũ | Migration v2 tùy chọn, chỉ đọc dữ liệu cũ; dùng lại kết quả hoàn thành, stage chưa merge, source/cache/checkpoint |

## Tính đúng và kiểm thử

`test_drive_queue.py` kiểm tra hash/tamper, compact roundtrip, input order, copy thất bại, native/symbol/asset parity với core cũ, checkpoint native, mất runtime giữa model batch, mất runtime sau stage trước merge, mất runtime sau export trước commit, seed tăng dần không ghi đè candidate, migration v2 không sửa nguồn, page mapping Docling, envelope VLM, telemetry, cursor log, notebook và export/import hai input liên tiếp.

Mapping, render, normalization, cross-validation, layout materialization, packaging, merge, checkpoint và importer chạy với core v5 thật. OCR/Docling/VLM được thay bằng worker giả trong kiểm thử CPU. Không dùng kết quả này làm chứng cứ chất lượng suy luận hoặc tốc độ GPU.

Kiểm tra đủ **14/14 ZIP input**, tổng **896.239.610 byte**, SHA-256 khớp index cũ; **48/48 file core v5** còn nguyên. **17/17 test v3 đạt** (52,344 giây gồm discovery), gồm regression coverage Docling từng nhóm; **9/9 test hồi quy v2 đạt** (11,512 giây). Kết quả được ghi ở `test_evidence_20261021.json`. Không đóng lại input hoặc sửa SQLite thật của người dùng. Runtime ZIP phát hành có 15 file Python, 40.238 byte, đã kiểm tra hash đối chiếu notebook.

Số test, thời gian và hash kiểm tra thực tế ghi trong `test_evidence_20261021.json`, `tests_20261021.txt`, `INPUT_VALIDATION_20261021.json`. `RUNTIME_RELEASE.json` ghi hash runtime; notebook được phát hành cùng ZIP bootstrap có hash được khóa trong cell xác minh.

## Khác biệt có chủ đích

- Mỗi job gốc vẫn tối đa 100 trang; 20 là đơn vị thực thi nội bộ, không thay plan, source pages hay budget VLM toàn tài liệu.
- Với tài liệu chưa có native cache, adapter stream tạo record theo quy tắc v5 và cùng validator. Các seed đã có không render lại. Mẫu test so sánh được text, ký hiệu, ID, group/split và hash ảnh; chưa phải chứng minh mọi PDF đều giống tuyệt đối.
- Hash file được thực hiện theo khối thay vì `read_bytes()` trong adapter runtime; file source của release không đổi.
- Metadata liên kết child → parent không phải semantic verification; không tự chấp nhận mô tả VLM.
- Công việc merge/routing và một số snapshot vẫn cần metadata toàn tài liệu. Cache trọng số HF/Paddle còn ở Drive. Giữ model trong CPU còn cần RAM; telemetry giúp quyết định dùng `KEEP_MODEL_RESIDENT=False`.

## Kết luận kiểm chứng

Các thay đổi vận hành có thể kiểm tra tại máy; chưa đo phần trăm tăng tốc/giảm RAM hoặc tỷ lệ hết lỗi connecting trên Colab. Cần chạy input thử với `MAX_INPUTS=1`, kiểm tra telemetry và quality flags trước khi chạy toàn hàng đợi. Lỗi cache Docling/OCR/Table từ log cũ không bị che hoặc tự chuyển thành thành công.
