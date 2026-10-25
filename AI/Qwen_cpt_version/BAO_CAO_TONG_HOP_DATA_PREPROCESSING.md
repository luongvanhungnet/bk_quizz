# Báo cáo tổng hợp quá trình triển khai data preprocessing qua các phiên bản

**Dự án:** BKQuiz — học phần Thuật toán ứng dụng, IT3170  
**Phạm vi tổng hợp:** các đợt preprocessing và kết quả đã lưu đến ngày 19/10/2026, múi giờ Asia/Bangkok  
**Thư mục thực hiện:** `D:\BKQuiz\AI\Qwen_cpt_version`

## 1. Mục tiêu và dữ liệu đầu vào

Tác vụ là chuyển slide PDF thành dữ liệu văn bản có cấu trúc để continued pretraining (CPT), đồng thời giữ được công thức, bảng, mã nguồn và kiến thức thể hiện bằng hình. Đầu ra phải truy ngược được về tài liệu, trang và vùng ảnh nguồn; thông tin chưa xác minh được đưa vào hàng đợi rà soát.

Đã làm việc với **một tệp PDF gồm 1.060 trang**, không phải 1.060 tài liệu độc lập:

```text
D:\bk_quizz_data\slide_processed\pdf\IT3170-Thuật toán ứng dụng.pdf
```

SHA-256 tài liệu:

```text
c6c829f14bf2a8a1e42b6919d729fdf23865ef4734eb25817f183103dd877087
```

PDF chứa hai bộ bài giảng được gộp. Mã IT3170 được kế thừa từ manifest với trạng thái suy luận; không tự xác nhận tác giả của toàn bộ bản tổng hợp. File PDF gốc được giữ nguyên.

Luồng tổng quát đã được xây dựng:

```text
PDF
  → native text + ảnh trang + tọa độ + font/baseline + vector
  → layout detection và định tuyến vùng
  → text / OCR / formula / table / diagram extraction
  → chuẩn hóa, bảo toàn ký hiệu, lọc phần lặp, che PII theo luật
  → exact dedup + near-duplicate grouping
  → kiểm tra cấu trúc, bằng chứng và ngữ nghĩa
  → CPT JSONL hoặc Review Queue
  → tokenizer đúng model đích + EOS + packing + source map
```

Trong báo cáo này, **đã triển khai** nghĩa là có code/notebook/artifact; **đã chạy** nghĩa là có output thực tế; **hợp lệ cấu trúc** nghĩa là vượt validator; **đã xác minh ngữ nghĩa** nghĩa là đã đối chiếu nội dung với nguồn. Các trạng thái này không được dùng thay cho nhau.

## 2. Các phiên bản và phạm vi thực thi

| Giai đoạn | Thư mục | Nội dung chính | Trạng thái thực tế |
|---|---|---|---|
| Tiền xử lý ban đầu | `data_preprocessing` | Trích xuất, layout, công thức/bảng trên CPU; chuẩn hóa, dedup, review và CPT | Đã chạy trên toàn bộ 1.060 trang ở lớp native/layout; chỉ một phần đủ điều kiện train |
| Hybrid local–Colab | `hybrid_preprocessing` | Tách công việc CPU và GPU; thử OCR/formula/VLM theo trang | Local đã chạy; đã nhận kết quả Colab cho 12 trang |
| Region v1 và scored routing | `region_preprocessing` | Crop theo vùng, extractor chuyên dụng, batch/cache; thêm luật tính điểm 4–8% | Đã nhận kết quả GPU với lịch 56 vùng VLM, 644 formula và 16 table |
| Region v2 | `region_preprocessing_v2` | Sửa schema, tích hợp bảng, routing công thức; so sánh 3B–7B | Đã sửa và kiểm chứng bảng trên CPU; đã nhận pilot Colab 3B/7B và kết quả công thức |
| Region v3 | `region_preprocessing_v3` | Đồ thị ba bước, bằng chứng bbox, cây trạng thái, benchmark và holdout | Đã triển khai và nhận kết quả pilot GPU; 1/6 crop VLM hợp lệ |
| Region v4 | `region_preprocessing_v4` | Schema chung, hình học PDF + VLM, đọc từng board, ngân sách token/VRAM và retry | Đã đóng gói, kiểm thử và mô phỏng luồng; **chưa có kết quả Qwen GPU v4** trong phạm vi báo cáo |

**Lưu ý tên phiên bản:** các tên run như `it3170_regions_v4` hoặc `it3170_scored_v3` là vòng thử nội bộ trong thư mục `region_preprocessing`. Chúng không phải bản phát hành `region_preprocessing_v4`. Run chính của bản v4 hiện tại là `region_preprocessing_v4/runs/it3170_v4_20261019_final`.

