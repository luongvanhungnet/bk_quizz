# Đánh giá preprocessing hybrid so với đợt trước

Ngày đánh giá: 2026-10-18. Cùng PDF IT3170, 1.060 trang, SHA-256 `c6c829f14bf2a8a1e42b6919d729fdf23865ef4734eb25817f183103dd877087`. Bản mới đã có kết quả Colab thực tế trong `runs/it3170_test/cloud_return.json`, manifest `3754e951ce99206c42bf34ecb199728ed2a9aa3a166eca344549b63b3ab3cf47`. Báo cáo này cập nhật tình trạng sau khi nhập kết quả; TEST_REPORT.md trước đó chỉ phản ánh thời điểm chưa chạy Colab.

**Kết luận: kiến trúc phân chia CPU/GPU khả thi, nhưng bản mới chưa chứng minh chất lượng dữ liệu train tốt hơn. Nó tăng khả năng tạo ứng viên từ hình, đồng thời bộc lộ lỗi OCR tiếng Việt, schema VLM và sai/thiếu quan hệ trong hình. Hiện bộ 264 mẫu đã duyệt của đợt cũ có mức sẵn sàng cho train cao hơn preview của đợt mới.**

## Phạm vi so sánh

| Tiêu chí | Đợt cũ | Hybrid mới | Nhận định |
|---|---|---|---|
| PDF native | 1.060 trang | 1.060 trang | Cùng tài liệu |
| Layout + formula bằng model | 1.060 trang trên CPU | 12 trang trên T4 | Mới chưa đạt độ phủ cũ |
| PP-StructureV3 đầy đủ | 86 trang | Không chạy pipeline này | Pipeline mới thay đổi chức năng; không chỉ đổi phần cứng |
| VLM | Chưa chạy hàng loạt; một số hình được Codex đối chiếu | Qwen2.5-VL-3B chạy 12 trang | Có thêm lớp ứng viên, chưa có duyệt nội dung |
| Trang đã đối chiếu ở đợt cũ | 26 | Chưa có reviewed_annotations mới | Không coi output model là nội dung đã xác minh |
| Đầu ra để train | 264 mẫu sau cổng chất lượng và dedup | 326 mẫu native preview, training_ready=false | Không so số mẫu như cùng tiêu chuẩn |
| Traceability | PDF/trang/ảnh + hash | Giữ lớp đó và hash manifest/worker/prompt/model revision | Cả hai có truy vết; bản mới mở rộng ràng buộc cloud |

326 mẫu so với 264 không phải mức tăng chất lượng hoặc độ phủ kiến thức: bản mới chưa có đầy đủ kiểm tra layout, bảng và công thức trên mọi trang, chưa áp dụng bộ annotation đã duyệt của đợt cũ, và dùng chính sách exact dedup khác. Một số trang ít cờ hơn vì chưa chạy detector, không phải vì đã sạch hơn.

## OCR và công thức

**OCR tiếng Việt chưa được cải thiện như mục tiêu.** Audit model thực sự tải về cho thấy recognizer Latin v5 cũ thiếu 45 ký tự trong bộ probe tiếng Việt; recognizer Latin v3 mới, dù gọi lang=vi, thiếu 50 ký tự. Đây là khả năng biểu diễn ký tự, không phải CER/WER. Không đủ căn cứ suy ra CER tăng bao nhiêu, nhưng không thể coi việc đặt lang=vi đã giải quyết mất dấu.

Ví dụ trang 20, bản OCR mới xuất “Li giái ví du” thay “Lời giải ví dụ”, “Sú dung bién nguyén…” và biến số mũ thành `1018`. Lớp native ở trang này giữ được tiếng Việt và `10^{18}`. Vì vậy OCR cần là lớp bổ sung/đối chiếu, không ghi đè native tốt.

PP-FormulaNet-S vẫn là model đã dùng ở đợt cũ. Bản mới nhận đúng ứng viên `a=b=10^{18}` ở trang 20, nhưng detector chỉ tìm một vùng; công thức kết quả `2×10^{18}` chưa có bản ghi formula riêng. Đợt cũ có đủ hai công thức sau khi đối chiếu ảnh. Nhận dạng đúng một crop không chứng minh đủ mọi công thức của slide. Chưa có Formula Accuracy trên bộ gold độc lập.

