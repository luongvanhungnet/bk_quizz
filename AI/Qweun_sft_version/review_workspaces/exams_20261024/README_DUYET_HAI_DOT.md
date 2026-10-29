# Duyệt ảnh đề thi và câu hỏi VLM

Web dùng chung với lần duyệt CPT: <http://127.0.0.1:8765/>.

Hàng đợi hiện có **7.305 ảnh từ 7.231 trang PDF**, thuộc 374 tài liệu / 49 nhóm tên môn. Bảy trang cuộn dài được chia thành các ảnh chồng lấn để đọc được chữ. Các trang/câu có vấn đề được gom từ hàng đợi OCR, câu bị cách ly và câu bị loại khi dựng tập SFT. PDF gốc và tập SFT đã đóng gói trước đây giữ nguyên.

## Kết quả tự động ngày 25/10/2026

Đã áp dụng OCR v3 cho đủ 7.305 ảnh: **138 ảnh cần duyệt thủ công**, **7.138 ảnh tự chuyển VLM**, **4 ảnh giữ lựa chọn VLM của bạn**, **5 trang lấy TXT** và **20 trang trắng**. Không giới hạn hàng đợi bằng cách lấy 499 ảnh đầu tiên. OCR, native text và kiểm tra thị giác của máy là bằng chứng sàng lọc; chưa đo xác suất thất bại VLM trên GPU.

18 câu hỏi từ 5 trang TXT đang chờ duyệt đợt 2, chưa có câu nào được chấp nhận tự động. Quyết định cũ của bạn vẫn giữ đủ 4 sự kiện; 123 tệp của release SFT cũ và danh mục ảnh vẫn khớp hash. Báo cáo: `AUTO_TRIAGE_VALIDATION_REPORT.json`; danh sách thủ công: `auto_triage_20261025/manual_review_queue.jsonl`.

Bộ kiểm thử workflow đạt 140 bài; sau tối ưu tốc độ web, các bài store/web được chạy lại kèm kiểm tra phát hiện PDF thay đổi giữa hai yêu cầu. Notebook và runtime đã được cập nhật cho quyền xử lý tự động; chưa chạy GPU/Colab trong lượt này.

## Đợt 1: tự động lọc ảnh và duyệt phần rủi ro

Mở <http://127.0.0.1:8765/sft/?stage=1>, hoặc chạy `Start_Review.cmd` trong thư mục này.

Theo yêu cầu ngày 25/10/2026, hệ thống dùng lớp chữ PDF, OCR tiếng Việt + tiếng Anh và đặc trưng ảnh để phân luồng riêng với quyết định của người dùng:

- **Tự động · TXT / OCR**: văn bản đủ điều kiện tách câu hỏi; giữ nguyên TXT và bằng chứng. Điều kiện bảo thủ để tránh mất hình, bảng, công thức, dấu đáp án, chú thích PDF hoặc cấu trúc lựa chọn.
- **Tự động · chuyển VLM**: ảnh đọc được nhưng cần VLM giữ bố cục, dữ kiện thị giác hoặc cách đánh dấu đáp án.
- **Tự động · trang trắng**: không đưa vào tách câu hỏi; có thể xem lại và thay đổi bằng bộ lọc.
- **Cần duyệt thủ công**: ảnh có dấu hiệu khó đọc, thiếu bằng chứng, lỗi xử lý chưa khắc phục, hoặc quyết định Tạm hoãn / nguồn thay đổi của bạn.

Mục tiêu dưới 500 ảnh thủ công không phải giới hạn cắt danh sách. Điểm OCR và điểm sàng lọc chưa phải xác suất VLM thất bại đo trên GPU. Những câu thiếu đáp án vẫn được giữ thiếu đáp án, không vì vậy mà coi ảnh là không đọc được.

1. Chọn học phần và trạng thái. Mặc định chỉ hiện mục cần duyệt thủ công, tạm hoãn hoặc cần duyệt lại.
2. Đối chiếu ảnh nguồn. Bấm ảnh để phóng to; cuộn bên trong ảnh để đọc phần dưới. Văn bản native cũ chỉ dùng tham khảo.
3. **↑ Dùng ảnh này cho VLM** cho phép đưa đúng ảnh này vào gói tách chữ. **↓ Loại ảnh** loại khỏi input VLM. **Tạm hoãn** giữ lại để xem sau và chưa đưa vào VLM.
4. Dùng ←/→ để chuyển ảnh, ↑ để chọn, ↓ để loại, H để hoãn. Khi đang nhập ghi chú, phím tắt không lưu quyết định.
5. Muốn thay đổi quyết định, chọn bộ lọc Tất cả / Đã loại / Đã chấp nhận rồi lưu quyết định mới. Lịch sử cũ được giữ lại.

Chọn ảnh ở đợt 1 **chưa chấp nhận các câu hỏi trong ảnh**. Các trạng thái tự động có chính sách và bằng chứng riêng, không tạo sự kiện duyệt của người dùng. Quyết định bạn lưu luôn được ưu tiên.