## 3. Công nghệ được dùng cho từng phần công việc

| Công đoạn | Công nghệ/cách làm đã sử dụng | Vai trò cụ thể | Phiên bản/giai đoạn |
|---|---|---|---|
| Đọc cấu trúc PDF | Python, PyMuPDF | Lấy text, ký tự, font, bbox, baseline, ảnh và đường vẽ vector; render trang | Ban đầu và được kế thừa qua các bản |
| Phát hiện bố cục | PaddleOCR, PP-DocLayout-M | Xác định text, formula, table, image/chart, header/footer và số trang | Ban đầu; hybrid; region tái sử dụng cache đúng hash |
| Pipeline tài liệu đầy đủ | PP-StructureV3 | Kết hợp OCR, formula và bảng ở những trang cần bổ sung | Ban đầu chạy đầy đủ trên 86 trang |
| OCR ảnh chứa chữ | PaddleOCR; ban đầu có recognizer Latin PP-OCRv5, hybrid cấu hình PP-OCRv3 `lang=vi` | Đọc chữ raster, giữ output/capability audit; không mặc định thay native text | Ban đầu và hybrid Colab |
| Nhận dạng công thức | PP-FormulaNet-S | Crop công thức → LaTeX ứng viên; lưu nguồn, bbox và trạng thái kiểm định | Ban đầu đến v4; v4 dùng lại seed |
| Nhận dạng bảng | TableRecognitionPipelineV2, PaddleX OCRResult, native PDF cell text | Tạo cấu trúc bảng/HTML từ vùng bảng; cung cấp chữ ô từ native thay vì OCR lại tùy tiện | Region v1; sửa tích hợp ở v2; v3/v4 kế thừa |
| Hiểu hình/sơ đồ | Qwen2.5-VL-3B-Instruct | Đọc diagram/graph/chart và tạo JSON quan sát | Hybrid, region v1, baseline v2 |
| Hiểu hình bằng model lớn hơn | Qwen2.5-VL-7B-Instruct | Pilot đồ thị/cây, node/cạnh/trọng số/hướng | V2, v3; v4 giữ model này nhưng chưa chạy GPU |
| Phát hiện hình học raster | OpenCV, NumPy | Contour, Otsu/Canny, đường nối, hình tròn/hộp, HSV cho board/cell | Scored routing; v3/v4 bổ sung ứng viên hình học |
| Phân tích hình học native | PyMuPDF vector paths + luật hình học | Ghép nhãn vào node, đường nối vào endpoint, tìm ứng viên trọng số/mũi tên | V3; dùng làm đầu vào có kiểm tra ở v4 |
| Xử lý ảnh | Pillow/PIL | Crop, padding, resize, hash pixel và đổi hệ tọa độ | Hybrid/region; v4 thống nhất đường resize |
| Làm sạch chữ | `unicodedata` NFC, regex và hình học text | Phục hồi khoảng trắng, giữ số/ký hiệu/code, nối dòng có điều kiện, lọc lề lặp | Ban đầu và tái sử dụng |
| Che thông tin liên hệ | Regex và nhãn ngữ cảnh | Che email, số liên hệ/định danh có nhãn trong lớp dùng train | Ban đầu và lớp CPT kế thừa; không phải bộ PII detector bao phủ mọi trường hợp |
| Trùng chính xác | `hashlib` SHA-256 | Nhận diện text/ảnh/crop trùng, xác thực tài liệu, cache và artifact | Mọi giai đoạn |
| Gần trùng | `datasketch` MinHash/LSH + SimHash 64 bit | Đề xuất cặp gần trùng và giữ cùng split; không tự xóa khác biệt kiến thức | Ban đầu; hybrid và các bản kế thừa |
| Kiểm định đầu ra | JSON parser, validator Python, kiểm tra LaTeX/HTML và bằng chứng bbox | Chặn field sai, enum lỗi, cạnh treo, LaTeX lặp/hỏng, bảng thiếu cấu trúc | Tăng dần từ v1 đến v4 |
| Hợp đồng v4 | Schema dạng JSON và validator Python dùng chung định nghĩa với prompt/example | Giảm lệch giữa hướng dẫn model và bộ kiểm tra | V4 |
| Đóng gói CPT | Hugging Face tokenizer, EOS, causal packing | JSONL text → token; giữ mảnh cuối, nhãn causal và ánh xạ token về nguồn | Ban đầu dùng Qwen2.5 Base; về sau dùng tokenizer Qwen3 |
| Suy luận GPU | PyTorch, Transformers, SDPA, FP16; bitsandbytes NF4 ở các đợt v2/v3 và cấu hình v4 | Nạp và chạy VLM; giảm chi phí weights, quản lý giới hạn input/output | Colab GPU |
| Lưu môi trường/kết quả | Python venv, `pip freeze`, tar.gz, Google Drive, ZIP/JSONL/manifest | Tách Paddle/Torch, phục hồi môi trường phù hợp Python, tiếp tục từ cache, giữ audit | Hybrid trở đi |
| Kiểm thử | unittest/pytest theo từng bộ, syntax/AST, ZIP CRC, hash và đối chiếu token | Kiểm tra hành vi, hồi quy và tính toàn vẹn; không thay benchmark nội dung | Mọi giai đoạn, đặc biệt v2–v4 |