CER/WER=0 của đợt cũ chỉ áp dụng hai trang 20 và 100, đo lớp native đã sửa khoảng trắng so với bản chép bởi Codex. Không đại diện toàn tài liệu và không phải benchmark độc lập. Không dùng giá trị này để kết luận toàn bộ OCR cũ hoàn hảo hoặc so trực tiếp với lớp OCR mới.

## VLM: lỗi định dạng và lỗi kiến thức phải tách riêng

- 12/12 request có sinh output, nhưng 0/12 qua parser/schema nghiêm ngặt hiện tại.
- Sau khi bỏ riêng hàng rào Markdown để kiểm tra: 6 trang có đủ bộ trường cấp cao; 5 trang là JSON đọc được nhưng thiếu trường; trang 130 bị cắt ở giới hạn 1.536 token.
- Bỏ Markdown chỉ khắc phục lớp định dạng; không xác minh bảng, cạnh, hướng hoặc công thức. Bổ sung trường rỗng cũng không khôi phục kiến thức bị bỏ sót.

Các ví dụ đã đối chiếu output với ảnh nguồn và/hoặc annotation nguồn cũ:

| Trang | Kết quả mới | Ý nghĩa |
|---|---|---|
| 49, bàn phím SMS | Đọc được các nhóm chữ nhưng Markdown không giữ ma trận 4 hàng × 3 cột, mất ô trống/cấu trúc | Chưa thay thế được bảng HTML đã kiểm tra ở đợt cũ |
| 51, input/output | Đọc được Case #1=29 và Case #2=41; Markdown không tổ chức đúng hai ô chứa nhiều dòng | Có ích về text, chưa đạt table structure |
| 129, 4-queens | Chuyển hình cây trạng thái thành ba nút khái niệm N-Queens/Backtracking/Forward Checking | Là diễn giải chủ đề, không trích đúng cây trạng thái nhìn thấy |
| 300, cạnh có hướng | Có đủ nhãn 1–4 nhưng thiếu cung 3→1 và để một số hướng null; còn lặp quan hệ 2–3 | Mất kiến thức cốt lõi về hướng cung |
| 500, Kruskal | Trích 10/11 cặp cạnh–trọng số đúng; thiếu c–e trọng số 5, không giữ cạnh tô đỏ | Ứng viên hữu ích nhưng thiếu một cạnh có thể làm sai bài toán; chưa đánh giá metric toàn tập |
| 1042, DFS(6) | Ảnh có 9 đỉnh; output chỉ khai báo 5 node và có edge tham chiếu ID chưa khai báo | Không đủ tính toàn vẹn cấu trúc để dùng train |

Nhận xét này là kiểm tra có chủ đích của Codex, chưa phải precision/recall đo trên bộ gold do người độc lập gán nhãn. Chưa có cơ sở báo tỷ lệ đúng chung cho toàn bộ VLM hoặc 1.060 trang.

## Khử trùng

| Thành phần | Cũ | Mới |
|---|---|---|
| Exact | Theo văn bản của các trang đã đủ điều kiện | Chỉ loại trùng toàn trang khi cùng text SHA-256 và cùng render SHA-256 |
| MinHash | 128 permutations, chỉ mục trong 288 trang đủ điều kiện | 128 permutations, xét toàn 1.060 trang |
| SimHash | Xác nhận trên ứng viên MinHash | Tạo ứng viên độc lập bằng 4 band, Hamming ≤3 |
| Kết quả | 24 mẫu exact bỏ, 62 cặp near | 63 nhóm trùng chữ, 9 trang trùng chữ+ảnh, 737 cặp near |

Bản mới bảo thủ hơn với hình: cùng chữ nhưng khác ảnh không bị loại. SimHash độc lập giúp giảm phụ thuộc vào ứng viên MinHash. Đổi lại, exact có thể giữ nhiều trang chỉ khác footer/số trang; số cặp cần rà soát tăng. Không coi 737/62 là mức tăng recall vì khác phạm vi, thuật toán ứng viên và điều kiện lọc; chưa có nhãn duplicate/non-duplicate chuẩn.

## Thời gian và tài nguyên thực tế

T4, batch 1, cùng gói 12 trang; cộng các thời gian đã ghi trong artifact:

| Công việc mới | Thời gian |
|---|---:|
| Đọc/render 1.060 trang local | Khoảng 90,0 giây, ước từ timestamp đầu/cuối |
| Clean + dedup + packing + bundle local | 24,03 giây |
| Paddle 12 trang: OCR + layout + formula | 4,61 giây; khởi tạo riêng 19,11 giây |
| VLM 12 trang | 363,31 giây, trung bình 30,28 giây/trang |
| Khởi tạo VLM | 88,46 giây |
| Cài môi trường Colab lần đầu | 1.677,30 giây, khoảng 27,96 phút |
| VRAM allocated đỉnh của Torch | 8.068.608.000 byte, khoảng 7,51 GiB |

