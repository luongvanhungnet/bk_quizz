# Báo cáo triển khai v4 — IT3170

Ngày: 19/10/2026. Run phát hành: `runs/it3170_v4_20261019_final`.

V4 đã được xây dựng và kiểm tra tại máy; **chưa có suy luận Qwen v4 trên GPU**. Chưa xác nhận tăng độ chính xác, giảm thời gian hay loại bỏ OOM trên T4. Các khoảng cải thiện dự đoán trước đây không được coi là kết quả đo.

## Thay đổi theo lỗi v3

| Lỗi thực tế v3 | Cách xử lý trong v4 |
|---|---|
| Quan hệ cây dùng `parent_bbox`, `child_bbox` | Schema, validator và ví dụ prompt sinh từ cùng một định nghĩa; ví dụ relation không rỗng, đúng `parent`, `child`, `bbox` |
| Attributes trả singleton array, quote null | Repair chỉ định dạng có audit: bỏ fence, unwrap một object, đổi quote null thành chuỗi rỗng; thiếu facts vẫn không hợp lệ |
| Trang 812 nhận chú thích thành node | Ứng viên node phải có hình học PDF phù hợp; crop task thu hẹp quanh hình, không đưa toàn bộ layout vào prompt |
| Trang 494 lặp d–e, thiếu b–e | Cạnh native giữ ID riêng, xác nhận inventory, đọc attributes theo nhóm tối đa bốn cạnh; thêm gate bbox/endpoint và trọng số native bị bỏ trống |
| N-Queens bỏ trạng thái và dùng tọa độ ví dụ | Tách 20 bàn cờ, đọc cell từ crop riêng; vị trí board lấy từ proposal cố định có nguồn, links được nhận riêng trên cây tổng thể |
| Trang 930/1042 OOM | Canary chạy trước, giảm context, kiểm tra token/image grid thật, giới hạn output theo task, cleanup trong `finally`, một retry profile nhỏ hơn |
| Chỉ có kiểm thử schema, thiếu model regression | Giữ 10 raw stage v3 làm fixture; thêm test lỗi cũ, cache/retry, giới hạn ảnh, holdout guard và luồng import |

## Dữ liệu và kế hoạch thực thi

- Giữ 818 parent request: 745 formula, 16 table, 57 VLM region trên 56 trang (5,28% của 1.060 trang).
- 44 đồ thị có ứng viên native đủ điều kiện cho luồng hybrid; 11 vùng thiếu hình học phù hợp dùng luồng fallback ngắn.
- Hai cây trang 129 được tách thành 20 task đọc board và hai task đọc links.
- 330 task khai báo: 75 inventory, 211 edge attributes, 11 nodes fallback, 11 edges fallback, 20 board, hai tree links. 88 slot attributes nằm trong nhánh fallback động; chunk không có cạnh được bỏ qua mà không gọi model.
- Canary 930/1042 có 10 task; pilot đầy đủ có 39 task trên sáu parent thuộc năm trang. Số task không đồng nghĩa số crop trang hoặc số inference thực tế sau cache/retry.
- Không tái sử dụng output VLM lỗi v3 như facts đã đúng. Raw output cũ giữ làm regression/audit. 761 specialist seed được giữ nguyên prediction và tính lại quality gate.

Các ứng viên hình học chỉ là bằng chứng đề xuất. VLM có thể từ chối node/cạnh; phần bị bỏ sót hoặc nhập nhằng được ghi uncertainty/review, không tự suy diễn để làm đầy đồ thị. Với nhánh native, model không tự đổi nhãn native hoặc thêm node mới âm thầm; sai biệt cần người duyệt xử lý nguồn và tạo lần chạy mới.

## Hợp đồng, cache và review

`schema.py` là nguồn chung của schema và ví dụ; `prompts.py` sinh hướng dẫn từ đó. Kiểm tra ID chéo ở inventory, attributes, edges và tree links; kiểm tra range/overlap của cell, bbox hữu hạn, field lạ và JSON duplicate key. Root object được yêu cầu nhất quán. Không dùng ví dụ enum nối bằng dấu pipe.

Mỗi lần thử giữ raw output, repair log, lỗi cấu trúc, traceback, profile và telemetry. Cache identity gắn ảnh, context, model revision, code/config, phép biến đổi crop và upstream. Chỉ task thành công cấu trúc được cache; cache vẫn `semantic_verified=false`. Attempt cũ không bị ghi đè.

Import kết quả kiểm tra lại task schema/identity, đối chiếu seed specialist và tái ghép parent từ task output; parent khác bằng chứng task sẽ bị từ chối. Những kiểm tra này bảo vệ tính nhất quán dữ liệu, không chứng minh nội dung model đúng.

## Bộ nhớ và khả năng phục hồi

Model giữ Qwen2.5-VL-7B-Instruct NF4, revision `cc594898137f460bfe9f0759e9844b3ce807cfb5`, torch 2.6.0, transformers 4.57.6, bitsandbytes 0.48.1, SDPA, FP16 compute, batch 1.

