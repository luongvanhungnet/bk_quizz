# Báo cáo sửa pipeline IT3170 preprocessing v2

Ngày: **19/10/2026**. Nguồn điều tra: [báo cáo đợt trước](../region_preprocessing/evaluation_33f6b7b75d29/REPORT.md), ZIP `region_results_33f6b7b75d29.zip`, manifest scored_v3. Mọi output, manifest, hash và audit cũ được giữ nguyên.

**Đã xử lý hai P0 và triển khai bản mới Qwen2.5-VL-7B.** Đo thực tế tại máy: sửa schema dẫn xuất cho 46 output cũ không gọi inference; tái hiện và sửa đủ 16 lỗi bảng bằng model thật trên CPU. Đã sửa routing/crop FormulaNet, thêm kiểm định và regression cho các trang khó. **Chưa chạy inference 7B hoặc baseline 3B với prompt mới trên Colab; chưa có kết luận 7B tốt hơn 3B.** Máy hiện tại không có NVIDIA runtime để thực hiện phép so sánh GPU này.

## 1. Kết quả trước/sau đã đo

| Hạng mục | Trước | Sau sửa / số đo hiện có | Giới hạn |
|---|---|---|---|
| VLM cũ qua schema | 0/56 | **46/56** bản dẫn xuất qua schema; 9 lỗi cấu trúc, 1 JSON lỗi giữ lại | Không chạy inference lại; không đo chất lượng model mới |
| 55 output VLM parse được | Enum nhiều lựa chọn, không hợp lệ | 46 qua schema, 9 vẫn lỗi; chuỗi mơ hồ đổi thành `unknown` có log | Không tự chọn graph/diagram hoặc sửa cạnh |
| Table integration | 16/16 `KeyError` trên Colab | **16/16 tạo HTML có cấu trúc trên CPU** | Không phải 100% Table Accuracy |
| Reproduction lỗi bảng có full traceback | ZIP cũ không lưu | Đã tái hiện cả **16/16** lỗi `doc_preprocessor_res`, giữ traceback mới | Không gọi traceback CPU là traceback lịch sử Colab |
| Bbox native bảng vượt crop | Chưa có guard | 14 bảng qua lần đầu; sửa 2 bbox vượt nhẹ rồi đủ 16 | Chỉ clip khi ≥95% diện tích bbox nằm trong ảnh |
| Output formula cũ qua validator | 421/644 | **391/644** qua validator mới | Chuyển thêm 30 ứng viên có dấu hiệu nhiễu sang review; không phải Accuracy giảm |
| Routing 644 formula parent | Gửi nguyên crop | **576 parent có crop toán; 10 chồng bảng chuyển nhánh; 49 visual review; 9 native review** | Review không có nghĩa là xóa nội dung hoặc đã trích đủ |
| Request công thức sau split/exact dedup | 644 | **745 crop**, 10 được reuse, 735 có thể cần inference mới | Số crop tăng vì tách nhiều biểu thức; không phải tăng số slide hoặc độ phủ đã xác minh |
| Request VLM production | 56 trang | **56/1.060 = 5,28%** | Giữ mục tiêu 4–8%, không ép quota |
| Cache reuse trong gói mới | Không có seed sửa lỗi | **16 table CPU + 10 formula cũ = 26** record có lineage/hash | Không đưa raw VLM 3B vào cache 7B |
| CPT | 264 mẫu, 29.771 token | **Giữ nguyên** | 0 mẫu prediction mới tự vào train |
| Kiểm thử | 25 test cũ | **26 test v2 + 25 regression cũ đều PASS** | Không thay cho benchmark ngữ nghĩa hoặc GPU |

CER/WER native không được dùng làm minh chứng cải thiện: không sửa lớp native hay nguồn QA hai trang cũ. Chưa có Formula Accuracy, Table Accuracy hoặc Information Coverage toàn học phần mới; không gán một điểm /100 tùy ý.

## 2. P0 — Prompt, validator và tái kiểm định

[prompt.txt](prompt.txt) liệt kê năm giá trị `graph`, `diagram`, `chart`, `illustration`, `unknown` bằng dòng riêng và đưa đúng một ví dụ JSON hợp lệ với `image_type="graph"`. Không dùng enum nối `|` làm ví dụ. Validator chấp nhận đủ năm giá trị; bool không được chấp nhận làm trọng số số học.

Tách rõ ba tầng:

