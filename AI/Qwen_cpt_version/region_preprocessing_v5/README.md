# IT3170 preprocessing v5

**Đã chốt v5.0.0 làm phiên bản chính thức.** Chạy corpus qua [entrypoint và đặc tả chính thức](D:/BKQuiz/AI/data_preprocessing/README.md). Mã tại thư mục này là workspace phát triển/lịch sử; snapshot chính thức được giữ riêng, kiểm SHA trước khi chạy. Các lệnh IT3170 dưới đây vẫn mô tả run cũ để truy vết.

Pipeline: **Native + OCR + VLM + Cross-validation + Human Review**. V5 là một phiên bản độc lập; không sửa đầu ra, manifest hay CPT dataset của v1–v4.

Đã nhập ZIP Colab ngày 21/10/2026: **6/6 mô tả VLM**, 17/17 lượt OCR thành công. Xem [phân tích kết quả và so sánh các phiên bản](evaluations/colab_24f2f2d02890_20261021/REPORT.md). API thành công không đồng nghĩa đúng nội dung.

## Bắt đầu

Mở PowerShell ở `D:\BKQuiz`:

```powershell
$py = 'AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe'
$v5 = 'AI\Qwen_cpt_version\region_preprocessing_v5'
$run = "$v5\runs\it3170_v5_20261020"
& $py "$v5\review_app.py" --run $run --port 8765
```

Mở **http://127.0.0.1:8765**. App Python chạy bằng thư viện chuẩn, không cần Streamlit hoặc tài khoản Label Studio. Nếu cổng đang được dùng, chọn `--port 8766`.

Run local đã chuẩn bị đủ ảnh của 1.060 slide IT3170 và đã nhập kết quả pilot. Hàng đợi người duyệt mặc định **chỉ có đầu ra VLM thành công, không rỗng**: hiện 6 mô tả trên 6/1.060 slide (0,57%). Native/OCR/formula/table không có VLM không nằm trong hàng đợi này.

## Chạy máy trên Colab

1. Upload `cloud_packets/it3170_v5_pilot_11pages/v5_colab_input.zip` lên Drive hoặc qua ô upload của notebook.
2. Mở `Colab_Region_Preprocessing_V5.ipynb`, chọn GPU. Mặc định chạy pilot 11 trang: **20, 33, 35, 49, 129, 300, 494, 812, 869, 930, 1042**. Có native/OCR, công thức, bảng và các hình khó.
3. Chạy OCR, parser được bật, rồi VLM. Các engine chạy trong process/môi trường riêng. Notebook thử khôi phục các môi trường đã lưu trên Drive; chỉ dùng lại khi phiên bản và kiểm tra import đạt.
4. Tải ZIP kết quả và nhập về local bằng lệnh dưới đây. Việc nhập chỉ thêm kết quả máy; không tạo quyết định người duyệt.

```powershell
& $py "$v5\cli.py" merge --run $run `
  --packet "$v5\cloud_packets\it3170_v5_pilot_11pages" `
  --results "$env:USERPROFILE\Downloads\TEN_ZIP_KET_QUA.zip"
```

Để chạy OCR/parser trên toàn bộ inventory, tạo gói **mới** rồi bật `RUN_ALL` trong notebook:

```powershell
& $py "$v5\cli.py" package --run $run `
  --out "$v5\cloud_packets\it3170_v5_all" --scope all --model 7b
