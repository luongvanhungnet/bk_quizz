# Báo cáo triển khai data preprocessing v5 — IT3170

Ngày: **20/10/2026**, Asia/Bangkok. Run dùng để tiếp tục: **`runs/it3170_v5_20261020`**.

> Cập nhật 21/10/2026: đã nhận và phân tích ZIP Colab v5 thật. Xem [báo cáo kết quả và so sánh v1–v5](evaluations/colab_24f2f2d02890_20261021/REPORT.md). Nội dung dưới đây là snapshot lúc triển khai, trước lượt Colab này; các câu “chưa chạy GPU” chỉ áp dụng thời điểm đó.

V5 đã được triển khai và chuẩn bị dữ liệu local theo luồng **Native + OCR + VLM + Cross-validation + Human Review**. App kiểm duyệt đã được thử trên trình duyệt thật. Đã chạy canary OCR và FormulaNet thật trên CPU. **Chưa chạy Qwen v5, Docling hoặc MinerU model thật trên GPU/Colab trong đợt này**, nên chưa có điểm chính xác hay tỷ lệ cải thiện v5 so với v4.

## 1. Thay đổi trọng tâm so với v4

Người dùng báo v4 gần như lỗi toàn bộ, nghi do đầu ra quá phức tạp và ảnh thiếu dữ kiện. Đây là thông tin người dùng cung cấp; đợt triển khai này không có ZIP v4 mới để định lượng lại nguyên nhân. Các thay đổi dưới đây xử lý trực tiếp hai giả thuyết đó, nhưng chưa chứng minh được mức cải thiện thực nghiệm.

| Hạng mục | V3/v4 | V5 |
|---|---|---|
| Giao việc cho VLM | Inventory/node/cạnh/thuộc tính hoặc bàn cờ, liên kết giữa nhiều task | Một ảnh → một lượt mô tả tự nhiên |
| Định dạng model phải sinh | JSON/schema, trường và liên kết bắt buộc | Không yêu cầu JSON, tọa độ hay inventory đầy đủ |
| Ảnh thiếu dữ kiện | Có thể không đạt schema/quality gate | Cho phép mô tả phần nhìn rõ và nói phần không đọc được |
| Sửa schema | Không được tự coi là xác minh ngữ nghĩa | Bỏ nhu cầu sửa JSON VLM; code đóng gói text thành record nội bộ |
| Đối chiếu | Nhiều heuristic và chuyên gia theo vùng | Cùng vùng ảnh, xét vai trò nguồn và lineage; không bỏ phiếu đa số |
| Kiểm duyệt | Các công cụ annotation/review riêng | App Python thống nhất ba nhóm + SQLite lịch sử |
| Xuất dữ liệu mới | Không tự thêm facts chưa xác minh | Chỉ quyết định người thật approve/correct còn hiệu lực, thuộc train |

V5 đánh đổi khả năng lấy inventory đầy đủ bằng nhiệm vụ dễ hơn cho VLM. Một mô tả đúng nhưng ngắn có thể có groundedness cao và coverage thấp. Hai chỉ số này phải được chấm riêng; không dùng “có text trả về” làm độ chính xác.

## 2. Công việc và công nghệ

