# Thử pipeline local CPU + Colab GPU trên IT3170

Đợt thử riêng trên PDF `D:\bk_quizz_data\slide_processed\pdf\IT3170-Thuật toán ứng dụng.pdf`, 1.060 trang. Không thay dữ liệu preprocessing hoặc model CPT trước đây. Kết quả thực tế xem [TEST_REPORT.md](TEST_REPORT.md).

## Luồng

1. **Windows CPU:** đọc PDF, render và lấy chữ theo tọa độ; NFC, nối dòng có điều kiện, giữ code/số/ký hiệu; lọc lề lặp và che PII có quy tắc.
2. **Windows CPU:** SHA-256, MinHash 128 permutations/seed 42 và SimHash 64 bit. SHA chữ chỉ phát hiện ứng viên; chỉ trùng cả chữ và ảnh trang mới được coi là trùng toàn trang. MinHash/SimHash chỉ nhóm, không tự xóa.
3. **Windows CPU:** bản preview JSONL + packing 1.024 token bằng tokenizer Qwen3 của HF export đã có. Có EOS, giữ đoạn cuối, metadata nguồn và ánh xạ token. `training_ready=false` vì còn thiếu kiểm tra layout/OCR/vision.
4. **Colab GPU:** PaddleOCR `lang=vi, PP-OCRv3`; PP-DocLayout-M phát hiện vùng trước PP-FormulaNet-S; Qwen/Qwen2.5-VL-3B-Instruct đọc hình, bảng và quan hệ. Các tiến trình chạy nối tiếp, môi trường Paddle/Torch riêng.
5. **Windows CPU:** nhập ZIP kết quả, kiểm tra hash tài liệu/ảnh/manifest; đối chiếu ứng viên với ảnh. Chỉ transcript được xác minh mới được xuất thành `reviewed_cpt/`. Chạy lại cả ba phép dedup sau khi nhập phần đã kiểm tra.

Không dùng Qwen3:1.7b text để thay thế VLM. PP-FormulaNet chỉ đọc vùng công thức; không thay bước định vị vùng. VLM không được phép tự viết lại toàn bộ slide. Cấu hình này chưa có model table structure chuyên dụng: bảng từ VLM phải được kiểm tra hàng/cột trước khi nhận.

## Chạy phần Colab đã chuẩn bị

1. Mở Google Colab → **Upload notebook** → chọn `IT3170_Hybrid_Preprocessing.ipynb` trong thư mục này.
2. Chọn GPU runtime. Mục tiêu thử là T4 16 GB hoặc GPU lớn hơn, batch 1; không coi Colab Pro là cam kết luôn được cấp loại GPU này.
3. Chạy từ trên xuống. Khi notebook hỏi file, chọn `runs/it3170_test/colab_input.zip` (khoảng 1,7 MB).
4. Cho phép mount Drive để kết quả từng trang được lưu tại `MyDrive/BKQuiz_preprocessing/results_<hash>/`. Có thể chạy tiếp sau khi ngắt phiên; chỉ tái sử dụng kết quả đúng hash và cấu hình.
5. Lần đầu tải thư viện CUDA và khoảng vài GB trọng số Qwen2.5-VL. Thời gian cài/tải tách khỏi inference. Hai venv chỉ tồn tại trong `/content/` nên phiên mới cần dựng lại; kết quả nằm trên Drive.
6. Cell cuối tải `colab_results_<hash>.zip`. Kiểm tra `summary.json` trước: lỗi và invalid JSON vẫn được ghi; chưa có gold thì CER/WER và độ chính xác nội dung để null.

Mặc định thử 12 trang **20,49,51,129,130,300,500,800,869,1000,1042,1060**. Có công thức tràn số (20), bảng SMS/input-output (49/51), sơ đồ 4-queens (129), cạnh có hướng (300), chữ tiếng Việt (869), đồ thị vector DFS (1042). Đây là mẫu kỹ thuật được chọn chủ đích, không phải mẫu thống kê ngẫu nhiên và chưa chứng minh xử lý toàn bộ tài liệu thành công.

