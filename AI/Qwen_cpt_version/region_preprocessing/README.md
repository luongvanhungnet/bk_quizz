# Pipeline theo vùng: native → FormulaNet/Table Recognition → batch VLM

Đợt được giao cho người dùng: **`runs/it3170_regions_v4`**. Các thư mục v1–v3 là bản thử nội bộ trước khi kiểm tra ảnh crop; không dùng gói đó để chạy đợt này. PDF gốc, kết quả preprocessing cũ và model CPT không bị sửa.

**Mục tiêu ngân sách:** dưới 5% số trang PDF được gửi inference VLM mới. Với 1.060 trang, giới hạn nghiêm ngặt là 52 trang; với 1.000 trang là 49. Không dùng số crop thay số trang và không đếm trang chưa xử lý là đã sạch.

Xem [REPORT.md](REPORT.md) để biết số lượng thực tế, độ phủ còn thiếu và phạm vi kiểm thử.

## Luồng đã triển khai

1. **Native + layout:** dùng native PyMuPDF đã trích đầy đủ 1.060 trang, kiểm tra lại SHA PDF, số trang và từng ảnh render. Tái sử dụng 1.060 cache PP-DocLayout-M chỉ khi khớp hash PDF/ảnh; không dùng lại các LaTeX OCR cũ để giả lập inference mới. Khi thiếu layout có thể thêm `--detect-missing` để chạy detector trên CPU; nếu không, trang thiếu vào Review Queue.
2. **Vùng kiến thức:** định tuyến từ nhãn layout và native geometry. Text/code giữ ở PyMuPDF. Math native chưa được detector bao phủ vẫn có crop FormulaNet. Vector chưa phân loại chắc chắn được giữ làm ứng viên/rà soát, không âm thầm xóa.
3. **Lọc:** logo/footer/header/số trang theo nhãn và vị trí; bìa đã đối chiếu hash được loại như non-content; nền vector tô từng dòng code giữ ở nhánh native. Một số ảnh chân dung/minh họa đã xem được gắn routing annotation và giữ ở review thay vì VLM; không suy đoán danh tính hoặc tự bỏ ngữ cảnh học thuật. Đây chưa phải bộ phân loại ảnh hoàn hảo cho mọi PDF.
4. **Định tuyến chuyên biệt:** formula → PP-FormulaNet-S; table → TableRecognitionPipelineV2; diagram/graph/chart ứng viên → Qwen2.5-VL-3B-Instruct. Table Recognition dùng cell text từ native PDF. Bảng không có chữ native vào review/OCR riêng, không tự chuyển sang VLM.
5. **Crop:** padding 8 pixel; VLM tối đa cạnh dài 1.024 pixel và khoảng 768 visual token. Lưu bbox trang, kích thước trước/sau, hash pixel gốc, hash pixel sau resize và file SHA-256. Crop có chữ/nhãn quá nhỏ có thể cần xử lý lại ở độ phân giải khác rồi kiểm tra nguồn.
6. **Batch:** nhóm crop theo kích thước/tỷ lệ; batch 2, FP16, SDPA, padding trái, max_new_tokens=1024. Chưa đo throughput của cấu hình mới trên Colab, không cam kết giảm thời gian theo tỷ lệ batch.
7. **Cache:** khử trùng bằng pixel SHA-256 **trước resize**, không xóa gần trùng vì màu/cạnh/trọng số có thể khác. Cache inference ràng buộc model revision, prompt, schema/worker, cấu hình, hash crop gốc/crop tối ưu và native table text. Cache chung trên Drive; output structurally invalid không thành cache thành công. Thay manifest config mà không dựng lại cache key sẽ bị từ chối.
8. **Validate → CPT/Review:** kiểm tra JSON, node ID, tham chiếu cạnh, kiểu hướng/trọng số, HTML bảng và cú pháp LaTeX cơ bản. Bỏ wrapper Markdown có ghi dấu phục hồi, không sửa nội dung để hợp thức hóa output. Cấu trúc đúng không đồng nghĩa kiến thức đúng: dự đoán mới phải được đối chiếu nguồn trước khi vào CPT. Bản CPT ban đầu chỉ kế thừa các mẫu đã qua cổng cũ và vẫn an toàn theo routing mới.

## Giới hạn dưới 5% và Review Queue

Lọc/khử trùng hiện chưa làm số ứng viên tự nhiên giảm xuống dưới 5%. Scheduler thực thi giới hạn trang và lấy mẫu ưu tiên theo từng phần của tài liệu; phần vượt ngân sách có trạng thái `deferred_budget`. Không coi các slide trạng thái gần giống là cùng hình; mỗi bước đổi màu/cạnh/số vẫn được giữ.

Tỷ lệ trong report có ba nghĩa khác nhau:

- `natural_unique_vlm_page_ratio`: trang có ứng viên VLM chưa được giải quyết sau lọc/reuse/exact dedup, trước giới hạn ngân sách; không phải số trang được chứng minh đều bắt buộc VLM.
- `scheduled_vlm_page_ratio`: trang thực sự được lập lịch cho VLM, nhỏ hơn 5%.
- `vlm_alias_coverage_pages`: trang có thể dùng chung kết quả crop trùng chính xác, có thể lớn hơn số trang được gửi inference; vẫn cần kiểm tra ngữ cảnh/trang.

`full_knowledge_coverage_met=false` cho đến khi các vùng còn thiếu đã được xử lý/xác minh. Muốn đạt đồng thời độ phủ cao và <5% inference, cần thêm native graph parsing, classifier chuyên biệt hoặc thêm annotation/cache đã xác minh; không thể chỉ tăng mức lọc rồi coi nội dung biến mất là đã xử lý.

## Chạy Colab

1. Upload [IT3170_Region_Routing.ipynb](IT3170_Region_Routing.ipynb) lên Colab, chọn GPU.
2. Chạy từ trên xuống; khi được hỏi chọn [region_input.zip](runs/it3170_regions_v4/region_input.zip).
3. Notebook tái sử dụng hai venv cũ trong `/content/` nếu đúng phiên bản, hoặc cài riêng Paddle GPU/Torch khi phiên mới. Các file model vẫn cần tải nếu chưa cache.
4. Output từng crop và log nằm ở `MyDrive/BKQuiz_region_preprocessing/results_<hash>/`. Cache chung nằm tại `MyDrive/BKQuiz_region_preprocessing/cache/`.
5. Cell cuối tải `region_results_<hash>.zip`. Mọi lỗi, OOM, cắt dở, schema sai đều được ghi lại; không tự chuyển sang pipeline toàn trang hoặc VLM cho bảng.

Nếu batch 2 báo OOM, giữ kết quả lỗi để audit và tạo plan mới bằng `plan --batch-size 1 --out AI\Qwen_cpt_version\region_preprocessing\runs\it3170_batch1`. Không chỉnh trực tiếp config trong ZIP cũ rồi tái sử dụng cache key. Batch 2 chưa được kiểm chứng GPU ở đợt này.

## Nhập kết quả

Từ `D:\BKQuiz`, thay tên HASH bằng file thực tế đã tải:

```powershell
AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe AI\Qwen_cpt_version\region_preprocessing\route.py merge --results "$env:USERPROFILE\Downloads\region_results_HASH.zip"
```

Lệnh kiểm tra manifest/cache identity và dựng `prediction_review.jsonl`. Nó không tự thay chữ nguồn bằng VLM. `review_queue.jsonl` giữ cả phần vượt ngân sách và lỗi/cờ chất lượng nguồn. `regions.jsonl` giữ quan hệ `duplicate_of` để đối chiếu kết quả dùng chung.

Sau khi xem ảnh nguồn, thêm transcript cuối vào `reviewed_annotations.jsonl`, mỗi dòng gồm:

```json
{"page":1042,"document_sha256":"lấy từ review_queue.jsonl","render_sha256":"đúng hash trang","verified":false,"reviewer":"người kiểm tra","evidence":"đã đối chiếu đủ đỉnh, cạnh và hướng trong ảnh","text":"transcript gồm native text, công thức, bảng hoặc mô tả quan hệ đã kiểm tra"}
```

Chỉ đặt `verified=true` sau khi kiểm tra thật, rồi chạy:

```powershell
AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe AI\Qwen_cpt_version\region_preprocessing\route.py merge --results "$env:USERPROFILE\Downloads\region_results_HASH.zip" --reviews AI\Qwen_cpt_version\region_preprocessing\runs\it3170_regions_v4\reviewed_annotations.jsonl
```

Đầu ra `cpt/`: text JSONL, metadata, packing, source-map, SHA-256/MinHash/SimHash và tokenizer manifest. Không chia ngẫu nhiên trang gần trùng thành test; chỉ có một tài liệu nên toàn bộ cùng split train. Chọn JSONL text hoặc packed tokens để train, không nạp cả hai. Đoạn cuối được giữ; trainer cần padding label=-100 và causal model dịch nhãn đúng một lần.

## Tạo plan khác

```powershell
AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe AI\Qwen_cpt_version\region_preprocessing\route.py plan --out AI\Qwen_cpt_version\region_preprocessing\runs\it3170_regions_next
```

Lệnh từ chối ghi đè plan hoàn tất. `--native` và `--previous` cho phép chọn cache nguồn khác; routing annotations chỉ áp dụng khi hash PDF/ảnh khớp, không dùng chéo tài liệu. Script hiện dành cho dataset IT3170 đã có provenance; không tự khẳng định chất lượng cho PDF khác.

Tham khảo chính thức: [Table Recognition v2](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/table_recognition_v2.html), [Qwen2.5-VL batch inference](https://huggingface.co/docs/transformers/v4.57.6/en/model_doc/qwen2_5_vl).