1. JSON/schema: trường, kiểu dữ liệu, node ID duy nhất, tham chiếu cạnh hợp lệ.
2. Cảnh báo chất lượng: graph rỗng, label lặp, hướng toàn null, hình chưa phân loại.
3. Duyệt nội dung bằng nguồn: duy nhất tầng này có thể làm căn cứ cho một transcript CPT sau này; phiên bản hiện tại không tự phê duyệt.

Ví dụ JSON với arrays rỗng hợp schema, nhưng graph rỗng vẫn bị cảnh báo thiếu nội dung. Điều này giải quyết mâu thuẫn giữa ví dụ hợp lệ và kiểm định tính đầy đủ.

[revalidate.py](revalidate.py) đọc lại raw text của 56 output cũ, trong đó 55 parse được; không gọi model. Chuỗi `diagram|graph` không cung cấp bằng chứng để chọn một loại, nên bản dẫn xuất ghi `unknown` và lưu thay đổi cũ/mới, nguồn, cache key, lý do. Không sửa label/cạnh/weight, không tự thêm observed facts và không ghi đè record gốc. 46 bản dẫn xuất hợp schema vẫn **semantic_verified=false**, **destination=review_queue**. 9 record lỗi tham chiếu/kiểu và 1 JSON cắt dở vẫn lỗi.

Bằng chứng: [metrics](revalidation/metrics.json), [bản ghi tái kiểm định](revalidation/vlm_schema_review.jsonl).

## 3. P0 — Table recognition

### Nguyên nhân đã tái hiện

Trong PaddleX 3.7.2, `table_recognition_post_processing_v2.get_table_recognition_res` đọc:

```python
overall_ocr_res["doc_preprocessor_res"]["output_img"].shape[0:2]
```

Worker cũ tự dựng `overall_ocr_res` chỉ có cell text, rec_boxes/polys/scores và path. Payload thiếu `doc_preprocessor_res`, nên hậu xử lý lỗi trước khi trả bảng. Không cần bật OCR tiếng Việt hoặc document unwarping để sửa lỗi contract này.

### Cách sửa

[table_adapter.py](table_adapter.py) dựng `OCRResult` tương thích, có ảnh BGR của đúng crop, `model_settings`, các trường OCR serialization và native text/geometry. Điểm 1 chỉ là placeholder API cho native geometry, không được gọi là OCR confidence. Giữ orientation/dewarping/layout/OCR tắt khi truyền tọa độ native để tránh thay đổi hệ tọa độ.

Bổ sung kiểm tra bbox hữu hạn, không suy biến. Hai bảng trang 752 và 799 có native bbox vượt trái khoảng 3,11% và 2,62% diện tích; clip về ảnh với ngưỡng ≥95%, giữ nguyên chữ. Bbox vượt nhiều hơn vào review, không tự kéo tọa độ tùy ý.

### Kiểm thử thực tế

- Môi trường local: PaddleOCR **3.7.0**, PaddleX **3.7.2**, PaddlePaddle CPU **3.2.2**; cùng phiên bản package với Colab, khác backend CPU/GPU. Ghi cả hash file package vì version string chưa đủ mô tả source thực tế.
- Canary bảng trang 12 tạo HTML thành công trước khi chạy batch sửa lỗi.
- Lần đầu: 14/16 thành công, hai bảng bị guard bbox chặn. Sau sửa bbox: hai bảng còn lại thành công. Không ghi đè kết quả thất bại ban đầu.
- Đã tái hiện đủ 16 lỗi thiếu `doc_preprocessor_res` với full traceback mới trên CPU. ZIP lịch sử không có full trace nên không thể khôi phục trace cũ.
- Worker mới chặn batch specialist khi chưa có canary thành công gắn với đúng manifest và hash record. Lỗi mọi request và lỗi khởi tạo stage đều lưu traceback đầy đủ.
- HTML có hàng/cell chỉ chứng minh tích hợp chạy được. Cần đối chiếu hàng/cột, cell text và span trước khi CPT; không gán `verified=true` cho 16 bảng.

Bằng chứng: [tổng hợp cuối](evidence/table_final_summary.json), [canary](evidence/table_canary_cpu.json), [compatibility/package hashes](evidence/paddle_compatibility.json), [traceback ban đầu](evidence/old_table_traceback.txt), [16 lần regression đầu](evidence/table_cpu_regression), [hai lần retry bbox](evidence/table_bbox_retry).

Một log chẩn đoán đầu có lỗi in Unicode của console Windows sau khi HTML đã lưu thành công; không tính lỗi in này là thất bại của table model. Kết quả cuối dựa trên record JSON và regression, không dựa riêng vào exit code của lần in thử đó.