Qwen3:1.7b là **model văn bản đích cho CPT** trong giai đoạn sau. Nó không thay thế Qwen2.5-VL trong tác vụ đọc ảnh. Tokenizer là công cụ đóng gói dữ liệu; sử dụng tokenizer không đồng nghĩa đã huấn luyện hoặc đã chạy inference model đó.

## 4. Chi tiết những gì đã thực hiện theo từng phiên bản

### 4.1. Tiền xử lý ban đầu: lấy dữ liệu có thể kiểm soát từ PDF

Đã trích xuất và chuẩn hóa đủ 1.060 trang. PP-DocLayout-M và mô-đun công thức chạy trên toàn bộ trang; PP-StructureV3 đầy đủ chạy bổ sung trên 86 trang. Paddle chạy CPU trên máy local; đã chuyển về PaddlePaddle 3.2.2 sau lỗi oneDNN/PIR gặp ở 3.3.1.

Các xử lý nội dung đã thực hiện:

- Phục hồi khoảng trắng tiếng Việt bằng khoảng cách ký tự thay vì yêu cầu LLM viết lại câu.
- Giữ chỉ số trên khi font/baseline của PDF xác nhận; ví dụ chuyển biểu diễn dính `1018` về `10^{18}` khi có bằng chứng.
- Ghép code bị chia block bằng tọa độ, giữ dòng và thụt lề; không dùng LaTeX OCR chồng vùng code để thay mã gốc.
- Lọc số trang/header/footer theo vị trí và tần suất; trang ít chữ vẫn giữ để kiểm tra hình.
- Giữ glyph chưa giải mã trong audit và gắn cờ; không xóa toàn bộ ký hiệu lạ.
- Kiểm tra bảng ký tự thực tế của OCR. Recognizer Latin tải ở đợt này thiếu một số chữ tiếng Việt có dấu, nên không mặc định dùng OCR thay native text.

Kết quả có 288 trang đủ điều kiện trước exact dedup; bỏ 24 bản text trùng trong tập đủ điều kiện, còn **264 mẫu CPT**. Có 753 trang cần review và 19 trang non-content đã xem nguồn rồi loại khỏi train. Lưu 1.038 record công thức và 18 record bảng, bao gồm ứng viên chưa xác minh; không cộng các record đó thành số mẫu train.

Đã đối chiếu ảnh 26 trang bởi Codex. Bộ QA hai trang 20 và 100 có CER/WER bằng 0 trên bản chuẩn chép từ ảnh trong phạm vi đó; không phải gold chuyên gia độc lập và không đại diện toàn bộ học phần.

Đóng gói ban đầu dùng tokenizer `Qwen/Qwen2.5-7B`, EOS 151643: **29.771 token, 15 sequence tối đa 2.048 token**. Validation/test để rỗng theo đơn vị tài liệu, không chia ngẫu nhiên hai bộ slide chồng lặp.

### 4.2. Hybrid: tách máy local và Colab

Trên Windows đã đọc/render lại 1.060 trang, chuẩn hóa, chạy ba phương pháp dedup và đóng gói preview. Trên máy i7-1165G7, RAM lắp 8 GB, báo cáo local ghi:

| Công việc | Số đo của lượt đó |
|---|---:|
| Đọc/render | Khoảng 90 giây, suy từ timestamp; không phải profiler từng hàm |
| Dedup | 1,22 giây |
| Tokenize/packing, gồm nạp tokenizer | 20,26 giây |
| Preview | 326 mẫu, 33.925 token, 34 sequence tối đa 1.024 token |
| Trùng text | 63 nhóm |
| Trùng cả text và ảnh toàn trang | 9 trang dư trên toàn tài liệu |
| Cặp ứng viên gần trùng | 737 |

