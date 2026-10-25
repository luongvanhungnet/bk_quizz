# Báo cáo triển khai preprocessing v3 — IT3170

Ngày phát hành: 19/10/2026. Run chính: `runs/it3170_v3_20261019`.

Đã triển khai pipeline và kiểm tra tại máy. **Chưa chạy suy luận Qwen v3 trên GPU**, do đó chưa có căn cứ kết luận độ chính xác ngữ nghĩa v3 cao hơn v2. Bộ 60 trang mới đang chờ gán nhãn. Các con số sau phân biệt kiểm tra kỹ thuật, chẩn đoán trên development và kết quả model.

## Thay đổi

- Đồ thị: ba bước nhận dạng node → cạnh → thuộc tính. Mỗi đối tượng có bbox; hướng, trọng số, cạnh tô màu cần bằng chứng cục bộ. Thiếu bằng chứng giữ unknown/cảnh báo, không tự điền true.
- Giữ raw output từng bước, kiểm tra endpoint trước khi cache; ràng buộc id giữa các bước. Hướng cạnh được đổi theo arrow target chỉ qua thao tác được ghi audit rõ ràng.
- Tận dụng text/vector PDF để đưa ra ứng viên node/cạnh và phát hiện bất đồng với VLM. Các ứng viên không được coi là thông tin đã xác minh.
- Trang 129: tách ảnh cây N-Queens thành hai crop, dùng schema trạng thái bàn cờ/quan hệ cha-con thay cho đồ thị nhãn chung. CV đưa ra 11 và 9 ứng viên bàn cờ để đối chiếu.
- Công thức: bổ sung text tại vùng crop, giữ ký hiệu gốc, cảnh báo fragment, delimiter, số không khớp và LaTeX lặp/hỏng. Crop cụ thể bị dính dấu câu được sửa theo span nguồn.
- Bảng: giữ tích hợp Paddle đã sửa ở v2, kiểm tra ô/rowspan/colspan, độ phủ text và các số với vùng native; không chỉ kiểm tra HTML parse được.
- Tách schema validation khỏi semantic review. Không tự nâng trạng thái verified khi sửa schema hoặc vượt heuristic.
- Bộ 60 trang có phân tầng và hàng đợi annotation; nhóm trang nguồn, near-duplicate text và ảnh VLM trùng chính xác cùng split. Nhóm holdout bị chặn khi đóng CPT.

## Số liệu trước/sau có thể xác minh

| Hạng mục | V2 | V3 hiện tại |
|---|---:|---:|
| Trang toàn tài liệu | 1.060 | 1.060 |
| Trang định tuyến VLM | 56 | 56 (5,28%) |
| Crop VLM | 56 | 57 (55 graph + 2 state tree) |
| Công thức có output cấu trúc hợp lệ | 704/745 | 704/745 |
| Công thức vượt heuristic ngữ cảnh v3 | Chưa đo theo luật mới | 625/745 |
| Bảng có output cấu trúc hợp lệ | 16/16 | 16/16 |
| Bảng vượt heuristic ngữ cảnh v3 | Chưa đo theo luật mới | 13/16 |
| Pilot VLM 7B có output | 5 crop | Chưa chạy; chuẩn bị 6 crop |
| Bộ benchmark mới hoàn tất nhãn | Không có bộ này | 0/60 |
| Mẫu CPT kế thừa sau tách nhóm holdout mới | 264 trước tách | 224; dành lại 40 |
| Dự đoán v3 mới được đưa tự động vào CPT | — | 0 |

704 công thức hợp lệ của v3 gồm 703 kết quả v2 tái sử dụng và một canary CPU mới; 41 kết quả lỗi cũ vẫn được giữ trong review, không chạy lại mù quáng. Tổng 761 seed bao gồm 745 công thức và 16 bảng. “Vượt heuristic” không phải tỷ lệ đúng, và các cảnh báo không phải lỗi ngữ nghĩa đã được chứng minh.

### Canary FormulaNet tại máy

Crop `p0033_r00013_f01` trước đây sinh `\mathcal{O}(n\log n)^{\cdot}`. Crop biên mới `p0033_r00013_f01_v3_boundary` chạy PP-FormulaNet-S trên CPU trả về `\mathcal{O}(n\log n)`, loại được số mũ chấm không đúng. Thời gian record khoảng 7,75 giây, gồm khởi tạo model trong lượt này; không đại diện throughput cả tài liệu. Môi trường: PaddleOCR 3.7.0, PaddleX 3.7.2, Paddle CPU 3.2.2. Raw record và hash được giữ trong `evidence/formula_canary_cpu/` và `evidence/formula_canary_identity.json`. Record vẫn `semantic_verified=false`.

### Chẩn đoán đồ thị trên development

| Trang | Node có nhãn từ native | Cặp cạnh ứng viên khớp gold cũ |
|---|---:|---:|
| 494 | 7/7 | 11/11 |
| 812 | 2/2 | 1/1 |
| 930 | 7/7 | 11/11 |
| 1042 | 9/9 | 11/11 |