## 4. P1 — Phân loại và crop công thức

[formula_routing.py](formula_routing.py) ưu tiên vùng bảng đã biết và cấu trúc hàng/cột native; tránh gửi code hoặc văn bản không có biểu thức riêng biệt vào FormulaNet. Với đoạn văn kèm toán, tách theo span math-font/superscript và các ký hiệu/số kề nhau, giữ nguyên câu native làm ngữ cảnh. Các vùng không có bằng chứng công thức tách được giữ review; không âm thầm loại các slide ít chữ.

Ví dụ đã đối chiếu ảnh crop:

- Trang 11: từ cả câu tiếng Việt thành phần `(a,b ≤ 10^18)` và `(T ≤ 10)` riêng.
- Trang 33: lấy phần `5 × 10^8` và các giới hạn/độ phức tạp, giữ câu giải thích ở native.
- Trang 60: hai formula parent chồng bảng chuyển về table hiện có, không gửi lại bảng vào FormulaNet.
- Trang 73: lấy dãy `0,1,…,n−1` và các biểu thức tập hợp; không dùng FormulaNet chép lại câu “Gán nhãn bởi các số nguyên…”.
- Trang 85: tách `O(n)` khỏi câu giải thích; biểu thức phụ thuộc ngữ cảnh vẫn cần duyệt cùng native.

Giữ dấu toán, số, ngoặc, chỉ số và số mũ; không chuẩn hóa chúng thành văn xuôi. Công thức đúng từ native cũng chưa được tự coi là công thức OCR verified. Vì tách một vùng lớn thành nhiều biểu thức và gộp exact duplicate, số request 745 không so trực tiếp với 644 như accuracy/coverage.

Validator mới bắt thêm chuỗi token lặp, đoạn lặp dài, ký tự thay thế/control, output quá dài và môi trường LaTeX không cân bằng. Có thể chặn nhầm một biểu thức dài hợp lệ, nên dùng như cổng review, không xóa nội dung nguồn. **Chưa có benchmark FormulaNet inference trên crop mới; 391/644 là kiểm định lại output cũ, không phải kết quả model trên 745 crop mới.**

## 5. P1 — Kiểm định ngữ nghĩa và so 3B/7B

[gold_cases.json](gold_cases.json) gắn hash PDF/trang/crop, do Codex đối chiếu ảnh; không phải bộ gold chuyên gia độc lập. [semantic_eval.py](semantic_eval.py) đếm label theo multiset để label lặp không được thưởng, so topology, trọng số, hướng và highlight khi có nhãn tham chiếu. Không suy diễn hướng từ việc thiếu mũi tên; trường tham chiếu chưa chắc được để null và không tính vào mẫu số metric đó.

Đo lại raw output 3B cũ trên cùng ảnh nguồn:

| Trang khó | Số đo / vấn đề 3B cũ | Tiêu chí dùng cho pilot mới |
|---|---|---|
| 129 | Cây bàn cờ bị chuyển thành node chú thích | Rubric manual: trạng thái bàn cờ và nhánh; không chấm bằng một cây suy đoán |
| 494 | Đúng 7/7 label; 9/11 cặp cạnh; 8/11 trọng số nguồn; highlight chưa xác định 0/11 | Đủ b–d=9, c–e=5; d–e=15; giữ màu/đánh dấu nếu có |
| 812 | 2 label đúng trong 3 label dự đoán; 0/1 cạnh nguồn | Chỉ đỉnh 0 và 1; K=2 và y[1]/y[2] là chú thích |
| 930 | 7/11 cặp cạnh; **0/11 hướng cung được khôi phục** | Đủ 11 cung, đúng source→target |
| 1042 | 7/9 label nguồn; hai label lặp; 4/11 cặp cạnh | Giữ đủ nhãn 1–9, không thay nhãn bằng node ID |

Topology ở bảng là cặp đầu mút; hướng đo riêng. Trọng số đúng tính trên cạnh đúng, không chỉ so tập số. Null là chưa xác định, không được thưởng như false. Highlight chỉ có nhãn rõ ở graph trang 494; các trang khác còn thiếu gold highlight. Trang 129 chỉ có rubric, chưa có inventory trạng thái đầy đủ nên **không có điểm accuracy tự động cho trang này**.

Bằng chứng baseline cũ: [old_3B_semantic_diagnostics.json](evidence/old_3B_semantic_diagnostics.json). Các phép đo này chỉ là tập chẩn đoán chọn có chủ đích, không tổng quát thành điểm VLM toàn học phần.