Paddle+VLM và khởi tạo cộng khoảng 7,92 phút; cộng cài đặt lần đầu khoảng 35,88 phút. Đây là tổng các số đã ghi, không phải phép đo end-to-end bao gồm upload/download, thao tác người dùng và mọi overhead. VRAM allocated chỉ là bộ nhớ Torch ghi nhận, không phải tổng VRAM của mọi tiến trình.

Trên đúng 12 trang, log cũ ghi tổng khoảng 5,58 giây cho layout/formula components, cộng 56,00 giây cho PP-StructureV3 ở 7 trang có cache. Không được lấy tổng này chia cho 4,61 giây rồi tuyên bố GPU nhanh hơn bao nhiêu: bản cũ còn nhận dạng cấu trúc bảng ở một số trang, bản mới chạy OCR khác và không cùng đầy đủ chức năng. VLM không có baseline cũ tương đương để đo speedup.

Với pipeline mới, VLM chiếm phần lớn thời gian inference. Giới hạn GPU đang dùng đủ cho lượt thử thực tế, nhưng chưa có thử toàn học phần hoặc profiler RAM máy chủ. Không ngoại suy thời gian 1.060 trang như một cam kết.

## Đánh giá theo mục tiêu

- **Tách tải khỏi laptop 8 GB:** đạt ở nhóm thử; Paddle và Qwen2.5-VL đã chạy trên T4.
- **Tăng khả năng tự tạo ứng viên từ hình:** đạt; đã có output VLM có cấu trúc một phần.
- **Giữ đúng kiến thức để train:** chưa đạt; có thiếu công thức/cạnh/đỉnh, bảng sai cấu trúc và text OCR mất dấu.
- **Khử trùng an toàn với hình:** chính sách mới tốt hơn về phòng tránh xóa nhầm; chưa đo precision/recall.
- **Tăng dữ liệu train đã xác minh:** chưa chứng minh; chưa có reviewed_cpt/train.jsonl mới tại thời điểm kiểm tra.
- **Đánh giá định lượng chất lượng:** chưa đủ gold chung; không gán một điểm /100 tổng hợp tùy ý và không suy ra model CPT sẽ tăng điểm quiz.

## Ưu tiên trước khi mở rộng

1. Giữ native-first. Chỉ OCR vùng scan/chữ hỏng; kiểm tra recognizer thực sự đủ dấu tiếng Việt và đo trên cùng bộ tham chiếu.
2. Tách sửa định dạng VLM khỏi duyệt nội dung. Kiểm tra đủ node, edge tham chiếu hợp lệ, hướng, trọng số, số hàng/cột và các đối tượng bị bỏ sót; trang 130 cần crop hoặc tăng ngân sách đầu ra có kiểm soát.
3. Giữ bảng bằng model table recognition hoặc bản chép có kiểm tra; không thay bảng đã duyệt bằng Markdown VLM chưa đúng cấu trúc.
4. Dùng lại nội dung đã xác minh của đợt cũ nếu hash PDF/ảnh khớp; không bỏ 264 mẫu tốt để thay bằng 326 preview.
5. Chấm cặp trên cùng trang và cùng lớp đầu ra: native, OCR, công thức, bảng, đồ thị. Đo CER/WER, formula exact/semantic correctness và quan hệ đúng/thiếu trước khi mở rộng Colab tới toàn bộ tài liệu.

## Bằng chứng

- [Quality report cũ](../data_preprocessing/outputs/it3170/quality_report.json)
- [QA native hai trang cũ](../data_preprocessing/outputs/it3170/qa/reference_metrics.json)
- [Annotation đã đối chiếu của đợt cũ](../data_preprocessing/outputs/it3170/reviewed_annotations.jsonl)
- [Kết quả local mới](runs/it3170_test/local_result.json)
- [Kết quả Colab đã nhập](runs/it3170_test/cloud_return.json)
- [Hàng đợi rà soát mới](runs/it3170_test/cloud_review_queue.jsonl)

Thời gian khởi tạo, môi trường, GPU và audit OCR lấy từ các JSON runtime trong file người dùng đã tải: `C:\Users\hungw\Downloads\colab_results_3754e951ce99.zip`.