| Bước | Công nghệ/mã | Đã thực thi trong lần này |
|---|---|---|
| Phân loại PDF | PyMuPDF, `prepare.py` | Kiểm tra text layer, native/mixed/visual-only trên 1.060 trang |
| Lưu slide nguồn | PyMuPDF + cache render có hash | Giữ đủ 1.060 PNG toàn trang; kiểm tra hash, không render lại cache đúng |
| Ưu tiên PPTX gốc | python-pptx trong `adapters.py` | Có adapter text/shape/table/chart và test PPTX thật sinh trong fixture; không có PPTX IT3170 tương ứng để chạy |
| Inventory vùng ban đầu | PP-DocLayout/rule-based từ cache trước | Giữ vùng có tọa độ, crop công thức đã sửa, source/seed hash; không chạy lại detector để làm mới số liệu |
| Ngữ cảnh | Pillow, bbox chuẩn hóa [0,1000] | Giữ exact crop, mở rộng ngữ cảnh xung quanh và full slide; đưa native context ngắn vào prompt |
| OCR tiếng Việt | PaddleOCR 3.7.0, PaddleX 3.7.2, PP-OCRv3 `lang=vi` | CPU canary trang 869 chạy thành công; giữ 13 dòng OCR và bất đồng với native |
| Công thức | PP-FormulaNet-S | CPU canary trên crop đã sửa trang 33; tái dùng seed cũ đúng hash |
| Bảng | PP-StructureV3, `paddle_worker.py` | Tích hợp worker để PP-StructureV3 sở hữu OCR tiền xử lý; 16 seed bảng cũ được giữ, không tuyên bố đã chạy 16 lượt mới |
| Layout/reading order bổ sung | Docling 2.140.0, `parser_worker.py` | Adapter + worker + notebook, kiểm thử cấu trúc; chưa suy luận model thật local |
| Parser độc lập | MinerU 4.0.12, legacy content_list/DocVortex schema 2.0 | Adapter, CLI probe và notebook tùy chọn; chưa suy luận model thật local |
| Hiểu sơ đồ | Qwen2.5-VL-7B-Instruct NF4 mặc định, tùy chọn 3B | Worker một lượt, prompt text, cache, telemetry; kiểm tra luồng bằng model giả |
| So sánh đầu ra | Python, `cross_validation.py` | Native/OCR cùng vùng, role/lineage, bất đồng số/ký hiệu, LaTeX hỏng, rủi ro nội dung |
| Ảnh mờ/trùng | Pillow, OpenCV, ImageHash | Gắn cờ ảnh nhỏ/ít nét và 97 nhóm perceptual hash ứng viên; không tự xóa |
| Schema | Pydantic | Kiểm tra record nội bộ, hash, bbox, loại vùng; không yêu cầu VLM sinh schema |
| Human review | Python HTTP server + HTML/JS + SQLite | App thực tế, bộ lọc, ảnh nguồn, candidates, editor, bốn quyết định và lịch sử |
| Label Studio | Export/import JSON + XML config | Có adapter tùy chọn, test annotation nguồn/human; không cài hay vận hành server Label Studio |
| Chuẩn hóa/xuất | Python, Unicode NFC, SHA-256, tokenizer local tùy chọn | Giữ số/dấu toán học, che email, tách holdout, xuất có metadata và kiểm hash |

Docling đọc native PDF cùng nguồn không được đếm là một lần OCR độc lập. Các nhánh Paddle/PP-Structure và parser dùng Paddle cùng backend không được tính như những phiếu độc lập. Native và OCR khác nhau thì giữ cả hai; không dùng VLM viết lại toàn bộ bài giảng.

## 3. Dữ liệu local thực tế

PDF: `D:\bk_quizz_data\slide_processed\pdf\IT3170-Thuật toán ứng dụng.pdf`.

SHA-256 PDF: `c6c829f14bf2a8a1e42b6919d729fdf23865ef4734eb25817f183103dd877087`.

| Phân loại trang | Số lượng |
|---|---:|
| Có native text | 985 |
| Mixed theo rule text ngắn + ảnh | 55 |
| Scanned hoặc visual-only theo rule ít text | 20 |
| Tổng render | **1.060** |

Đây là phân loại sự hiện diện của text, không chứng minh chữ đã đúng hoặc trang ít chữ không có kiến thức.

| Inventory để đối chiếu/duyệt | Số record |
|---|---:|
| Văn bản toàn trang | 978 |
| Trang code theo heuristic | 82 |
| Công thức | 745 |
| Bảng | 16 |
| Vùng hình/sơ đồ | 424 |
| Tổng | **2.245** |

1.060 record text/code là lớp đối chiếu toàn trang; các vùng formula/table/diagram có thể nằm trong cùng slide. **2.245 record không phải 2.245 trang và không phải lượng kiến thức độc lập không trùng.**

| Nhóm máy hiện tại | Số lượng |
|---|---:|
| Tin cậy | **0** |
| Chưa chắc chắn | **2.204** |
| Lỗi nghiêm trọng | **41** |
| Được người thật duyệt | **0** |
| Đủ điều kiện xuất CPT v5 mới | **0** |

41 mục critical gắn với lỗi cấu trúc công thức được bảo toàn từ cache. Không tự quy mọi cảnh báo thành sai kiến thức. Có 1.749 record bị xếp rủi ro cao theo loại hoặc dấu hiệu nội dung; con số này khác với nhóm critical.