Tổng 25 nhãn và 34 cặp cạnh khớp trên bốn crop đã dùng chỉnh luật. Đây là chẩn đoán bộ đề xuất hình học native, không phải độ chính xác VLM v3 hoặc kết quả độc lập. Vector cong/đa cạnh vẫn có thể gây nhập nhằng; raw path giữ nguyên để kiểm tra.

Baseline Qwen 7B v2 trên cùng bốn đồ thị: node 25/25; topology precision 30/40 = 75%, recall 30/34 = 88,24%; trọng số 11/11; hướng 8/11; highlight 0/11. Chỉ so sánh model sau khi chạy các bước v3 và đối chiếu cùng gold; không lấy schema pass thay cho những metric này.

### Hàng đợi cần rà soát

- 120/745 công thức có ít nhất một cảnh báo hoặc lỗi cấu trúc. Flag có thể chồng lấp: 41 lỗi cấu trúc, 52 delimiter cần ngữ cảnh, 23 số không được native crop hỗ trợ, 9 thiếu số native, 9 fragment bắt đầu bằng quan hệ.
- Ba bảng cần đối chiếu text/số: `p0035_r00018`, `p0060_r00026`, `p0958_r01267`. Không kết luận cả ba sai khi chưa đọc nguồn.
- 57 crop VLM chưa có dự đoán v3. Lịch ba bước đầy đủ có 167 lời gọi khi không có cache, vì vậy v3 chưa chứng minh nhanh hơn v2.

## Benchmark và dữ liệu CPT

60 trang gồm 24 graph, 18 formula, 8 table, 10 native/sparse; 42 development, 18 holdout. Có 14 trang graph dưới ngưỡng cần gán nhãn để ước lượng bỏ sót định tuyến trên tập mẫu. Nhãn hiện pending: chưa báo CER/WER, Formula Accuracy, Table Accuracy hay Diagram Fact Precision mới.

Các trang từng dùng hiệu chỉnh/duyệt được đưa vào development. Nhóm được nối bằng các đoạn nguồn 50 trang, các cặp text gần trùng đã phát hiện và crop VLM trùng pixel; 116 trang thuộc nhóm được bảo vệ. Đây không phải ranh giới chương ngữ nghĩa hoàn hảo hoặc cam kết phát hiện mọi trùng lặp. Precision/recall định tuyến trên mẫu phân tầng không tự đại diện toàn bộ 1.060 trang.

CPT hiện có 224 mẫu, 25.691 token, 26 chuỗi tối đa 1.024 token; EOS 151645, không chat template, giữ mảnh cuối và nguồn của từng span. 40 mẫu kế thừa thuộc nhóm holdout được tách ra. Bản cũ 264 mẫu vẫn nguyên vẹn. Chỉ transcript có người duyệt, bằng chứng và hash trang khớp nguồn mới được thêm qua `annotations.py`; trang thuộc nhóm holdout bị chặn.

Checkpoint CPT đã huấn luyện trước đây trên bộ 264 mẫu có thể đã tiếp xúc các trang được dành lại. Cần đánh giá downstream từ base hoặc dùng học phần/tài liệu chưa thấy để đo tổng quát hóa độc lập; chia lại dữ liệu không xóa rò rỉ của checkpoint cũ.

## Kiểm thử và bằng chứng

- **88 test PASS**: 37 v3, 26 hồi quy v2, 25 hồi quy v1. Log trong `evidence/*_release.txt`.
- Kiểm tra hash nguồn/code/crop/context/seed, ZIP CRC, snapshot collection không cần model, loại nhóm holdout khỏi CPT, nhất quán nhóm near/exact duplicate, số token và syntax Python/notebook đều PASS.
- Kết quả kiểm tra: `evidence/release_validation/metrics.json`.
- Manifest SHA-256: `aa4973c0f29fe834579fd5f92625e10538cad733218e88c692552a4a0e3d1c73`.
- ZIP SHA-256: `86b83344af652218d64f56a2751a01729b188e4eb76448a7acf18c9d7efc1b6e`.
- Hash nguồn v1/v2 lưu trong `runs/it3170_v3_20261019/preserved_source_hashes.json`.

Model Colab: Qwen2.5-VL-7B-Instruct NF4; torch 2.6.0, transformers 4.57.6, qwen-vl-utils 0.0.14, bitsandbytes 0.48.1. Notebook kiểm tra môi trường trước suy luận, không giả định archive venv luôn chạy được trên runtime mới.

## Giới hạn và bước tiếp theo

Chạy pilot Colab, đọc nguồn để đánh giá node/cạnh/hướng/trọng số/highlight và cây trạng thái rồi mới chạy đầy đủ. Hoàn tất nhãn 60 trang để đo CER/WER, exact LaTeX, cấu trúc ô bảng, graph/state accuracy, precision/recall định tuyến và thời gian duyệt. Chưa có số liệu verified tokens/hour vì chưa diễn ra lượt duyệt này.

Builder hiện gắn với IT3170 và cache nguồn đã có. Contract chart/illustration được triển khai nhưng chưa được đánh giá bằng ảnh thật trong lượt này. Heuristic có thể bỏ sót hoặc báo thừa; kiểm tra hình học không chứng minh quan hệ đúng ngữ nghĩa. Toàn bộ pipeline không tự viết lại giáo trình bằng LLM và không tự xuất facts VLM chưa xác minh vào CPT.
