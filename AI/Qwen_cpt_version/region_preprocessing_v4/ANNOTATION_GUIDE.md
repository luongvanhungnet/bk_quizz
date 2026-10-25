# Gán nhãn và duyệt dữ liệu v4

Giữ `benchmark_queue.jsonl` gốc. Sao chép những dòng cần gán nhãn sang JSONL mới, giữ nguyên page, document/render hash, group và split. Xem ảnh qua `benchmark_review.html` cùng PDF nguồn. Dùng development để chỉnh luật; chỉ đánh giá holdout sau khi đã cố định prompt và code.

Với mỗi dòng benchmark được gán nhãn, đặt `annotation_status="verified"`, bổ sung `reviewer` (người đối chiếu), `evidence` (ghi chú nguồn cụ thể) và `gold` gồm:

```json
{
  "contains_knowledge_visual": true,
  "requires_vlm": true,
  "reference": {
    "text": "Bản chép đúng toàn bộ chữ của trang nếu đo CER/WER",
    "regions": []
  }
}
```

Đây chỉ là phần `gold`, không phải một record đầy đủ. Không copy giá trị mẫu làm nhãn thật. `requires_vlm` thể hiện phần kiến thức còn cần VLM sau các extractor chuyên dụng, không chỉ việc trang có ảnh. `reference.text` bỏ trống bằng cách bỏ field nếu chưa có bản chép đầy đủ; không dùng một đoạn ngắn để tính CER/WER toàn trang.

Mỗi phần tử `reference.regions` giữ `request_id` và `input_file_sha256` từ manifest; thêm `latex` cho formula, `html` cho table, `graph` theo định nghĩa gold đồ thị v2 hoặc `state_tree` theo schema v4. Các tọa độ state tree dùng bbox chuẩn hóa 0–1000 trên đúng crop; hàng/cột bàn cờ bắt đầu từ 0. Giữ các nhãn không chắc chắn ở pending thay vì tự xác nhận từ output model.

`annotations.py check-benchmark` kiểm tra thông tin nguồn, trạng thái và split. `evaluate.py --annotations` chỉ chấm vùng có nhãn tham chiếu tương ứng; số lượng mẫu được chấm phải được báo cùng điểm.

## Transcript để đưa vào CPT

Tệp transcript review là luồng riêng với nhãn benchmark. Mỗi dòng cần:

```json
{
  "page": 494,
  "document_sha256": "Lấy đúng từ manifest",
  "render_sha256": "Lấy đúng hash ảnh trang từ manifest",
  "review_type": "source_verified_transcript",
  "verified": true,
  "reviewer": "Tên người đã đối chiếu",
  "evidence": "Vị trí nguồn và cách kiểm tra các thông tin",
  "text": "Nội dung đã đối chiếu với trang nguồn, giữ đúng công thức và ký hiệu"
}
```

Không lấy JSON thô VLM làm transcript. Giữ nội dung quan sát được, không bổ sung suy diễn không có nguồn; biểu đồ chỉ ghi giá trị đọc được. Có thể dùng facts model làm đề xuất để đối chiếu từng ý, nhưng người duyệt chịu trách nhiệm bản transcript cuối. `export-cpt` từ chối trang thuộc nhóm holdout, hash sai, transcript rỗng hoặc thiếu xác nhận/bằng chứng. Output phải là thư mục mới.