Zero trusted là trạng thái ban đầu có chủ đích: chưa có xác nhận OCR độc lập đầy đủ. Sau khi nhập canary OCR trang 869, native và OCR vẫn khác nhau nên không tự nâng nhóm. Các mục có VLM mô tả đúng một phần vẫn cần người xem ảnh.

## 4. VLM và ngân sách

Prompt thực thi ở `vlm_worker.py`, biến `PROMPT`. Nội dung yêu cầu mô tả ngắn phần học thuật nhìn rõ, cho phép bỏ phần mờ, không giải bài tập và không tự bổ sung facts. Không có schema inventory hoặc chuỗi tự kiểm chứng.

Worker dùng Qwen2.5-VL-7B-Instruct ở revision khóa, NF4, SDPA, batch một ảnh, tối đa 512 visual token và 512 output token. Có resize theo grid 28, giới hạn prompt, theo dõi input/output token, VRAM và cleanup. Chỉ một lần gọi `generate` cho một ảnh trong một attempt; không retry schema hoặc đổi nhiều bước tự động. Khởi tạo model lỗi sẽ không tải lại cho từng ảnh. Lỗi một ảnh sau khi khởi tạo không ngăn các ảnh còn lại.

Cache thành công gắn với ảnh/context/crop/target bbox, nguồn, prompt, model và runtime. Thay đổi ngữ cảnh không được tái dùng đầu ra cũ như thể nó nhìn ảnh mới. Lỗi/attempt/raw được giữ riêng. `--retry-errors` là lựa chọn tường minh.

**424 vùng hình là inventory kiểm duyệt, không phải mặc định 424 lời gọi VLM.** Gói all giữ lịch 56 vùng trên 56/1.060 trang (**5,28%**); các mục dưới ngưỡng, trùng chính xác và nguồn đã xem vẫn ở hàng đợi review. `--all-visuals` mới mở rộng sang toàn bộ hình. Như vậy phạm vi review tăng mà mặc định vẫn giữ mục tiêu 4–8% trang cần VLM.

Gói chính là `cloud_packets/it3170_v5_pilot_11pages/v5_colab_input.zip`: 11 trang, có text/OCR, 5 vùng công thức, 1 bảng và 6 ảnh VLM. Các trang 129, 494, 812, 930, 1042 đều có trong pilot. Seed specialist hợp lệ được bỏ qua để không chạy lại vô ích. Gói 8 trang dựng trước đó được giữ để audit, không phải gói hướng dẫn chính.

## 5. Cross-validation và người duyệt

Văn bản chỉ vào nhóm máy trusted khi native và OCR khác lineage, cùng nguồn/vùng, khớp sau NFC/khoảng trắng, không bất đồng hoặc lỗi và không thuộc nội dung rủi ro cao. Thiếu bằng chứng vùng thì giữ uncertain. Tọa độ không biết không được đoán rồi tính là khớp.

Công thức ưu tiên math recognizer làm đề xuất, bảng ưu tiên table recognizer, hình ưu tiên mô tả VLM. Đây là lựa chọn trình bày cho người xem, không phải phê duyệt. LaTeX kiểm tra ký tự lỗi, dấu ngoặc, command lặp và toàn biểu thức lặp; không xóa chỉ số, số mũ, dấu hoặc đổi ký hiệu để làm khớp.

App hiển thị full slide, exact crop, crop ngữ cảnh, native và các engine. Người thật chọn approve/correct/reject/defer, nhập tên/bằng chứng; nội dung rủi ro cao cần xác nhận đã đối chiếu. Lịch sử SQLite append-only liên kết source/crop/context/proposal/machine revision. Kết quả máy thay đổi làm phê duyệt cũ stale. Import Label Studio bỏ qua predictions và đòi annotation người thật có provenance.

Xuất CPT chỉ nhận approve/correct hiện hành, split train, hash ảnh không đổi và đúng manifest PDF. Perceptual hash không tự loại những hình gần giống có trọng số/hướng khác. Exact dedup chỉ loại khi cả text và pixel cùng khớp. Tách nhóm holdout từ v3 tiếp tục được giữ; v5 không nhập lại bộ CPT cũ 224 mẫu như thể đã được duyệt theo chính sách mới. Các bộ cũ còn nguyên tại thư mục phiên bản cũ.