Giới hạn VLM: FP16, SDPA, batch 1, tối đa 1.280 visual token, 1.536 token đầu ra. Chữ nhỏ có thể cần crop riêng. Model revision được khóa trong notebook; không tự nâng model giữa các trang. OCR có thêm audit bảng ký tự model thực sự tải xuống; `lang=vi` không thay thế phép đo CER/WER.

## Nhập kết quả về máy

Từ `D:\BKQuiz`, thay tên ZIP bằng file thực tế đã tải:

```powershell
AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe AI\Qwen_cpt_version\hybrid_preprocessing\local_pipeline.py merge --results "$env:USERPROFILE\Downloads\colab_results_HASH.zip"
```

Lệnh chỉ nhập ứng viên vào `cloud_return.json` và `cloud_review_queue.jsonl`; không tự thêm kiến thức chưa xác minh vào train. Ảnh toàn trang trong gói upload giữ nguyên nguồn, có thể chứa thông tin liên hệ; gói này là dữ liệu audit, không phải tập text đã che PII để công khai.

Tạo `reviewed_annotations.jsonl`, một dòng cho mỗi trang đã đối chiếu, ví dụ cấu trúc:

```json
{"page":20,"document_sha256":"lấy nguyên từ request_manifest.json","render_sha256":"lấy đúng hash của trang 20","verified":false,"reviewer":"tên người kiểm tra","evidence":"đã đối chiếu chữ, số mũ, dấu nhân và điều kiện tràn số với ảnh","text":"bản chép cuối đã kiểm tra"}
```

Chỉ chuyển `verified` thành `true` sau khi kiểm tra thật. Không điền hash mới để hợp thức hóa annotation cũ. Bản chép phải gồm nội dung học thuật cần giữ: công thức LaTeX, bảng có cấu trúc và mô tả quan hệ trong hình nếu có; không chỉ lấy vài nhãn.

```powershell
AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe AI\Qwen_cpt_version\hybrid_preprocessing\local_pipeline.py merge --results "$env:USERPROFILE\Downloads\colab_results_HASH.zip" --reviews AI\Qwen_cpt_version\hybrid_preprocessing\runs\it3170_test\reviewed_annotations.jsonl
```

Đầu ra `reviewed_cpt/` chỉ gồm các trang đã duyệt, không tự ghép những trang còn chờ xử lý. `train.jsonl` chứa text; metadata/packing/source-map tách riêng. Chọn một loại đầu vào khi train. Một tài liệu vào train, chưa có validation/test độc lập; không chia ngẫu nhiên trang gần trùng.

## Tạo đợt thử khác hoặc mở rộng

Lệnh mặc định đã hoàn tất và sẽ từ chối ghi đè run hoàn tất. Dùng `--run` mới. `--pages` quyết định trang gửi Colab; phần trích xuất và dedup local vẫn đọc cả PDF:

```powershell
AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe AI\Qwen_cpt_version\hybrid_preprocessing\local_pipeline.py prepare --pdf "D:\bk_quizz_data\slide_processed\pdf\IT3170-Thuật toán ứng dụng.pdf" --manifest D:\bk_quizz_data\slide_processed\_audit\manifest.json --run AI\Qwen_cpt_version\hybrid_preprocessing\runs\it3170_test_002 --pages 20,49,51,129,300,869,1042
```

Muốn phủ 1.060 trang cần lập danh sách trang đầy đủ và dự trù GPU/Drive. Không suy thời gian toàn bộ tài liệu chỉ từ 12 trang chưa chạy GPU. Mỗi cấu hình ảnh/crop/model khác nên tạo đợt mới để giữ bằng chứng so sánh.

## Công cụ và phiên bản

Local tái sử dụng môi trường và hàm extraction/normalization đã có trong `data_preprocessing/`, không cài thêm GPU vào Windows. Notebook khóa các thư viện chính và lưu `pip freeze` thực tế của cả hai môi trường cùng hash model Paddle, revision HF, prompt, ảnh và cấu hình.

Tham khảo: [PaddleOCR, ngôn ngữ và phiên bản](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html), [PP-FormulaNet](https://www.paddleocr.ai/main/en/version3.x/module_usage/formula_recognition.html), [Qwen2.5-VL-3B](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct).
