# Báo cáo triển khai preprocessing v6 / orchestrator v5

Bổ sung ngày 23/10: đã sửa bộ đọc JSONL cho ký tự Unicode và tái hiện/khắc phục lỗi cột 841 của IT4025 trang 264–363. Xem [báo cáo sửa lỗi](JSONL_FIX_REPORT_20261023.md); số 30 kiểm thử bên dưới là mốc triển khai 22/10. Bằng chứng hồi quy mới nằm trong `test_jsonl_evidence_20261023.json`.

## Phạm vi phiên bản

Kế thừa `colab_orchestrator_v4` (134 gói độc lập), tạo runtime/notebook và BASE riêng. Không sửa bộ 134 input, PDF gốc, core v5 chính thức, các runtime trước hoặc cơ sở dữ liệu kiểm duyệt. Đầu ra vẫn cùng schema để có thể kiểm tra/nhận lại kết quả cũ, nhưng ghi rõ `preprocessing_version=6.0.0` cho lượt xử lý mới. Kết quả legacy được giữ nguyên ZIP và version gốc.

## Nguyên nhân đã xử lý

IT4906 chứa ảnh nền RGB 2×8 được vẽ 24.378 lần/trang ở bảy trang. Native trước đây tạo crop/context/record cho từng mảnh, rồi OCR xử lý các request không mang kiến thức. Bản cũ còn tính lại đại diện và tập trang của mỗi nhóm ảnh trùng ở từng record; merge quét record/request nhiều lần. Chia tối đa 20 trang không giới hạn số vùng hoặc dung lượng thực.

Log Docling cho thấy lỗi `header too large` lặp trên 10 nhóm. Bản mới dùng cache cục bộ riêng, audit header/offset/hash và smoke test một trang trước queue, sau đó lưu ZIP cache đã kiểm tra lên Drive. Lỗi Docling lúc chạy dừng gói ngay batch đầu. Không khẳng định đã nạp model thành công trên Colab khi chưa chạy thực tế.

## Chứng cứ trước/sau

`REGRESSION_METRICS.json` lưu thông số và phạm vi phép đo.

| Kiểm tra | Trước | Sau |
|---|---:|---:|
| Proposal ảnh nền ở mỗi trang 3, 10, 115, 116, 122, 217, 227 | 24.378 | 0 |
| Tổng ảnh nền bị đưa vào vùng xử lý trên 7 trang | 170.646 | 0 |
| Ảnh render và OCR toàn trang | Giữ | Giữ |
| Native trang 217 với adapter mới | — | 1 record, giữ nguyên “TỐI ƯU ĐA MỤC TIÊU” |
| Routing CPU, cùng 5.000 record tổng hợp | 0,508 giây | 0,030 giây |
| Kết quả routing trên benchmark | Tham chiếu | Khớp toàn bộ field và ngân sách |
| SHA-256 input ZIP đối chiếu lại | 134 ZIP | 134 ZIP khớp index cũ |

Routing nhanh hơn khoảng 17,17 lần ở phép đo CPU tổng hợp cụ thể; không dùng tỷ lệ này để dự báo tổng thời gian corpus, VLM/GPU, CER/WER hoặc coverage. Những chỉ số chất lượng đó chưa được đo lại.

## Cơ chế vận hành

- `region_policy.py`: catalog nền đã xác minh theo hash PDF + RGB, inventory mỗi occurrence, fallback toàn trang/rủi ro cao cho ảnh không xác minh có quá nhiều vùng. Không lọc chỉ vì ảnh nhỏ.
- `native_batches.py`: dùng `get_image_info` một lần theo trang, tạo crop sau quyết định policy và báo tiến độ.
- `fast_routing.py`, `layout_merge.py`: aggregate theo hash/trang một lần, giữ score và ngân sách của bản trước.
- `merge_adapter.py`: adapter có anchor chính xác trên core đã khóa; index ID/trang, memoize hash trong một lượt, audit layout overflow. Không sửa file core.
- `page_batches.py`: giới hạn đồng thời 20 trang / 256 request / 64 MiB asset. Trang đơn vượt giới hạn dừng gói, không tự bỏ nội dung.
- `stage_guard.py`, `stage_worker.py`: CPU stage ở subprocess riêng, deadline 900 giây, tiến độ/RSS và guard RAM/disk. Kill chỉ cây tiến trình do bộ điều phối sở hữu.
- `orchestrator.py`, `warm_worker.py`: timeout model, dừng Docling ở batch lỗi đầu, giữ traceback và gate chưa hoàn tất.
- `runtime_profile.py`, `model_cache.py`: preflight có timeout, cache trọng số tại `/content`, ZIP cache trên Drive có inventory/hash và chỉ restore một lần trong phiên.
- `client.py`, `telemetry.py`: deadline tổng lệnh controller, status console ngắn, RSS/swap/state/I/O mỗi PID cùng RAM/VRAM/timing.
- `reuse_previous.py`, `unit_store.py`: nhận ZIP cũ hoàn chỉnh đã kiểm hash/member, không ghi lên BASE cũ; các lỗ tiến độ vẫn pending. Không tự nâng legacy thành chất lượng v6.
- `import_units.py`: CLI có workspace v6 mặc định riêng; raw ZIP và SQLite người duyệt được bảo toàn.

## Kiểm thử

30/30 kiểm thử đạt. Native, PDF, ZIP/hash, merge, restart, timeout và import chạy bằng code thực; backend model trong kiểm thử tích hợp được mô phỏng. Test native thực dùng trang 217 IT4906; kiểm tra cấu trúc nền dùng đủ bảy trang. Có kiểm tra model timeout, CPU subprocess timeout, Docling fail-fast, cache header lỗi, cache roundtrip, ảnh nhỏ chưa biết nguồn, overflow, ngân sách request và nhận kết quả cũ mà không sửa dữ liệu.

Core v5 vẫn được kiểm tra qua `manage.py verify` với 48 file. 134 input giữ hash theo index đã audit đủ 13.314 trang; không dựng lại hoặc đổi split/group.

## Giới hạn còn lại

Chưa chạy notebook mới với L4/High-RAM trên Colab, chưa chạy nhận dạng Docling/Paddle/Qwen thật trong đợt triển khai. Không bảo đảm Colab không mất kết nối. Cache local mới có thể cần tải model ở lần đầu; smoke test có thể dừng nếu trọng số hoặc môi trường vẫn lỗi. Catalog nền hiện chỉ xác minh mẫu IT4906; mẫu khác có quá nhiều vùng được giữ toàn trang và đưa vào review, không tự xóa. Kết quả legacy không được coi là đã áp dụng bộ lọc mới.