Preview có `training_ready=false`; không thay bộ 264 mẫu đã làm sạch trước đó. Số mẫu preview lớn hơn không chứng minh dữ liệu tốt hơn.

Đã cấu hình Colab với hai môi trường Paddle/Torch riêng, OCR tiếng Việt, PP-DocLayout-M → PP-FormulaNet-S và Qwen2.5-VL-3B. Mười hai trang thử được chọn để bao gồm text, công thức, bảng, cây trạng thái, đồ thị và mã nguồn.

**Bằng chứng sau khi nhận kết quả:** `cloud_return.json` có 12 trang; nhánh Paddle báo `ok` ở 12/12, nhánh VLM là `invalid_json_or_schema` ở 12/12; tất cả chưa verified. Điều này bổ sung cho `TEST_REPORT.md` được viết trước khi kết quả Colab trở về. Không được tiếp tục mô tả hybrid là “chưa từng chạy Colab”, cũng không được gọi `Paddle ok` là nội dung đã đúng.

Lệnh merge chỉ nhập dự đoán vào hàng đợi review; không đưa tự động vào CPT. Ở giai đoạn này chưa có table structure model riêng, nên bảng đọc qua VLM vẫn cần đối chiếu hàng/cột.

### 4.3. Region v1 và scored routing: chuyển từ cả trang sang vùng kiến thức

Đã tái sử dụng native/layout cache chỉ khi khớp hash, phát hiện vùng cần xử lý, lọc decoration đã xác minh, crop/padding/resize và định tuyến:

```text
Text/code → PyMuPDF
Formula → PP-FormulaNet-S
Table → TableRecognitionPipelineV2
Diagram/graph/chart ứng viên → Qwen2.5-VL-3B
```

Ban đầu có bản dựng thử giới hạn nghiêm ngặt dưới 5% bằng ngân sách. Sau đó chuyển sang **Rule-based + PP-DocLayout-M** với điểm:

```text
S = 4D + 3C + 2U + R − 4B − 3E
```

Trong đó D là bằng chứng sơ đồ/đồ thị, C là biểu đồ thống kê, U là thông tin chưa trích đủ, R là rủi ro thiếu nội dung, B là decoration đã xác minh, E là extraction đã xử lý/đối chiếu đầy đủ. Luật hiện hành chọn S ≥ 7; chart có bằng chứng rõ có thể chọn từ S ≥ 6. Các vùng còn thiếu thông tin dưới ngưỡng được giữ review, không coi là đã sạch.

OpenCV và native vector được dùng để củng cố nhãn layout bằng node/box/link; nhãn `chart` của detector không tự biến graph DFS thành biểu đồ thống kê. Sáu đặc trưng gồm diagram/chart, native coverage, image area, duplicate và specialist success.

Đợt scored chọn **56/1.060 trang = 5,28%**, không cắt vì quota/top-k. Đây là tỷ lệ được lập lịch VLM, chưa chứng minh chỉ từng đó trang cần thị giác để phủ đủ kiến thức.

Kết quả GPU v1 đã nhận:

| Nhánh | Kết quả cấu trúc | Vấn đề chính |
|---|---:|---|
| Formula | 421/644 hợp lệ theo validator cũ | Có crop đoạn văn/bảng nhầm vào FormulaNet, LaTeX hỏng |
| Table | 0/16, cả 16 lỗi | `KeyError: 'doc_preprocessor_res'` trong tích hợp |
| VLM | 0/56 hợp lệ schema gốc | 55 output parse được nhưng enum chứa nhiều lựa chọn nối bằng pipe; một output JSON lỗi |

Batch VLM dùng FP16, SDPA, batch 2; ảnh khoảng 768 visual token và output tối đa 1.024 token. Cache theo pixel gốc trước resize tránh coi hai hình khác cạnh/màu/trọng số là cùng ảnh. Giai đoạn này cho thấy lỗi tích hợp và hợp đồng prompt có thể làm hỏng pipeline dù model đã sinh được nội dung.

### 4.4. Region v2: sửa lỗi nền trước khi so model

Đã sửa prompt enum, cho phép đúng một loại ảnh; tái kiểm định 55 output v1 parse được **không chạy lại inference**. Kết quả dẫn xuất có 46/56 record hợp lệ schema, chín lỗi cấu trúc và một JSON lỗi còn lại. Không tự nâng chúng thành verified.

Đã tái hiện đủ 16 lỗi bảng trên CPU với full traceback mới. Adapter tạo PaddleX `OCRResult` có `doc_preprocessor_res` và native cell text/bbox đúng hợp đồng. Rotation/dewarping được tắt để tọa độ không lệch; bbox chỉ clip khi ít nhất 95% diện tích nằm trong crop. Kiểm chứng một bảng trước, sau đó đủ **16/16 tạo HTML cấu trúc trên CPU**. Đây là thành công tích hợp, không phải 100% Table Accuracy.

