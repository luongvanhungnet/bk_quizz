# Colab vẫn “Connecting” trên L4: chẩn đoán và bản sửa

## Kết luận từ bằng chứng hiện có

Ảnh notebook `Colab_V5_L4_HighRAM.ipynb` hiển thị đồng thời:

1. `Saving failed since 12:11 AM` và **`Automatic saving failed. This file was updated remotely or in another tab`**.
2. Trạng thái **Connecting**.
3. Đang ở input **03/14**, log cuối là sao chép input/checkpoint vào `/content/.../_checkpoint_restore/`, chưa phải chạy VLM.

Người vận hành xác nhận **file telemetry trên Drive vẫn cập nhật đều trong lúc Connecting**. Vì vậy, ít nhất tiến trình monitor và đường ghi Drive vẫn hoạt động. Không có căn cứ gọi đây là runtime đã chết, GPU bị lỗi hoặc hết RAM. Tuy nhiên, monitor chạy riêng nên điều này **không chứng minh tác vụ OCR/VLM chính đang tiến triển**; cần xem các `stage_start`/`stage_end`, tiến độ batch/transfer và tài nguyên.

Thông báo autosave xác nhận Colab đang từ chối lưu do xung đột revision tài liệu. Các khả năng gồm một tab/thiết bị khác, ghi đè file qua Drive, hoặc lỗi đồng bộ tài liệu của Colab. Không thể xác định chính xác tác nhân chỉ từ ảnh, cũng không thể khẳng định hai tab đang cùng mở. Triệu chứng tương tự đã được ghi nhận trong [issue của dự án Colab](https://github.com/googlecolab/colabtools/issues/2707); các bình luận không phải kết luận về nguyên nhân của lượt chạy này.

**L4/High-RAM không sửa lỗi autosave hoặc kết nối trình duyệt.** Hai lỗi xuất hiện cùng lúc chưa chứng minh autosave gây Connecting. Chẩn đoán hợp lý nhất hiện tại là lỗi ở kết nối/đồng bộ giao diện, trong khi VM còn hoạt động; bước khôi phục có thêm chi phí I/O và lượng output không cần thiết từ code.

## Điểm yếu tìm thấy trong bộ điều phối

| Điểm yếu | Hệ quả | Sửa trong bản 22/10 |
|---|---|---|
| `copy_verified` hash toàn bộ file Drive trước rồi đọc lại để copy, dù receipt đã có SHA-256 | Hai lượt đọc nguồn trên đường Drive → VM | Dùng hash từ receipt, hash luồng copy và kiểm lại file đích; vẫn từ chối dữ liệu sai hash |
| Replay mọi delta theo thứ tự cũ → mới, ghi đè các bản metadata đã lỗi thời | Nhiều lần đọc/ghi và khó thấy tiến độ thật | Khôi phục phiên bản cuối theo index, duyệt delta mới → cũ; index mới có inventory từng archive để bỏ qua ZIP không cần |
| Xóa ZIP tạm ngay sau mỗi delta, không nhận biết file đã khôi phục khi thao tác bị ngắt | Tiếp tục khôi phục tốn I/O lặp; `manifest.json` tồn tại có thể khiến bỏ qua phần còn thiếu | Giữ cache ZIP đến khi restore hoàn tất, xác minh file có sẵn, thêm marker khôi phục chưa xong; `register_one` nhận marker này |
| In `TRANSFER_COMPLETE` kèm toàn bộ JSON/đường dẫn dài | Output notebook phình và tăng tải render/autosave | Log truyền ngắn; tiến độ restore tổng quát; client chỉ gửi tối đa 20 dòng/3.500 ký tự phần log trong mỗi lần đọc |
| Notebook lưu output theo mặc định | Log vận hành đi vào revision `.ipynb` | `metadata.colab.private_outputs=true`; người vận hành kiểm tra lại tùy chọn “Omit code cell output when saving” |
| Sampling tài nguyên và sync Drive cùng thread; daemon chờ sync trước khi trả IPC | I/O telemetry chậm có thể làm chậm phản hồi và che diễn biến tài nguyên | Thread sampling riêng, sync riêng; trả IPC trước khi yêu cầu sync |
| Không có khóa chống hai daemon cùng BASE trên một VM | Các phiên có thể ghi state đè nhau | Khóa hệ điều hành theo BASE trên cùng VM; tự giải phóng khi tiến trình thoát |

Google cũng khuyến nghị giảm đọc/ghi Drive và làm việc với archive trên VM trong [Colab FAQ](https://research.google.com/colaboratory/faq.html). Đây là cơ sở cải thiện I/O, không phải bằng chứng Drive hiện bị quota hoặc outage.

## Những gì vẫn được bảo toàn

- Core **v5.0.0**, Qwen2.5-VL-7B, prompt, bộ 14 input, batch 20 trang, page map và các gate human review.
- Toàn bộ ZIP checkpoint cũ, manifest/hash, output OCR/VLM và hồ sơ kiểm toán trên Drive. Không viết lại index checkpoint cũ chỉ để thêm inventory; delta phát sinh mới mới có thêm trường này.
- Native text, ký hiệu toán, kết quả gốc và SQLite kiểm duyệt. Không tự xác minh VLM hoặc xuất nội dung chưa kiểm duyệt sang CPT.
- Kiểm tra SHA-256 khi truyền. Upload kết quả vẫn được kiểm tra file đích trên Drive rồi mới commit/chuyển input.
- Runtime L4 trước sửa được giữ tại `releases/l4_before_stability_20261022`; runtime v3/T4 trước đó cũng được giữ.

Index cũ thiếu inventory từng archive vẫn phải mở nhiều ZIP để tìm file, nhưng không còn ghi đè phiên bản cuối bằng phiên bản cũ. Các input trước vẫn có thể phải staging lại trên VM mới để phục hồi dependency/cache phân bổ giữa các gói. Bản sửa không hứa loại bỏ toàn bộ việc đọc lại đó.

Khóa coordinator chỉ bảo vệ **cùng một VM**. Nó không ngăn một VM khác cùng ghi BASE và không sửa xung đột autosave notebook. Chỉ vận hành một queue ghi vào BASE tại một thời điểm.

## Cách khôi phục phiên hiện tại

1. **Không chạy thêm một queue cùng BASE khi telemetry phiên cũ vẫn cập nhật.** Xem `downloads/latest_index.json` và `queue_state.json` để biết input nào đã lưu/commit; không chỉ dựa vào trạng thái Connecting. Chờ input hiện tại hoàn thành nếu các stage/batch vẫn tiến triển.
2. Bảo toàn nội dung notebook đang mở bằng **File → Download → Download .ipynb**, hoặc **File → Save a copy in Drive** với tên riêng. Nếu dùng `Show diff`, đọc khác biệt trước khi lưu đè. Đóng các tab/editor khác của cùng file nếu có. Không ghi đè file notebook đang mở bằng upload từ máy tính.
3. Sau khi đã bảo toàn notebook, reload/reconnect trang hiện tại để thử gắn lại phiên cũ. Nếu vẫn Connecting, kiểm tra **Runtime → Manage sessions**. Việc mở bản sao notebook không đảm bảo tự gắn vào cùng kernel; không bấm chạy queue trong bản sao khi phiên cũ còn chạy.
4. Khi input đã có kết quả lưu bền vững, đóng SESSION/phiên cũ trước khi dùng bản mới. Nếu phải kết thúc VM đang kẹt, nhóm chưa checkpoint có thể phải chạy lại; các checkpoint Drive đã có được giữ.
5. Thêm **`colab_orchestrator_v3_l4_stable_runtime.zip`** vào **MyDrive/BKQuiz_cpt_data**. Không cần upload lại 14 input. Runtime mới có tên riêng; không đổi tên runtime cũ để giả lập bản mới.
6. Mở **`Colab_V5_L4_Stable.ipynb`** thành một tài liệu mới có tên riêng; chọn **Python 3 / L4 / High-RAM**. Kiểm tra **Edit → Notebook settings → Omit code cell output when saving this notebook**. Giữ `BASE=.../BKQuiz_v5_drive_v3`, `BATCH_PAGES=20`, `MAX_INPUTS=1`. Chạy lần lượt các cell. Nếu kernel đã import runtime cũ, bootstrap yêu cầu khởi động lại trước khi nạp bản sửa.
7. Dùng Google Drive để tải kết quả sau. Không xóa `queue_state.json`, checkpoint hoặc cache để thử sửa lỗi kết nối.

Colab mô tả tùy chọn không lưu output và yêu cầu cookie cho output/service worker trong [FAQ chính thức](https://research.google.com/colaboratory/faq.html). Nếu lỗi giao diện tiếp diễn sau khi dùng một tài liệu riêng, thử trình duyệt đã cập nhật, tắt tạm extension chặn nội dung cho Colab và kiểm tra quyền cookie cho `googleusercontent.com`. Đây là các bước khoanh vùng trình duyệt, không phải nguyên nhân đã được xác nhận trên máy này.

## Quan sát sau sửa

`BASE/telemetry/live_status.json` chứa:

- `sampled_unix`: lần lấy mẫu tài nguyên gần nhất.
- `drive_synced_unix`: lúc bản trạng thái được xuất lên Drive.
- PID, các stage đang hoạt động, RAM khả dụng, RSS theo tiến trình và VRAM.

`events_*.jsonl` vẫn giữ chi tiết stage, byte truyền và tiến độ restore. Bản log đầy đủ được giữ trên VM và trong ZIP xuất, dù màn hình chỉ hiện phần ngắn. Nếu Drive bị kẹt, file trạng thái trên Drive có thể cũ dù sampling cục bộ còn chạy; trạng thái cũ không đủ để kết luận OOM.

## Kiểm thử và giới hạn kết luận

Xem `tests_stability_20261022.txt` và `test_evidence_stability_20261022.json`. Kiểm thử gồm các regression trước đó, sai hash, cache hỏng, restore bị ngắt sau khi đã ghi manifest, tương thích index cũ, sampling khi sync Drive chậm, giới hạn output và khóa coordinator.

Kết quả local: **35/35 test đạt**, không failure/error, khoảng **53,36 giây**. `manage.py verify` xác nhận **48/48 file** của core v5.0.0 giữ nguyên hash.

| Fixture: 6 delta, 1 ảnh bất biến + manifest cập nhật | Trước sửa | Sau sửa |
|---|---:|---:|
| Index cũ: số lần mở ZIP nguồn | 12 | 6 |
| Index cũ: số byte ZIP nguồn đọc | 4.950 | 2.475 |
| Index mới có inventory từng archive: số lần mở ZIP nguồn | 12 | 2 |
| Index mới: số byte ZIP nguồn đọc | 4.950 | 934 |

Đầu ra cuối của hai bản có hash giống nhau; mọi file checkpoint nguồn vẫn giữ nguyên hash. Fixture rất nhỏ, dùng để xác minh số lượt đọc và tính đúng của thuật toán. Không dùng thời gian fixture để dự đoán thời gian chạy toàn corpus. Index cũ giảm 50% byte ZIP đọc trong fixture nhờ bỏ lượt pre-hash nguồn; tổng I/O còn có đọc index, hash file local và kiểm tra nội dung ZIP.

`evidence/verify_stability.py` chạy thêm phép thử I/O trên checkpoint tổng hợp để so sánh code L4 trước sửa với bản mới. Số byte đọc và số ZIP mở là số đo fixture cục bộ, **không phải benchmark tốc độ Google Drive hoặc L4 thật**. Index cũ và index mới được đo riêng; không áp mức giảm của index mới cho lịch sử cũ.

Chưa có lượt chạy Colab sau sửa để xác nhận hết Connecting hoặc autosave conflict. Không thay đổi model hay tăng yêu cầu GPU để gọi đây là đã khắc phục toàn bộ sự cố.