```

Không thể dùng gói pilot để suy luận các trang không nằm trong gói. Chọn `--model 3b` nếu muốn profile nhẹ hơn; mặc định giữ **Qwen2.5-VL-7B-Instruct NF4**. `--formula-crosscheck` là lựa chọn bổ sung, không mặc định đưa mọi công thức sang VLM. Formula/table seed hợp lệ được tái sử dụng. Chỉ bật chạy lại specialist khi có lý do cụ thể.

Inventory có 424 vùng hình để lưu nguồn và định tuyến, nhưng mặc định gói toàn bộ chỉ định tuyến **56 vùng trên 56/1.060 trang (5,28%)** sang VLM theo lịch đã có. Các hình dưới ngưỡng hoặc trùng vẫn còn trong records/diagnostics, không đẩy toàn bộ vào hàng đợi người duyệt. Pilot có thêm hình tham chiếu trang 300. `--all-visuals` mới yêu cầu VLM cho cả 424 vùng; khi đó ngân sách 4–8% không còn áp dụng.

## Ba nhóm và thao tác người duyệt

| Nhóm máy | Ý nghĩa | Cách xử lý |
|---|---|---|
| Tin cậy (`trusted`) | Văn bản rủi ro thấp có native và OCR độc lập khớp, cùng nguồn/vùng, không lỗi hoặc bất đồng | Nhóm máy trong kiểm kê; không yêu cầu duyệt riêng native/OCR |
| Chưa chắc chắn (`uncertain`) | Thiếu một nguồn, các nguồn khác nhau, ảnh khó đọc, mô tả VLM hoặc nội dung rủi ro cao | Chỉ đầu ra VLM thành công được đưa vào web để duyệt |
| Lỗi nghiêm trọng (`critical`) | Không có đầu ra sử dụng được sau khi xử lý, nguồn sai, hoặc công thức hỏng cấu trúc | Giữ chẩn đoán; lỗi không có text VLM không được biến thành đề xuất để duyệt |

**Tin cậy của máy không đồng nghĩa đã được con người xác minh.** Ba nhóm vẫn được lưu trong JSONL cho toàn pipeline. Theo yêu cầu cập nhật, web chỉ dùng để xác nhận thông tin VLM; không tự xác minh phần dữ liệu bị ẩn khỏi queue. Một mô tả VLM đúng một phần được phép giữ lại, nhưng không được coi là bao phủ toàn bộ hình.

Trong app:

1. Điền tên người duyệt thật một lần; trình duyệt ghi nhớ tên.
2. Xem slide gốc và nguyên văn VLM. Crop/ngữ cảnh/candidates/lịch sử nằm trong các phần mở rộng.
3. **← / →** chuyển mục; **↑** chấp nhận; **↓** loại bỏ. Lên/xuống ghi ngay quyết định rồi chuyển mục tiếp theo. Chỉ chấp nhận sau khi đã đối chiếu ảnh.
4. Muốn sửa, bấm **Sửa**, chỉnh nội dung rồi bấm **Lưu bản sửa**. Phím tắt không hoạt động khi đang gõ/sửa; giữ phím không ghi lặp quyết định.
5. Không phải nhập lại ghi chú/checkbox cho mỗi lần duyệt nhanh. Quyết định vẫn gắn tên người, thao tác thực tế, revision và hash ảnh trong SQLite; không ghi đè lịch sử cũ.

Nếu kết quả máy hoặc ảnh nguồn thay đổi sau khi duyệt, quyết định cũ trở thành **stale**, cần duyệt lại. App không dùng câu trả lời máy làm nhãn chuẩn.

## Xuất CPT cho Qwen3 1.7B

```powershell
& $py "$v5\cli.py" export --run $run --out "$v5\datasets\it3170_v5_reviewed_01"
```

Chỉ các mục `approve/correct` còn hiệu lực, thuộc split `train`, được xuất. Nếu chưa duyệt thì dataset rỗng và `training_ready=false`. Development/holdout và nhóm chống rò rỉ từ v3 được giữ lại. Có thể thêm `--tokenizer DUONG_DAN_TOKENIZER_LOCAL` để đóng gói token 1.024, thêm EOS và lưu ánh xạ token về nguồn. Không áp dụng chat template cho CPT.

Sáu mô tả pilot hiện có 5 mục development và 1 mục train (trang 300). Duyệt xong không đồng nghĩa cả sáu sẽ được đưa vào tập train. Việc thu hẹp giao diện sang VLM không tự phê duyệt native/OCR hoặc bỏ quy tắc nguồn/holdout khi export.

Các file: `train.jsonl`, `train.metadata.jsonl`, `excluded.jsonl`, `manifest.json`; khi có tokenizer thêm `train.packed.jsonl` và `token_source_spans.jsonl`. Unicode NFC được chuẩn hóa; dấu toán học, số và ký hiệu được giữ. Email được che trước khi xuất. Perceptual hash chỉ tạo gợi ý trùng; chỉ loại tự động khi **cả văn bản và pixel ảnh khớp chính xác**.

## Công cụ và ranh giới

| Công việc | Công cụ thực thi |
|---|---|
| Phân loại PDF, native text, tọa độ, render | PyMuPDF; giữ cache nguồn đã kiểm hash |
| PPTX gốc nếu cung cấp | python-pptx; giữ shape/table/chart và drawing order, không gọi đó là reading order đã xác minh |
| Layout ban đầu của IT3170 | Tái sử dụng vùng PP-DocLayout/rule-based và crop công thức đã sửa từ các phiên bản trước |
| Layout/reading order/table bổ sung | Docling, adapter + worker Colab độc lập; mặc định không dùng native Docling như một OCR độc lập |
| OCR tiếng Việt | PaddleOCR PP-OCRv3 `lang=vi` |
| Công thức | PP-FormulaNet-S, kiểm tra cấu trúc và giữ seed/raw/source |
| Bảng | PP-StructureV3, để pipeline sở hữu OCR tiền xử lý; không giả lập `doc_preprocessor_res` |
| Parser đối chiếu tùy chọn | MinerU, môi trường riêng; adapter cho legacy và DocVortex schema 2.0 |
| Sơ đồ | Qwen2.5-VL, một ảnh → một mô tả tự nhiên |
| Ảnh mờ/trùng | Pillow, OpenCV, ImageHash; chỉ gắn cờ, không tự xóa hình ít chữ |
| Schema, logic | Python, Pydantic; schema áp dụng cho record nội bộ, không ép VLM sinh schema |
| Kiểm duyệt | App Python + SQLite; có adapter Label Studio tùy chọn |

Docling/MinerU không được cài và chạy model thật trên máy local trong đợt triển khai này. Notebook cung cấp luồng chạy độc lập; mọi lỗi cài đặt/suy luận phải được lưu. Với tài liệu mới, native và ảnh raster có thể chuẩn bị ngay; thành phần parser phát hiện ngoài inventory hiện có được giữ trong `unmatched` của import receipt để định tuyến bổ sung, chưa tự biến thành vùng huấn luyện.

## Label Studio tùy chọn

```powershell
& $py "$v5\label_studio.py" export --run $run --out "$v5\label_studio_tasks_01"
& $py "$v5\label_studio.py" import --run $run `
  --annotations 'D:\annotations.json' --reviewer 'TEN_NGUOI_DUYET' `
  --report "$v5\label_studio_import_01.json"
```

Export gồm assets và cấu hình gán nhãn. Cần cấu hình local-file storage của Label Studio theo tài liệu của họ. Import chỉ nhận annotation có người duyệt/bằng chứng và đúng hash nguồn; không nhận `predictions` làm phê duyệt.

## Đánh giá

Xem `REPORT.md` và `METRICS.md`. Chạy kiểm thử:

```powershell
Push-Location $v5
& '..\data_preprocessing\.venv\Scripts\python.exe' -m unittest discover -p 'test_*.py' -v
Pop-Location
```

Prompt thực tế ở **`vlm_worker.py`, biến `PROMPT`**; notebook sử dụng worker này. Gói Colab lưu SHA-256 prompt, mã runtime, ảnh nguồn, crop và cấu hình model để truy vết.