Routing FormulaNet được sửa bằng luật text/code/toán và hình học bảng; tách vùng toán khỏi đoạn văn, giữ native text và ký hiệu. Số crop sau tách/exact dedup là 745. Validator mới bắt thêm LaTeX lặp/hỏng; áp vào output v1 chỉ còn 391/644 qua kiểm tra, không có nghĩa độ chính xác model tự giảm.

Đã nhận kết quả Colab v2:

- Formula: **704/745** hợp lệ cấu trúc, 41 invalid.
- Table: **16/16** hợp lệ, tái sử dụng kết quả CPU.
- Baseline 3B: năm crop pilot, **4/5** hợp lệ; trang 129 có cạnh tham chiếu node không tồn tại.
- 7B: năm crop pilot, **5/5** hợp lệ; 51 crop production chưa chạy.

Hai model được so trên cùng ảnh/prompt ở pilot với NF4, FP16 compute, SDPA, batch 1; không lấy số đo v1 FP16/batch khác làm đối chứng thuần model. Trên bốn graph có gold chẩn đoán, 7B tốt hơn về nhãn và trọng số nhưng vẫn thêm/lặp cạnh, gán hướng và highlight sai. Trang 129 có JSON hợp lệ nhưng chưa mô tả đúng board/branch.

### 4.5. Region v3: tách đồ thị thành các bước và thêm bằng chứng

Đã triển khai node → edge → attribute; yêu cầu bbox của node, cạnh, trọng số, mũi tên và so sánh style. Thêm native vector candidates, ứng viên board từ HSV/CV, kiểm tra LaTeX theo ngữ cảnh và đối chiếu token/số trong bảng.

Một canary FormulaNet chạy CPU trên crop đã sửa ở trang 33 bỏ được số mũ chấm sai của `O(n log n)`. Kết quả này được seed vào v3, không phải cải thiện mới sinh ra từ Colab sau đó.

Đã tạo bộ 60 trang chờ annotation: 42 development, 18 holdout. Các nhóm nguồn/near text/exact visual được giữ cùng split; 116 trang thuộc nhóm bảo vệ. Tách 40 mẫu kế thừa khỏi train, còn **224 mẫu, 25.691 token, 26 sequence tối đa 1.024 token**. Việc giảm số mẫu là chính sách chống rò rỉ, không phải kết luận 40 mẫu bị lỗi nội dung.

Kết quả GPU v3 đã nhận:

| Trang/crop | Trạng thái và phát hiện |
|---|---|
| 129, hai cây | Sai schema relation; đồng thời thiếu/sai trạng thái board và có dấu hiệu sao chép tọa độ ví dụ |
| 494 | Nodes/edges có output; attributes trả mảng thay object, quote null; có cạnh d–e lặp, b–e thiếu và không đọc trọng số |
| 812 | Schema hợp lệ nhưng thêm hai chú thích vào node; node precision 2/4 = 50% |
| 930, 1042 | CUDA OOM ở bước nodes trên T4 |

Tổng pilot: **1/6 crop hợp lệ**, không crop nào vượt gate bằng chứng v3; full run bị chặn và 51 crop còn lại chưa chạy. Formula/table trong ZIP khớp seed. Đây là hồi quy về khả năng hoàn thành so với pilot v2 7B; không thể gọi thiết kế ba bước là cải thiện đã chứng minh.

### 4.6. Region v4: sửa theo lỗi v3 và kiểm thử luồng

Đã triển khai và đóng gói các thay đổi:

- Schema dạng JSON, ví dụ không rỗng và validator dùng chung định nghĩa; kiểm tra ID, bbox hữu hạn, cell và field lạ.
- Repair có audit chỉ giới hạn định dạng: bỏ fence, unwrap một object, đổi quote null thành chuỗi rỗng. Không tự tạo kiến thức thiếu.
- 44 vùng có native node/edge candidates đủ điều kiện đi theo luồng hybrid; 11 vùng dùng fallback ngắn.
- Attributes chia tối đa bốn cạnh/task; bổ sung gate bbox/endpoint và trọng số native bị bỏ trống.
- Tách 20 board để đọc queen/removed cells độc lập, rồi nhận quan hệ cây trên ảnh tổng.
- Một đường resize PIL → processor, kiểm tra số token thực; text tối đa 2.048, toàn chuỗi tối đa 4.096; visual cap 384, retry 256. Crop nhỏ có mục tiêu khoảng 64 visual token.
- Cleanup tensor cả nhánh lỗi; telemetry allocated/reserved/free/peak, image grid và token; tối đa hai lần thử/task trong một lượt gọi.
- Lưu attempt không ghi đè, cache ràng buộc source/config/upstream; import tái ghép parent từ task evidence và đối chiếu seed.
- Giao diện HTML và JSONL cho 123 item specialist cần review: 120 công thức, ba bảng.