Ảnh được resize qua một đường PIL → processor với cùng giới hạn: tối đa 384 visual token, retry 256. Crop nhỏ được tăng số patch mục tiêu khoảng 64 visual token; giữ bbox chuẩn hóa và phép đổi tọa độ để truy ngược nguồn. Không gửi vector paths thô dài vào mọi prompt. Prompt task tĩnh lớn nhất khoảng 3.700 ký tự; fallback có upstream động vẫn được kiểm tra số token thật trước generate.

Giới hạn text 2.048 token, tổng input + output 4.096. Output cap khác nhau theo stage. Worker ghi kích thước ảnh thực, `image_grid_thw`, visual/text/input/output token, allocated/reserved/free VRAM và peak cả khi lỗi. Nếu model forward bản khóa có tham số giới hạn logits prefill thì dùng và ghi tên tham số trong telemetry; nếu không có thì không giả định hỗ trợ.

Tensor được dọn cả nhánh exception. `empty_cache()` không thay cho việc giải phóng tensor. Mỗi task tối đa hai lần thử trong một lượt gọi; retry giảm visual cap có cờ review riêng. Trường hợp vẫn lỗi được giữ, không tự giảm chất lượng nhiều lần hoặc chuyển sang model khác mà không ghi nhận.

Thiết kế resize dựa trên [hướng dẫn Qwen2.5-VL cho Transformers 4.57](https://huggingface.co/docs/transformers/v4.57.1/en/model_doc/qwen2_5_vl). Hiệu quả VRAM cần đo trên T4 thật; NF4 chỉ giảm một phần chi phí mô hình và không bảo đảm mọi input vừa bộ nhớ.

## Specialist và CPT

Giữ 704/745 formula hợp lệ cấu trúc, 41 lỗi cũ ở review; 625 formula vượt heuristic. Bảng giữ 16/16 hợp lệ cấu trúc, 13 vượt heuristic. Không gọi đây là Formula/Table Accuracy. Có 123 item trong `specialist_review_plan.jsonl` và giao diện review HTML: 120 công thức, ba bảng. Mỗi item có category, flags, crop/context/hash và yêu cầu sửa đầu vào hoặc đối chiếu nguồn trước khi rerun/xuất transcript. V4 không mặc định chạy lại các crop specialist giống hệt.

CPT được sao chép nguyên trạng từ split v3: 224 mẫu, 25.691 token, 26 sequence tối đa 1.024 token; 40 mẫu giữ lại và 116 trang trong nhóm holdout được bảo vệ. Bộ 264 mẫu cũ vẫn còn. Bộ benchmark 60 trang vẫn pending, giữ group/split/hashes cũ; không tạo gold từ model giả hoặc từ kết quả VLM.

Chỉ transcript có người duyệt, bằng chứng và hash nguồn đúng mới đi qua exporter CPT. Các output mới luôn vào review queue; số dự đoán mới được xác minh tự động bằng 0. Checkpoint CPT trước đó có thể đã thấy các trang holdout mới; chia lại không xóa tiếp xúc lịch sử.

## Kiểm tra và nghiệm thu

Đã có 37 unit/regression test v4 và 88 test của v1/v2/v3 chạy lại. Log trong `evidence/*_release.txt`. Kiểm tra phát hành phải bao gồm ZIP CRC; hash source/runtime/crop/context/seed; nguồn cũ không thay đổi; loại nhóm holdout khỏi CPT; số token; syntax Python/notebook; luồng mô phỏng và nhập kết quả.

`local_audit.py` dùng model giả trong thư mục tạm để kiểm tra toàn bộ task/parent contract, dynamic fallback, collect và import. Phản hồi giả không được coi là annotation, không được xuất CPT và được xóa cùng thư mục tạm. Mọi số “thành công” trong phần `simulation` của metrics chỉ nói về kiểm thử tích hợp; độ chính xác model để null.

Kết quả kiểm tra phát hành và fingerprint chính xác nằm trong **`evidence/final_validation/metrics.json`** và **`runs/it3170_v4_20261019_final/build_metrics.json`**. Manifest SHA-256: `f0d68dd0cb775b81b5f54c37ebae105bf0b55c184c8186893a36bb38b70349ae`. Input ZIP SHA-256: `4f1f5420c47b3d9ad7ebdf9c699465cd0f70a4759cc4ac07a9dd4ad14519322e`. Các run thử khác được giữ để audit, không dùng làm đầu vào Colab chính thức.

Điều kiện đánh giá thực tế tiếp theo: canary không OOM, đủ pilot có output cấu trúc; đối chiếu node/cạnh/hướng/trọng số/queen/branch với nguồn; chấm cùng gold cũ và bộ nhãn mới sau khi hoàn tất. Chỉ khi đó mới so sánh chất lượng, thời gian và verified tokens/hour với v2/v3. V4 chưa được tuyên bố đạt các điều kiện GPU/ngữ nghĩa này.
