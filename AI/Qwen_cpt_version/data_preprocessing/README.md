# Tiền xử lý IT3170 cho Qwen2.5 Base

Chạy thử trên **một PDF học phần Thuật toán ứng dụng**, gồm 1.060 trang: `D:\bk_quizz_data\slide_processed\pdf\IT3170-Thuật toán ứng dụng.pdf`. File này gộp hai bộ bài giảng. Mã IT3170 được kế thừa từ manifest và có trạng thái `inferred`; không tự khẳng định tác giả của bản tổng hợp. Không sửa file nguồn.

Đầu ra nằm tại `outputs/it3170/`. Kết quả thực tế của lần chạy được ghi trong **`REPORT.md`**, `quality_report.json` và `validation.json`. Đây là bộ dữ liệu thử nghiệm có kiểm định: tập train chỉ gồm phần vượt qua các cổng chất lượng. Các trang còn thiếu thông tin hình/công thức được giữ trong dữ liệu chuẩn hóa và hàng đợi rà soát.

## Luồng thực thi

```text
PDF duy nhất + manifest nguồn
  -> ảnh trang + ký tự/font/baseline/bbox + ánh xạ trang gốc
  -> PP-DocLayout-M: phát hiện bố cục trên mọi trang
  -> PP-FormulaNet-S: nhận dạng các vùng công thức
  -> PP-StructureV3 đầy đủ: OCR + công thức + cấu trúc bảng trên trang cần bổ sung
  -> NFC / khoảng trắng hình học / thứ tự đọc / đoạn văn / giữ thụt lề code
  -> lọc phần lặp ở lề + che email/số liên hệ có nhãn
  -> kiểm định công thức, bảng, hình -> chấp nhận hoặc needs_review
  -> exact SHA-256 + MinHash/SimHash phát hiện gần trùng
  -> JSONL text cho CPT -> tokenizer Qwen2.5 Base + EOS -> packing 2.048 token
```

`recognize_components.py` dùng **các mô-đun bố cục/công thức của PP-StructureV3** để tránh OCR lại tất cả chữ có sẵn. `recognize.py` chạy pipeline **PP-StructureV3 đầy đủ** cho bảng/trang cần OCR. Đây là hai chế độ thực sự khác nhau, được thống kê riêng. Cấu hình CPU dùng `PP-FormulaNet-S` để phù hợp máy 8 GB RAM; có thể thay bằng mô hình lớn hơn trên máy đủ tài nguyên rồi đánh giá lại.

Đã kiểm tra bảng ký tự **thực tế của model OCR được tải**, không chỉ tên ngôn ngữ trong API: `latin_PP-OCRv5_mobile_rec` trong lần chạy này thiếu một số chữ tiếng Việt mang dấu. `ocr_capabilities.json` ghi từng ký tự thiếu, kể cả kiểm tra khả năng biểu diễn bằng Unicode NFD. Vì vậy OCR được dùng làm lớp ứng viên/nhận dạng cấu trúc; chữ native đã phục hồi và bản chép đối chiếu ảnh là lớp huấn luyện. Các vùng chỉ có ảnh chữ tiếng Việt chưa xác minh tiếp tục ở review. Có thể thay recognizer bằng model có đủ bảng ký tự tiếng Việt rồi đo CER/WER trên bộ chuẩn trước khi nhận tự động.

## Các tệp chính

| Tệp | Nội dung / cách dùng |
|---|---|
| `document.json` | SHA-256 PDF, số trang, nguồn chương, bằng chứng mã học phần |
| `native_pages.jsonl` | Lớp trích xuất gốc: ký tự, font, baseline, tọa độ, hình, vector; **chưa che PII**, chỉ phục vụ audit |
| `normalized.jsonl` | Một bản ghi mỗi trang; text, block, công thức, bảng, visual, nguồn và trạng thái chất lượng |
| `assets/page_XXXX.png` | Ảnh trang nguyên vẹn để truy vết; có thể chứa PII nguồn |
| `assets/formulas/` | Ảnh cắt vùng công thức được detector tìm thấy |
| `components/`, `ppstructure/` | Kết quả nhận dạng có hash ràng buộc với tài liệu và ảnh trang |
| `formulas.jsonl` | Nguồn ảnh, LaTeX ứng viên, ngữ cảnh, diễn giải đã kiểm tra nếu có, kiểm tra cú pháp và metadata |
| `tables.jsonl` | HTML/cell structure, phương pháp nhận dạng và trạng thái kiểm tra |
| `visuals.jsonl` | Trạng thái hình; với mẫu đã kiểm tra có đỉnh/cạnh/hướng/trọng số hoặc cấu trúc bảng |
| `review_queue.jsonl` | Trang chưa đủ điều kiện huấn luyện, lý do và ảnh cần đối chiếu |
| `reviewed_annotations.jsonl` | Các kiểm tra trực tiếp ảnh nguồn của Codex; ghi rõ **không phải gold do người độc lập gán nhãn** |
| `deduplication.json` | Mẫu trùng chính xác và các cặp gần trùng; giữ số, dấu và ký hiệu trong so sánh |
| `cpt/train.jsonl` | Dữ liệu đầu vào `{"text":"..."}` cho causal continued pretraining |
| `cpt/train.metadata.jsonl` | Metadata song hành, theo đúng thứ tự các dòng train |
| `cpt/train.packed.jsonl` | `input_ids`, `attention_mask`, `labels`; tối đa 2.048 token mỗi mẫu |
| `cpt/train.packed.sources.jsonl` | Ánh xạ từng khoảng token về trang/mẫu nguồn |
| `cpt/tokenization.json` | Tokenizer/revision/hash tệp, EOS, số token và quy tắc packing |
| `split_manifest.json` | Toàn bộ một tài liệu vào train; validation/test rỗng |
| `qa/reference_metrics.json` | CER/WER trên tập con hai trang chép từ ảnh bởi Codex; **không đại diện toàn tài liệu** |

