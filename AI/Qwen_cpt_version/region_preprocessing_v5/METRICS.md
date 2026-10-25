# Đánh giá chất lượng v5

Không dùng điểm confidence hoặc tỷ lệ `trusted` làm độ chính xác. Bộ kiểm thử code, số API thành công và chất lượng kiến thức là ba đại lượng khác nhau.

| Metric | Cách tính trong code | Cần nhãn nào? |
|---|---|---|
| Label Accuracy / A | Số loại vùng đúng / số loại đã kiểm | Loại vùng do người gán |
| CER | Tổng Levenshtein ký tự / tổng ký tự chuẩn | Transcript chuẩn |
| WER | Tổng Levenshtein từ / tổng từ chuẩn | Transcript chuẩn |
| Layout IoU / L | Trung bình giao/hợp bbox | Bbox chuẩn cùng hệ [0,1000] |
| Image–Label Alignment | Tỷ lệ true trong đánh giá người | Người đối chiếu ảnh với nội dung |
| Formula Exact Match | Khớp nguyên văn sau NFC/khoảng trắng, cả hai công thức hợp lệ cấu trúc | LaTeX chuẩn |
| Coverage / C | Số thành phần chuẩn được ghép đúng / tổng thành phần chuẩn | Inventory và matching do người xác nhận |
| Groundedness / G | Trung bình điểm [0,1] do người đánh giá | Mức bám sát ảnh của đúng đầu ra hiện tại |
| Structural validity / D | Tỷ lệ record hợp lệ schema nội bộ trên mẫu đánh giá | Kiểm tra Pydantic; không chứng minh đúng kiến thức |

`Q = .30 A + .25 G + .20 C + .15 L + .10 D`. Code trả Q trong [0,1], nhân 100 để có thang 100. Thiếu một chiều thì **Q=null**, không tự bù bằng điểm confidence hay đổi trọng số. CER/WER có thể lớn hơn 1 nếu có nhiều ký tự/từ chèn thêm. Không đồng nhất formula exact match với tương đương toán học.

Chọn mẫu phân tầng theo text/formula/table/diagram, ba nhóm rủi ro, native/mixed/visual-only. Luôn có các ca khó trang 129, 494, 812, 930, 1042. Khuyến nghị người thứ hai kiểm tra độc lập một phần mẫu và giải quyết bất đồng. Giữ một tập gold cố định trước khi so sánh v3/v4/v5; không chọn riêng những mẫu thành công của mỗi bản.

## Nhập reference

Mỗi dòng `references.jsonl` tương ứng một record. Chép `id`, các SHA và `machine_revision` từ run thật, rồi người duyệt điền reference/assessment. Ví dụ cấu trúc dưới đây **chỉ minh họa, không phải gold đã xác minh**:

```json
{"id":"ID_THAT","source_sha256":"SHA_PDF","render_sha256":"SHA_RENDER","crop_sha256":"SHA_CROP","machine_revision":"REVISION_THAT","reference_verified":true,"reviewer":"TEN_NGUOI_DUYET","reference":{"text":"Nội dung chuẩn đã đối chiếu","label":"diagram","bbox":[100,200,800,900],"component_ids":["khai_niem_1","quan_he_1"]},"assessment":{"groundedness":0.8,"image_label_aligned":true,"matched_prediction_component_ids":["khai_niem_1"]}}
```

Chỉ thêm trường có thể chấm: `latex` cho công thức; `component_ids` khi đã lập inventory. `matched_prediction_component_ids` là những thành phần chuẩn thực sự xuất hiện đúng trong mô tả máy, do người xác nhận. `assessment` bị từ chối nếu revision đã thay đổi. Reference text chuẩn vẫn có thể dùng lại giữa các model nếu cùng nguồn/vùng.

```powershell
$py = 'AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe'
$v5 = 'AI\Qwen_cpt_version\region_preprocessing_v5'
& $py "$v5\evaluate_run.py" --run "$v5\runs\it3170_v5_20261020" `
  --references 'D:\references.jsonl' --out "$v5\evaluation_human_01.json"
```

Để đánh giá tập prediction chuẩn hóa từ phiên bản khác, dùng `metrics.py --references ... --predictions ... --out ...`. Giữ cùng sample, bbox, quy tắc chuẩn hóa và mẫu số. Kết quả ghi rõ từng mẫu số, số reference bỏ qua, prediction thiếu và phạm vi chỉ trên mẫu đã gán nhãn.

Chưa có gold người dùng cho v5 nên hiện chưa báo cáo CER, WER, Accuracy, Coverage hay Q thực nghiệm của toàn bộ tài liệu. Một VLM mô tả ngắn có thể bám sát ảnh tốt nhưng coverage thấp; cả hai phải được báo cáo riêng.
