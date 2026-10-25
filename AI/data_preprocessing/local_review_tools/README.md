# Nhập kết quả Google Drive và mở web kiểm duyệt

Bộ công cụ cục bộ dùng frozen core v5 và runtime JSONL adapter v6. Giao diện, cổng phê duyệt và SQLite append-only của app cũ được giữ. `serve.py` thêm trang chọn 27 học phần, đọc JSONL theo dòng LF vật lý và chỉ giữ một học phần trong cache.

Cột **Kết quả VLM** trên trang chọn học phần hiển thị **còn lại/tổng số**. Chỉ quyết định mới nhất `approve`, `correct` hoặc `reject` khớp identity của kết quả hiện tại mới làm giảm số còn lại. Mẫu chưa duyệt, tạm hoãn và quyết định cũ cần duyệt lại vẫn được tính là còn lại. Số đếm đọc trực tiếp SQLite, tự cập nhật mỗi 15 giây khi trang đang hiển thị và khi quay lại trang; không tạo hay sửa quyết định duyệt.

Dùng Python của `AI/Qwen_cpt_version/data_preprocessing/.venv/Scripts/python.exe`, tại thư mục dự án:

```powershell
$py = 'AI/Qwen_cpt_version/data_preprocessing/.venv/Scripts/python.exe'
& $py -X utf8 -u AI/data_preprocessing/local_review_tools/ingest.py --extract
& $py -X utf8 -u AI/data_preprocessing/local_review_tools/assemble.py
& $py -X utf8 -u AI/data_preprocessing/local_review_tools/restore_reviews.py
& $py -X utf8 -u AI/data_preprocessing/local_review_tools/verify.py
```

`ingest.py --extract` kiểm phạm vi 134 unit, đường dẫn và CRC khi giải nén 9 ZIP Drive trong `D:/Download`. `assemble.py` dùng `inspect_result` chính thức để kiểm mọi object, danh tính input, trang và hash ảnh; giải nén trực tiếp dữ liệu phục vụ review và gộp một lần mỗi PDF. `publish_preserved` giữ nguyên candidate, đề xuất, bucket, lý do và machine revision. Đầy đủ log/cache/packet gốc vẫn nằm trong ZIP raw. Ảnh/ZIP bất biến có thể chia sẻ lưu trữ bằng hard link; JSON metadata và SQLite được ghi độc lập.

`restore_reviews.py` chỉ sao chép sự kiện đã có của đúng PDF, giữ nguyên review ID/payload và identity. Revision khác vẫn là stale/pending. `verify.py` đối chiếu lại số trang, ID, nội dung và ảnh trước khi tạo `review_catalog.json`. Sau đó dùng `Start_Review.cmd` trong workspace để mở web; `check_web.py` chỉ gửi GET để kiểm tra API và ảnh, không gửi quyết định duyệt.

Workspace mặc định: `AI/data_preprocessing/workspaces/unit100_v6_20261022`. Các lệnh nhập có checkpoint/biên nhận; xung đột nội dung được giữ và báo lỗi. Không tạo phê duyệt hay xuất CPT tự động, không sửa frozen release hoặc workspace cũ.

## Xuất CPT theo chỉ thị chủ dữ liệu ngày 23/10/2026

`release_training.py --workspace <workspace> --out <release mới> --default-pass-never-reviewed` chụp SQLite nhất quán, giữ reject/stale/defer và development/holdout ngoài train. Chấp nhận mặc định được ghi riêng trong `policy.json`; không tạo sự kiện human review. Lấy mẫu phân tầng seed 20261023 trong `audit/sample.json`, đối chiếu ảnh và ghi `audit/findings.json` trước khi chạy `release_training.py --out <release> --finalize`.

Finalize kiểm hash ảnh nguồn, khử trùng chính xác toàn corpus, loại trùng/gần trùng với split bảo vệ theo quy tắc đã ghi và cách ly lỗi lấy mẫu. Dùng `write_training_docs.py --release <release>`, rồi `build_training_colab.py --release <release>` để đóng ZIP/notebook đúng cặp hash. Runtime train tái dùng Qwen3 1.7B đã chốt, bổ sung đọc JSONL LF vật lý, chuẩn bị token theo luồng và chẩn đoán loss trên tối đa 64 sequence. Các file nguồn/review/snapshot cũ được giữ.

Release đã chuẩn bị: `../training_releases/cpt_27courses_20261023`. Hướng dẫn trong release phân biệt chấp nhận mặc định với human-verified và ghi rõ chưa chạy GPU Colab trong lượt đóng gói này.

## Duyệt đề thi SFT hai đợt

Hub đã có mục **Đề thi SFT** tại `/sft/`. Đợt 1 chọn ảnh cho VLM; chỉ ảnh được chấp nhận mới được xuất sang Colab. ZIP kết quả nhập lại thành câu hỏi chờ duyệt đợt 2; thao tác nhập không tạo quyết định người dùng. Quyết định và danh mục đề thi nằm riêng tại `AI/Qweun_sft_version/review_workspaces/exams_20261024`, không sửa SQLite hoặc frozen core CPT. Xem `README_DUYET_HAI_DOT.md` trong workspace đó để xuất ảnh, chạy notebook và nhập kết quả.