### So model sau khi sửa pipeline

- Production: **Qwen/Qwen2.5-VL-7B-Instruct**, revision `cc594898137f460bfe9f0759e9844b3ce807cfb5`.
- Baseline: Qwen/Qwen2.5-VL-3B-Instruct, revision `66285546d2b821cf421d4f5eb2576359d3770cd3`.
- Hai bên cùng NF4/double quant, FP16 compute, SDPA, batch 1, max_visual_tokens=768, max_new_tokens=2048, do_sample=false, cùng ảnh/prompt.
- Notebook chạy baseline 3B **5 crop mới cần thiết** vì prompt đã đổi; không chạy lại toàn bộ 56 output 3B đã có.
- Qua canary bảng và schema baseline mới chạy 7B pilot; qua schema pilot mới mở rộng 7B. Metric ngữ nghĩa không tự phê duyệt dữ liệu, dù cao hơn baseline.
- Không gọi số đo cũ 3B FP16 là đối chứng công bằng với 7B NF4. Chưa có số đo thời gian/VRAM/semantic của cặp mới cho đến khi nhận ZIP Colab.

## 6. Bảo toàn dữ liệu và cache

Release: [runs/it3170_v2_release](runs/it3170_v2_release). Manifest baseline `992e2fb4ff9b…`; production `d682e3b25b0d…`. Hai gói ZIP có CRC hợp lệ, manifest/crop/worker/prompt/schema/adapter/auxiliary hashes và cache identity đều đã kiểm tra.

Production có **817 request: 745 formula + 16 table + 56 VLM**. Sau seed có thể còn 735 formula và 56 VLM phải chạy, cộng pilot baseline 3B 5 crop. 100 alias exact được ghi riêng, không nâng alias thành extraction đã xác minh. Việc tăng formula request là do tách vùng; không làm tăng số trang VLM.

26 seed chỉ tái sử dụng inference có ảnh/engine/native cell text và model/package phù hợp, qua validator mới, có source cache key/manifest/evidence lineage. Không đổi raw output cũ để giả lập một lần chạy model mới. Worker kiểm tra hash seed trước nạp; thay prompt/model/config phải có key mới. Đã smoke-test nạp seed và gate canary thành công mà không gọi model lại.

Đã đối chiếu [preserved_source_hashes.json](runs/it3170_v2_release/preserved_source_hashes.json): ZIP kết quả cũ, manifest, region inventory, worker, prompt, validator và toàn bộ file CPT cũ không đổi. Native PDF và render hash được kiểm tra trước crop lại. Bộ CPT release là bản sao nguyên bộ cũ, không ghép prediction hoặc annotation benchmark.

## 7. Kiểm thử và phần chưa thực hiện

- **26 unit/source regression v2 PASS**: enum, ví dụ prompt, legacy migration không inference, dangling edge, không tự verified, công thức lặp/corrupt, math symbols, crop mixed text, chồng bảng, bbox guard và các trang 129/494/812/930/1042.
- **25 regression cũ PASS** trong tiến trình riêng; không sửa code cũ để làm test qua.
- **16/16 table integration CPU PASS** sau canary và sửa bbox; trace những lần thất bại vẫn lưu.
- Syntax toàn bộ Python và mọi code cell notebook PASS; CRC ZIP, cache identity, hash nguồn và seed smoke PASS.
- Log: [unit_v2.txt](evidence/unit_v2.txt), [regression_original.txt](evidence/regression_original.txt).

Chưa thực hiện: inference Colab với 7B/baseline prompt mới, benchmark FormulaNet trên crop mới, duyệt đầy đủ nội dung 16 bảng, gold toàn bộ cây 4-Queens, precision/recall routing và độ phủ kiến thức toàn PDF. Báo cáo không khẳng định các phần này đã đạt.

## Tài liệu chính thức đã đối chiếu

- [PaddleX v3.7.2 table pipeline](https://github.com/PaddlePaddle/PaddleX/blob/v3.7.2/paddlex/inference/pipelines/table_recognition/pipeline_v2.py) và [hậu xử lý table v2](https://github.com/PaddlePaddle/PaddleX/blob/v3.7.2/paddlex/inference/pipelines/table_recognition/table_recognition_post_processing_v2.py); source/package hashes local được lưu riêng.
- [Qwen2.5-VL-7B model card](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct).
- [Transformers bitsandbytes/NF4](https://huggingface.co/docs/transformers/v4.57.1/en/quantization/bitsandbytes).

Hướng dẫn chạy và nhập ZIP mới: [README.md](README.md).