Kế hoạch có 330 task khai báo trên 57 vùng VLM; một số slot attributes fallback rỗng sẽ được bỏ qua không gọi model. Canary 930/1042 gồm 10 task; pilot đầy đủ 39 task. Tăng số task nhỏ không tự chứng minh tổng thời gian giảm.

Đã chạy **37 test v4 + 88 test hồi quy v1/v2/v3 = 125 test PASS**, cùng kiểm tra artifact, holdout, token và syntax. Luồng mô phỏng bằng model giả đã kiểm tra collect/import và adapter metric cũ. Số parent/task mô phỏng thành công **không phải độ chính xác Qwen** và không tạo dữ liệu train.

Đến thời điểm tổng hợp, chưa có ZIP kết quả GPU v4 để chấm. Chưa thể xác nhận hết OOM, tăng node/topology precision hoặc tăng tốc thực tế.

## 5. Khử trùng lặp và chống rò rỉ đã thực hiện như thế nào?

| Kỹ thuật | Cách thực hiện | Giới hạn/chính sách giữ dữ liệu |
|---|---|---|
| SHA-256 text | Hash chữ sau chuẩn hóa để tìm nhóm cùng nội dung | Hai slide cùng chữ có thể khác hình; hybrid không tự xóa chỉ vì trùng text |
| SHA-256 ảnh/pixel | Hash toàn trang hoặc crop trước resize; ràng buộc với loại xử lý | Exact duplicate mới dùng chung đại diện; thay màu, trọng số hoặc trạng thái phải được giữ |
| MinHash + LSH | 128 permutations, seed 42; shingle năm token ở hybrid, xác nhận Jaccard ≥ 0,8 | Chỉ tạo ứng viên/nhóm gần trùng, giữ số và dấu toán |
| SimHash | 64 bit, bốn band 16 bit; xác nhận Hamming ≤ 3 ở hybrid | Tạo ứng viên độc lập với MinHash; không thay thế đối chiếu ngữ nghĩa |
| Group split | Ban đầu toàn một tài liệu vào train; v3/v4 bảo vệ nhóm holdout theo đoạn nguồn + near text + exact visual | Không chia trang gần giống ngẫu nhiên; nhóm hiện tại chưa phải phân chương ngữ nghĩa hoàn hảo |

62 cặp gần trùng ở tập xử lý ban đầu và 737 cặp ở lượt hybrid khác phạm vi, cách tạo ứng viên và chính sách. Không suy ra số cặp lớn hơn nghĩa dữ liệu mới kém hơn. Ngược lại, nhiều ứng viên hơn cũng chưa chứng minh phát hiện đầy đủ mọi bản trùng.

Checkpoint CPT trước đây có thể đã học bộ 264 mẫu chứa các trang vừa được dành lại. Tách holdout ở v3/v4 không xóa sự tiếp xúc lịch sử đó; cần nguồn đánh giá chưa thấy hoặc đối chứng từ base để đo tổng quát hóa model.

## 6. Chuẩn đầu ra, đóng gói và môi trường

### 6.1. Các lớp dữ liệu

| Lớp | Nội dung | Cách dùng |
|---|---|---|
| Native/raw | Text, font, bbox, ảnh/vector, raw OCR/VLM, lỗi | Audit và truy vết; chưa phải tập train đã che PII |
| Normalized | Text chuẩn hóa, vùng, công thức/bảng ứng viên và trạng thái | Cơ sở dựng dataset/review |
| Review Queue | Thiếu kiến thức, schema lỗi, uncertain hoặc thiếu bằng chứng | Đối chiếu với ảnh/PDF, không tự chuyển verified |
| CPT text JSONL | Mỗi dòng `{"text":"..."}` | Trainer tokenize bằng đúng model đích |
| Metadata/source map | Tài liệu, trang, hash, reviewer/evidence, span nguồn | Kiểm tra nguồn, split và dòng train |
| Packed JSONL | `input_ids`, `attention_mask`, `labels` | Huấn luyện causal LM; không nạp đồng thời với bản text để tránh học hai lần |
| Manifest/cache/audit | Model revision, prompt/code/config hash, crop identity, runtime | Tái lập, tiếp tục inference và so sánh các phiên bản |