Các thư mục ảnh, cache, môi trường và lớp raw dung lượng lớn đã được đưa vào `.gitignore` cục bộ. Chúng vẫn tồn tại trong thư mục AI và có thể tái tạo. Các tệp audit/raw chưa che PII cần được quản lý riêng khi chia sẻ; bộ `cpt/` là lớp dùng để huấn luyện.

## Quy tắc làm sạch và kiểm định

- Unicode NFC, giữ nguyên dấu tiếng Việt, số, dấu toán học, ngoặc và nội dung mã. Khoảng trắng mất trong lớp text được phục hồi từ khoảng cách giữa ký tự, thay vì đoán từ. Chỉ số trên có cờ PDF được giữ dạng `^{...}`; những vùng toán còn lại phải kiểm tra.
- Thứ tự đọc dùng whitespace cuts theo cột/vùng. Nối dòng chỉ trong cùng block và khi có dấu hiệu tiếp diễn; code giữ dòng và thụt lề. Các đoạn mã bị tách thành nhiều block được ghép bằng tọa độ.
- Chỉ lọc số trang ở lề và nội dung lề lặp đủ tần suất. Ảnh nền lặp được nhận diện qua hash. Trang ít chữ vẫn tồn tại, được chuyển sang kiểm tra hình. Chỉ các bìa/logo/cảm ơn **đã xem ảnh** mới có trạng thái `excluded_non_content`.
- Các ký tự private-use chưa giải mã được bị giữ lại trong audit và gắn cờ; chỉ ánh xạ bullet `Wingdings2/U+F097` đã đối chiếu sang `•`. Không xóa các glyph toán chưa biết.
- Native code có ưu tiên riêng. Nếu detector nhầm vòng `for` thành công thức, ứng viên chồng lên vùng code được ghi vào `ignored_predictions`, không thay mã nguồn bằng LaTeX OCR sai.
- Exact hash loại trùng **trên các mẫu đã đủ điều kiện train**. MinHash với 128 permutations, seed 42, và SimHash phát hiện gần trùng. Những cặp gần trùng chỉ dùng để nhóm cùng split; không tự xóa slide vì có thể khác số hoặc bước minh họa.
- LaTeX syntax check chỉ là smoke test ngoặc/khả năng chuyển đổi; không chứng minh đúng công thức. `semantic_verified` chỉ bật ở ví dụ đã đối chiếu ảnh. Công thức OCR sai vẫn nằm trong review, không được dùng làm kiến thức train.
- Email và số điện thoại/CCCD/MSSV có nhãn được che bằng placeholder. Không xóa các số dài không có nhãn vì có thể là giới hạn của bài toán. Bộ phát hiện PII có phạm vi cụ thể, không được coi là đầy đủ cho mọi loại dữ liệu cá nhân.
- `confidence.score=null` với chữ PDF/kiểm tra trực tiếp vì chưa có xác suất được hiệu chuẩn; trường `basis` giải thích nguồn. Điểm detector/OCR nếu backend trả về được giữ riêng. Không gán tùy tiện độ tin cậy 0,99.

## Hình, bảng, biểu đồ

Các ví dụ đã kiểm tra trực tiếp gồm tràn số với `10^{18}`, bảng bàn phím SMS, bảng input/output, đồ thị có hướng và đồ thị Kruskal. Mỗi ví dụ được ràng buộc bằng cả SHA-256 PDF và SHA-256 ảnh trang. Nếu nguồn thay đổi, annotation cũ bị từ chối.

Người dùng chưa có endpoint VLM. Vì vậy các sơ đồ còn lại giữ nguyên ảnh và trạng thái `pending`; pipeline **chưa mô tả đầy đủ mọi hình của 1.060 trang**. Không tạo mô tả hàng loạt bằng suy đoán. `vision.py` đã có đường tích hợp endpoint tương thích OpenAI, xuất proposal theo schema có đỉnh/cạnh, hướng, trục, đơn vị, giá trị đọc được, xu hướng, facts và uncertain. Proposal mặc định `verified=false` và chưa tự vào tập train.

Khi có máy chủ VLM, ví dụ cách gọi:

```powershell
.\.venv\Scripts\python.exe .\src\vision.py --out .\outputs\it3170 --endpoint http://localhost:8000/v1 --model TEN_MODEL_VLM --pages 129,300,500,1042
```