## Đưa ảnh đã chọn sang Colab

Bấm **Tách câu hỏi từ TXT / OCR** để tạo câu hỏi chờ duyệt đợt 2 cho các trang thuộc luồng TXT. Trang có cấu trúc chưa hỗ trợ được báo trong kết quả để chuyển VLM; không tự phê duyệt câu hỏi.

Bấm **Xuất ảnh đủ điều kiện sang Colab**. Gói chứa ảnh bạn đã chọn và ảnh `auto_vlm` thuộc chính sách tự động hiện tại, tối đa 100 ảnh / 128 MiB mỗi ZIP. TXT/OCR và trang trắng không tiêu tốn lượt VLM. Không có ảnh đủ điều kiện thì không tạo ZIP input.

Bấm **Notebook và hướng dẫn Colab** để tải notebook, runtime ZIP đúng cặp hash và hướng dẫn. Notebook hiện nằm tại `colab/BKQuiz_SFT_Exams_VLM_Round2.ipynb`; hướng dẫn chi tiết ở `colab/HUONG_DAN_COLAB.md`.

Các tệp cho Colab đặt trong Drive:

- `MyDrive/BKQuiz_SFT_EXAMS/`: runtime ZIP.
- `MyDrive/BKQuiz_SFT_EXAMS/inputs/`: ZIP ảnh đã duyệt được web xuất.
- `MyDrive/BKQuiz_SFT_EXAMS/results/`: ZIP kết quả VLM để tải về nhập lại web.

Nếu thay đổi lựa chọn sau khi đã xuất, xuất lại bộ input tương ứng; tránh chạy nhầm input cũ trên Colab. Kết quả của ảnh đã bị thu hồi hoặc thay đổi hash sẽ không được nhập. Không xóa PDF, ảnh nguồn hoặc quyết định cũ để chạy lại.

Runtime kế thừa Qwen2.5-VL-7B-Instruct NF4 của pipeline CPT, yêu cầu GPU L4 hoặc tương đương. VLM chỉ chép chữ, câu hỏi, lựa chọn, khóa đáp án và lời giải nhìn thấy; không tự giải hoặc bổ sung đáp án còn thiếu. Lỗi, output bị cắt và bản trả lời thô được giữ lại. Chưa chạy GPU thật trong bước thiết lập này.

## Đợt 2: loại câu hỏi lỗi

Câu hỏi từ TXT/OCR được đưa trực tiếp vào hàng đợi đợt 2. Sau khi Colab tạo ZIP kết quả, tải về máy và dùng **Nhập ZIP kết quả VLM** trên web. Tất cả câu mới nhập đều chờ bạn duyệt.

Mở <http://127.0.0.1:8765/sft/?stage=2>. Đối chiếu từng câu với ảnh gốc:

- **Chấp nhận câu hỏi** khi chữ, lựa chọn, dữ kiện và đáp án/lời giải ghi trên nguồn được giữ đúng.
- **Loại câu hỏi** khi bị lỗi hoặc không sử dụng được.
- Có thể mở **Sửa nội dung trước khi chấp nhận** để sửa bản tách. Bản máy ban đầu vẫn được giữ riêng.
- Câu thiếu đáp án có thể được giữ để bổ sung sau, nhưng chưa đủ điều kiện tạo mẫu SFT hỏi–đáp. Không mặc định lấy lựa chọn của người làm bài làm đáp án đúng.

Bấm **Xuất câu hỏi đã duyệt đợt 2** để lấy JSONL có bản đã chấp nhận và nguồn gốc. Đây là đầu vào cho bước dựng lại SFT sau này; không tự ghi đè tập SFT cũ hoặc chạy train.

## Lưu trữ và kiểm tra

- `pages.jsonl`, `manifest.json`: danh mục ảnh có danh tính gắn với PDF / trang / vùng ảnh.
- `assets/`: ảnh dựng khi xem, kèm hash và thông tin render.
- `human_reviews.sqlite3`: lịch sử append-only của riêng dữ liệu đề thi; không dùng chung SQLite duyệt CPT.
- `auto_routing_current.json`, `auto_triage_20261025/`: chính sách, bằng chứng native/OCR, hash, báo cáo và kiểm tra ảnh mẫu.
- `auto_text_results/`: TXT gốc, kết quả tách câu hỏi và báo cáo nhập.
- `colab/exports/`: input và manifest xuất từ quyền xử lý đợt 1 (người dùng / tự động).
- `colab/returns/`: ZIP trả về, raw output, lỗi và báo cáo nhập.
- `approved_questions/`: JSONL chỉ chứa câu qua đợt 2.
- `ui_evidence/`, `VALIDATION_REPORT.json`: chứng cứ và kết quả kiểm tra triển khai.

Khi PDF, ảnh hoặc kết quả VLM thay đổi, quyết định cũ không được tự áp cho phiên bản mới. Bộ chia train/validation/test và khử trùng sẽ được chạy lại khi dựng release SFT tiếp theo.