Packing thêm EOS thật sau mỗi mẫu, giữ mảnh cuối; `labels` theo causal LM để model dịch nhãn một lần. Padding của trainer cần bỏ vị trí pad khỏi loss. Không dùng chat template hoặc biến dữ liệu thành bộ hỏi–đáp sinh quiz trong bước CPT này.

Tokenizer Qwen2.5 Base ban đầu dùng EOS 151643 và pack 2.048 token. Khi chuyển đích sang Qwen3:1.7b, dữ liệu text được đóng gói lại bằng tokenizer Qwen3 từ HF export, EOS 151645, sequence tối đa 1.024 token. Không tái sử dụng token ID Qwen2.5 cho Qwen3 chỉ vì cả hai cùng họ Qwen.

### 6.2. Local và Colab

Local dùng Windows/Python, PyMuPDF và môi trường trong `data_preprocessing/.venv`; các phép sửa bảng/canary FormulaNet đã có chạy CPU thật. Colab chạy CUDA/T4 trong các đợt kết quả đã nhận; Paddle và Torch được tách venv/subprocess để tránh giữ đồng thời hai backend trên GPU.

Các đợt mới khóa PaddleOCR 3.7.0, PaddleX 3.7.2 và Paddle 3.2.2; Torch 2.6.0, Transformers 4.57.6 và bitsandbytes 0.48.1 ở đường NF4. Mỗi môi trường lưu `pip freeze`; archive venv theo Python tag giúp phục hồi khi phù hợp, không bảo đảm chạy được trên mọi runtime mới. Cache weights và cache inference là các lớp riêng, không đồng nghĩa đã được lưu trong archive venv.

Google Drive giữ kết quả bền vững theo manifest hash; ZIP dùng truyền dữ liệu và kiểm tra CRC. SHA-256 bảo vệ nhận dạng/tính toàn vẹn; bản thân hash không chứng minh kiến thức đúng.

## 7. Kết quả so sánh và ý nghĩa của các chỉ số

### 7.1. Tỷ lệ cấu trúc và độ phủ thực thi

| Chỉ tiêu | Region v1 gốc | V2 7B | V3 7B | V4 |
|---|---:|---:|---:|---|
| Formula hợp lệ cấu trúc | 421/644 | 704/745 | 704/745, gồm seed canary đã sửa | Kế thừa seed; chưa có inference specialist mới |
| Table hợp lệ cấu trúc | 0/16 | 16/16 | 16/16, reuse | Kế thừa seed |
| VLM hợp lệ schema | 0/56 gốc; 46/56 sau tái kiểm định dẫn xuất | 5/5 pilot | 1/6 pilot | Chưa đo trên model thật |
| VLM production chưa chạy | 0 | 51 crop | 51 crop | Chưa chạy GPU |
| Mẫu CPT mới từ predictions chưa xác minh | 0 | 0 | 0 | 0 |

Mẫu số, schema và vùng crop khác nhau. Bảng này mô tả trạng thái pipeline, không phải bảng xếp hạng độ chính xác nội dung. V3/v4 có 57 crop vì tách trang 129 thành hai cây, nhưng vẫn 56 trang VLM nguồn.

### 7.2. Đồ thị có gold chẩn đoán chung

V2 dùng bốn graph 494, 812, 930, 1042, gold đối chiếu bởi Codex và ràng buộc hash. Hướng, trọng số và highlight có phạm vi gold riêng, không áp nhãn cho các trang thiếu gold.

| Metric | V2 3B | V2 7B |
|---|---:|---:|
| Node label precision | 23/26 = 88,46% | 25/25 = 100% |
| Node label recall | 23/25 = 92% | 25/25 = 100% |
| Topology precision | 24/28 = 85,71% | 30/40 = 75% |
| Topology recall | 24/34 = 70,59% | 30/34 = 88,24% |
| Trọng số đúng / gold | 7/11 = 63,64% | 11/11 = 100% |
| Hướng đúng / gold | 8/11 = 72,73% | 8/11 = 72,73% |
| Highlight đúng / gold | 0/11 | 0/11 |

V3 chỉ hoàn tất trang 812, nên không dùng topology 1/1 của trang đó để tuyên bố tốt hơn tổng bốn trang v2. V4 chưa có output thật. Bộ bốn trang đã dùng phát triển luật không thay thế holdout độc lập.

### 7.3. Thời gian và VRAM đã đo ở pilot