Nếu endpoint cần khóa, đặt biến môi trường `VLM_API_KEY` ở máy chạy. Sau khi đối chiếu ảnh, ghi transcript/quan hệ vào `reviewed_annotations.jsonl` với `document_sha256`, `render_sha256`, `verified`, `reviewer`, `evidence`, `verification_level`. Chỉ tái sử dụng annotation cho đúng hash đã xem; không đổi hash để hợp thức hóa bản chép cũ.

## Cài đặt và chạy lại trên Windows

Từ thư mục này, Python 3.11:

```powershell
uv venv .venv --python 3.11
uv pip install --python .venv/Scripts/python.exe -r requirements-paddle.txt
.\run.ps1 -Mode hybrid -Tokenizer Qwen/Qwen2.5-7B -SequenceLength 2048
```

`requirements.lock.txt` lưu bộ phiên bản thực tế đã cài. `paddlepaddle==3.2.2` được chọn sau khi 3.3.1 gặp lỗi oneDNN/PIR trên máy này. Chi tiết kỹ thuật: [issue của PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR/issues/18162). Kết quả inference được lưu theo trang và tiếp tục từ cache ở lần chạy sau. Mô hình Paddle mặc định được tải vào cache của PaddleX trong tài khoản Windows; `.venv`, dữ liệu và mã pipeline nằm trong AI.

Các chế độ:

- `-Mode native`: chỉ trích xuất PDF + kiểm định + đóng gói; chưa chạy Paddle cho các trang chưa có cache.
- `-Mode hybrid`: phân tích layout/công thức mọi trang, sau đó PP-StructureV3 đầy đủ cho bảng/trang cần OCR.
- `-Mode full`: PP-StructureV3 đầy đủ trên tất cả trang; tốn thời gian CPU hơn.

Nếu chỉ cần dựng lại dataset sau khi kiểm tra thêm ảnh:

```powershell
.\.venv\Scripts\python.exe .\src\build_dataset.py --out .\outputs\it3170 --annotations .\outputs\it3170\reviewed_annotations.jsonl
.\.venv\Scripts\python.exe .\src\pack_qwen.py --out .\outputs\it3170 --tokenizer Qwen/Qwen2.5-7B
.\.venv\Scripts\python.exe .\src\validate.py --out .\outputs\it3170
.\.venv\Scripts\python.exe -m pytest tests -q
```

## Dùng cho continued pretraining

Chọn **một** trong hai đầu vào: `cpt/train.jsonl` để trainer tự tokenize, hoặc `cpt/train.packed.jsonl` nếu trainer nhận token sẵn. Không nạp cả hai để tránh học trùng. `text` là văn bản nguồn/diễn tả hình có kiểm tra, không có cặp hỏi-đáp hay chat template.

Packing dùng tokenizer **Qwen/Qwen2.5-7B Base**, thêm EOS thật của tokenizer sau mỗi mẫu. Mỗi mẫu tương ứng một trang đủ điều kiện; đoạn cuối được giữ, không cắt mất token. Packing liên tục cho phép attention qua ranh giới mẫu và có EOS phân cách; đây không phải attention dạng block-diagonal. `labels` bằng `input_ids`, để model causal LM dịch nhãn một lần trong loss. Đoạn cuối ngắn cần được data collator padding với `labels=-100` ở vị trí pad khi ghép batch. Khi chọn checkpoint Qwen khác, tokenize lại bằng đúng tokenizer/checkpoint đó.

Tài liệu được giữ toàn bộ trong một split vì có hai phiên bản chồng lặp. Validation và test rỗng **có chủ đích**; cần tài liệu/nhóm nguồn độc lập để đánh giá, không chia ngẫu nhiên các slide gần nhau. Dataset nhỏ này dùng thử pipeline và chạy smoke training, chưa đủ để kết luận hiệu quả CPT hoặc độ tổng quát.

## Chỉ số chất lượng

`quality_report.json` tách metric đo được với metric chưa có ground truth:

- Source Traceability: tính trên toàn bộ trang chuẩn hóa có ánh xạ tới PDF/trang gốc.
- Duplicate Rate: trùng chính xác trong các trang đủ điều kiện; near duplicates báo riêng.
- CER/WER toàn tập, Formula Accuracy, Diagram Fact Precision và Information Coverage: `null/not_measured` khi chưa có bản chuẩn độc lập. CER/WER của hai trang QA nằm riêng trong `qa/`, không thay thế đánh giá toàn tập.

`validate.py` kiểm tra SHA nguồn/ảnh, đủ trang, metadata, PII email, tập train không chứa mục needs_review, exact duplicates, split và **toàn bộ token** sau packing. Những kiểm tra này xác nhận tính toàn vẹn của pipeline; việc kiểm chứng kiến thức học thuật cần bộ chuẩn được gán nhãn.

Tài liệu kỹ thuật chính thức: [PP-StructureV3](https://paddlepaddle.github.io/PaddleOCR/main/en/version3.x/pipeline_usage/PP-StructureV3.html), [Qwen2.5 Base](https://huggingface.co/Qwen/Qwen2.5-7B).