## 6. Canary và kiểm thử

Canary thật được lưu trong `evidence/paddle_formula_canary` và `evidence/paddle_ocr_canary`:

| Canary | Kết quả | Thời gian record |
|---|---|---:|
| FormulaNet, crop sửa biên trang 33 | `\mathcal{O}(n\log n)` | Khoảng 1,41 giây |
| OCR tiếng Việt, slide 869 | 13 dòng OCR; có khác dấu so với native | Khoảng 11,97 giây |

Hai thời gian trên **không gồm khởi tạo model**, không đại diện throughput toàn tài liệu. OCR có dòng `Quy hoach döng` trong khi native là `Quy hoạch động`; raw được giữ. Canary vẫn chưa được người dùng cấp trạng thái semantic verified. Thành công API không được báo thành 100% accuracy.

Kiểm tra release:

- **139 test PASS**, kiểm tra core, adapter, app/API/Label Studio, notebook và workflow. Log: `evidence/tests_release.txt`.
- 2.245 record đạt schema, đủ 1.060 render; 6.735 kiểm tra hash ảnh ở bước release.
- ZIP CRC, code/image hash, source PDF và page mapping của gói pilot được kiểm tra.
- Test chặn context cũ gắn với VLM mới, crop Paddle sai, manifest PDF đổi sau khi duyệt, phê duyệt stale, holdout đi vào train và schema repair tự thành verified.
- Test một ảnh lỗi vẫn xử lý ảnh sau; một ảnh chỉ một lời gọi; cache thành công không gọi lại model. Đây là test model giả, không phải điểm Qwen.
- Browser Edge thật: ba bộ lọc, chuyển mẫu, full slide/crop/context, candidates và editor hoạt động; không lưu quyết định giả trên run thật. Bằng chứng: `evidence/ui_smoke.json`.
- Export trước human review trả **0 mẫu, `training_ready=false`**. Bằng chứng: `evidence/empty_cpt_check/manifest.json`.

Notebook có khôi phục archive venv theo Python tag, kiểm tra phiên bản/import, dựng env bằng uv khi cần, lưu freeze/logs và output bền vững trên Drive. Paddle, parser và Qwen chạy process riêng; output lỗi vẫn đóng ZIP được. Notebook được kiểm tra cú pháp, **chưa được chạy end-to-end trên Colab trong đợt này**.

## 7. Đo chất lượng và giới hạn còn lại

`METRICS.md`, `metrics.py`, `evaluate_run.py` triển khai Label Accuracy, CER/WER, Layout IoU, image-label alignment, exact LaTeX, coverage và Q theo trọng số người dùng. Thiếu gold hoặc một chiều thì trả null. Không dùng số test code đạt, schema pass hay tỷ lệ trả text làm Q.

Chưa có bộ gold người dùng hoàn tất cho v5, nên **chưa báo cáo CER/WER/Accuracy/Coverage/Q hoặc phần trăm cải thiện**. Cần chạy cùng pilot, người duyệt gán reference và chấm đúng proposal hiện tại trước khi so sánh với các bản cũ.

Context crop hiện mở rộng theo khoảng cách pixel; ở một số công thức vẫn có thể là fragment. Full slide luôn sẵn trong app. Generic PDF mới hiện có native và raster inventory; vùng parser mới không khớp inventory được giữ trong import receipt `unmatched`, cần định tuyến bổ sung, chưa tự thành CPT. Chưa có đánh giá toàn diện cho chart/ảnh minh họa hoặc tài liệu PPTX thực tế.

## 8. Tài liệu kỹ thuật tham chiếu

- Docling layout/reading order và CLI: [tài liệu chính thức](https://docling-project.github.io/docling/reference/cli/).
- MinerU output/provenance: [repository chính thức](https://github.com/opendatalab/MinerU/blob/master/docs/en/reference/output_files.md).
- Model VLM: [Qwen2.5-VL-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct).
- Label Studio task/import và local storage: [tasks](https://labelstud.io/guide/tasks.html), [local storage](https://labelstud.io/guide/storage_local).

Hướng dẫn chạy và lệnh merge/review/export nằm trong `README.md`.