| Khoản | V2 7B, năm crop | V3 7B, sáu crop |
|---|---:|---:|
| Khởi tạo model | 292,83 giây | 391,06 giây |
| Inference + overhead sau khi trừ khởi tạo | 283,91 giây | 532,67 giây |
| Tổng init + request được ghi log | 576,74 giây | 923,73 giây |
| Peak allocated ghi ở tác vụ thành công | Khoảng 6,04 GiB | Khoảng 11,62 GiB |
| OOM | Không ghi nhận ở pilot này | Hai crop |

Khởi tạo lười của v3 đã nằm trong thời gian request đầu; không cộng hai lần. Hai tập task khác nhau, nên chênh lệch không phải slowdown thuần do model. Peak ghi ở stage thành công không đại diện peak OOM. Không có thời gian GPU v4 để đối chiếu và không ngoại suy tuyến tính sang 1.060 trang như thể mọi trang đều chạy VLM.

## 8. Những phần đã đạt và những phần còn thiếu

**Đã thực thi và có bằng chứng:** trích xuất/native/layout đủ trang; chuẩn hóa bảo toàn ký hiệu/code; ba lớp dedup; cache/hash/source map; đóng CPT; Colab hybrid/v1/v2/v3; sửa tích hợp bảng thật trên CPU; so 3B–7B trên subset; chặn dữ liệu chưa xác minh; đóng gói v4 và kiểm thử tích hợp.

**Chưa hoàn tất:** chuyển toàn bộ kiến thức của 1.060 trang thành CPT đã xác minh; gán nhãn đầy đủ benchmark 60 trang; đo CER/WER, Formula/Table Accuracy, Diagram Fact Precision và Information Coverage toàn học phần; đo routing recall trên các trang bị bỏ qua; nhận/chấm kết quả GPU v4; đo verified tokens/hour.

Không gộp schema pass, test pass và model accuracy thành điểm tổng /100 tùy ý. Những ước lượng xác suất hoặc phần trăm cải thiện v4 trước đó là dự đoán kỹ thuật, không phải kết quả thực nghiệm.

## 9. Tài liệu và bằng chứng để truy vết

| Nhóm | Bằng chứng chính |
|---|---|
| Tiền xử lý ban đầu | [Báo cáo dataset](data_preprocessing/outputs/it3170/REPORT.md), [quality report](data_preprocessing/outputs/it3170/quality_report.json), [QA hai trang](data_preprocessing/outputs/it3170/qa/reference_metrics.json) |
| Hybrid local và Colab | [Báo cáo local ban đầu](hybrid_preprocessing/TEST_REPORT.md), [kết quả Colab đã nhập](hybrid_preprocessing/runs/it3170_test/cloud_return.json), [dedup](hybrid_preprocessing/runs/it3170_test/deduplication.json) |
| Định tuyến theo điểm | [SCORE_RULES.md](region_preprocessing/SCORE_RULES.md) |
| Region v1 | [Báo cáo kết quả](region_preprocessing/evaluation_33f6b7b75d29/REPORT.md), [metrics](region_preprocessing/evaluation_33f6b7b75d29/metrics.json) |
| Sửa lỗi v2 | [Báo cáo triển khai](region_preprocessing_v2/REPORT.md), [tái kiểm định không inference](region_preprocessing_v2/revalidation/metrics.json) |
| Kết quả v2 3B/7B | [Báo cáo đánh giá](region_preprocessing_v2/evaluation_d682e3b25b0d/REPORT.md), [metrics](region_preprocessing_v2/evaluation_d682e3b25b0d/metrics.json) |
| Triển khai v3 | [Báo cáo](region_preprocessing_v3/REPORT.md) |
| Kết quả GPU v3 | [Báo cáo đánh giá](region_preprocessing_v3/evaluation_aa4973c0f29f/REPORT.md), [metrics](region_preprocessing_v3/evaluation_aa4973c0f29f/metrics.json) |
| V4 | [Báo cáo triển khai](region_preprocessing_v4/REPORT.md), [audit phát hành](region_preprocessing_v4/evidence/final_validation/metrics.json), [build metrics](region_preprocessing_v4/runs/it3170_v4_20261019_final/build_metrics.json) |
| Gói text chuyển sang CPT Qwen3 | [Manifest dữ liệu](colab_qwen3_1_7b/data/manifest.json) |

Các báo cáo triển khai ghi trạng thái tại lúc viết; báo cáo kết quả và artifact trả về sau đó là bằng chứng cập nhật về việc inference đã chạy đến đâu. Báo cáo tổng hợp này ưu tiên dữ liệu kết quả đã nhận, giữ riêng những số liệu chưa đo và không sửa lịch sử các bản trước.
