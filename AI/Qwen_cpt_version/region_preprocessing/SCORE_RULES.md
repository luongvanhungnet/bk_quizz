# Rule-based + PP-DocLayout-M — cấu hình ưu tiên VLM 4–8%

Đợt hiện hành: **`runs/it3170_scored_v3`**. Giữ nguyên các đợt vùng v4 và scoring v1/v2 để audit; không ghi đè dữ liệu train hoặc kết quả GPU trước đó.

## Kết quả trên PDF IT3170

| Chỉ số | Kết quả |
|---|---:|
| Tổng trang có bản ghi đặc trưng | 1.060 |
| Trang tự động chọn VLM theo luật | **56 — 5,28%** |
| Crop VLM | 56, dự kiến 28 batch size 2 |
| Trang ứng viên dưới ngưỡng, giữ review | 314 |
| Cắt vì quota/top-k | **0** |
| FormulaNet riêng | 644 crop |
| Table Recognition riêng | 16 crop |
| Toàn bộ Review Queue | 774 trang, bao gồm cả trang đã lập lịch nhưng chưa được duyệt |
| CPT đã qua cổng cũ được giữ lại | 264 mẫu, 29.771 token |

Tỷ lệ 5,28% là **tỷ lệ được ưu tiên inference tự động**, chưa chứng minh chỉ 5,28% trang cần hỗ trợ thị giác để đạt độ phủ đầy đủ. Những graph đạt S=6 vẫn có thể cần VLM hoặc một extractor khác; chúng ở Review Queue. Bản mới không che phần chưa xử lý bằng cách đánh dấu text đầy đủ.

Các ngưỡng này được hiệu chỉnh và kiểm tra kỹ thuật trên cùng một PDF IT3170. Chưa có tập độc lập hoặc nhãn gold để kết luận precision/recall cao, và không cam kết PDF khác cũng nằm trong 4–8%.

## Công thức và ngưỡng quyết định

`S = 4D + 3C + 2U + R - 4B - 3E`, mỗi biến là 0/1.

Thứ tự quyết định:

1. B=1: bỏ vùng trang trí đã xác minh khỏi inference, giữ nguồn audit.
2. E=1: dùng lại extraction/source review đã xác minh.
3. Crop trùng chính xác: dùng chung đại diện. Nếu kết quả chưa có, trạng thái là **reuse_pending_canonical**, không phải đã xử lý thành công. Đại diện được chọn từ thành viên có bằng chứng/điểm cao nhất để không mất một bản alias rủi ro cao.
4. S≥7: tự động chọn VLM.
5. Chart đã có bằng chứng rõ, C=1 và S≥6: chọn VLM.
6. Vùng chưa giải quyết có điểm thấp/trung gian: review hoặc chờ specialist, không tự vào CPT.

Không thêm trang để đủ 4%, không cắt bớt trang để vừa 8%. Nếu tài liệu khác ra ngoài khoảng này, report ghi `within_target_range=false`.

## Siết sáu đặc trưng

| Đặc trưng | Cách tính / luật |
|---|---|
| has_diagram (D) | Không bật chỉ vì PP-DocLayout-M gán image/chart. Cần bằng chứng topology native hoặc hình học raster, như node labels + vector/link, hoặc cụm node/box + đường nối; hình raster còn cần nền phù hợp và confidence/context củng cố. |
| has_chart (C) | Nhãn chart chưa đủ. Cần từ ngữ trục/thống kê/đơn vị, ít nhất 4 nhãn số, đoạn ngang/dọc phù hợp và vùng đủ lớn. Các graph DFS bị detector gọi chart không tự thành biểu đồ thống kê. |
| native_text_coverage | Tỷ lệ vùng text body do layout phát hiện có ít nhất 3 ký tự native. Không có vùng text thì null. Đây không phải CER/WER, không phải tỷ lệ quan hệ đồ thị đã trích và không tự làm E=1. |
| image_area_ratio | Diện tích bbox crop so với trang; dùng cho R, không đủ để quyết định D. Trang nhiều ảnh chưa chắc cần VLM; chữ nhiều cũng chưa chứng minh hình đã được hiểu. |
| is_duplicate | Trùng pixel gốc trước resize và cùng loại xử lý. Không dùng near-duplicate để xóa trạng thái/nhãn/trọng số khác nhau. Alias chưa có kết quả không được coi là solved. |
| specialist_success (E) | Chỉ true khi có source review/extraction đã kiểm tra, khớp SHA PDF/ảnh và đủ nội dung vùng/trang. Điểm OCR cao, JSON hợp lệ, LaTeX cân ngoặc hoặc đã chạy model đều chưa đủ. Native đã được chấp nhận và không còn vùng unresolved có thể dùng lại. |

B chỉ true cho decoration/non-content đã đối chiếu nguồn; ảnh chân dung/minh họa chưa rõ ý nghĩa học thuật vẫn U=1 và review, không tự bật B.

U=1 khi vẫn có vùng thông tin chưa được extraction/semantic review giải quyết. Text native đầy đủ nhưng chưa có cạnh/hướng/quan hệ thì U vẫn bằng 1.

R=1 khi vùng ảnh chiếm ≥15% trang và **body text <120 ký tự**, hoặc coverage vùng chữ native <60%; chỉ tính rủi ro này khi nội dung chưa được xác minh đầy đủ. Coverage null không tự biến thành 0; điều kiện ít chữ vẫn áp dụng.

## Bằng chứng hình học cho D

- Native topology: ít nhất 4 nhãn ngắn kiểu node, ít nhất 3 vùng vector trong crop và ít nhất 3 đoạn nối đo được.
- Raster topology: tỷ lệ nền sáng ≥45%, ít nhất 3 node tròn + 3 đoạn, trong đó ít nhất 2 đoạn chéo, hoặc ít nhất 4 box + 5 đoạn; có confidence layout ≥0,5 hoặc từ ngữ ngữ cảnh sơ đồ/đồ thị. Điều kiện đoạn chéo hạn chế việc nhầm các lỗ chữ/số và khung trang thành node; raster graph chỉ có cạnh ngang/dọc có thể vào review.
- Dò contour trên cả Otsu và Canny để không bỏ khung màu vàng của flowchart. Phép đo OpenCV thực hiện ở cạnh dài tối đa 512 pixel; ảnh gửi VLM giữ cấu hình crop/resize riêng của đợt vùng.
- Trang có tên học phần + thông tin giảng viên/liên hệ, dưới 4 nhãn node native, được nghi là bìa: chặn D/C suy ra chỉ từ nền sọc/khung chữ. Khi chưa được xác minh, B vẫn bằng 0 và trang vào review.

Đây là heuristic hình học. Nét chữ/cell/mảng có thể tạo false positive; hình mờ hoặc bố cục lạ có thể tạo false negative. Các vùng chưa rõ vào review; không được coi các phép đếm contour là ground truth đồ thị.

## Độ nhạy của ngưỡng

Trên các đại diện crop chưa giải quyết của đợt này:

| Ngưỡng S | Số trang có đại diện đạt ngưỡng |
|---|---:|
| ≥5 | 302 |
| ≥6 | 302 |
| ≥7 | 56 |
| ≥8 | 0 |

Có 246 đại diện vùng đạt S=6 và 56 đại diện đạt S=7; còn 78 đại diện điểm 2/3. Các số là vùng đại diện khi nói đến histogram, khác với số trang. Ngưỡng 7 ưu tiên hình có cả dấu hiệu cấu trúc và rủi ro thiếu nội dung. Không hạ điểm E/B giả để đạt tỷ lệ; cũng không xóa nhóm S=6. Cần duyệt mẫu các nhóm này trước khi kết luận bỏ sót chấp nhận được.

## Ví dụ kiểm tra từ tài liệu

- Trang 5, flowchart: D=1,U=1,R=1 → S=7, chọn VLM; đã sửa phép dò để thấy khung màu vàng.
- Trang 129, cây trạng thái 4-queens: S=7, chọn VLM.
- Trang 1042, DFS(6): S=7, chọn VLM, tránh lặp lỗi thiếu node ở output cũ.
- Trang 20 và 49 đã có bản đối chiếu nguồn: E=1, dùng lại công thức/bảng đã xác minh.
- Trang 206, ảnh minh họa: U=1, review; không coi nó là trang trí đã xác minh chỉ vì không chọn VLM.
- Trang 770, bìa đã đối chiếu hash: B=1 → S=-4, không inference.
- Trang 887, bìa nghi ngờ nhưng chưa có semantic review tương ứng: D=0,B=0,U=1,R=1 → S=3, review. Trang 1043 có một node/khung chữ cũng ở review sau khi siết bằng chứng đường nối, thay vì chọn chỉ vì đếm được nhiều contour tròn.

## Chạy trên Colab

1. Upload **[IT3170_Scored_Routing.ipynb](IT3170_Scored_Routing.ipynb)**, chọn GPU.
2. Khi notebook hỏi file, chọn **[region_input.zip của scored_v3](runs/it3170_scored_v3/region_input.zip)**.
3. Notebook dùng lại worker FormulaNet/Table Recognition/batch Qwen2.5-VL-3B, với model/prompt/schema/config hash mới ràng buộc policy này. Kết quả lưu tại `MyDrive/BKQuiz_scored_preprocessing/`.
4. Sau khi tải ZIP về, merge vào đúng thư mục scored, không dùng mặc định vùng v4:

```powershell
AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe AI\Qwen_cpt_version\region_preprocessing\route.py merge --out AI\Qwen_cpt_version\region_preprocessing\runs\it3170_scored_v3 --results "$env:USERPROFILE\Downloads\region_results_HASH.zip"
```

Muốn đưa transcript mới vào CPT, thêm `--reviews ...\reviewed_annotations.jsonl` như hướng dẫn vùng; chỉ đặt verified=true sau đối chiếu ảnh. Không tự ghép prediction chưa duyệt vào train.

## Tái chạy scoring

```powershell
AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe AI\Qwen_cpt_version\region_preprocessing\score_rules.py --out AI\Qwen_cpt_version\region_preprocessing\runs\it3170_scored_next
```

Đầu vào tái sử dụng 1.060 cache PP-DocLayout-M đã kiểm tra hash và crop gốc v4; không chạy lại layout GPU. Lệnh từ chối ghi đè đợt hoàn tất. Không có bước tự chỉnh ngưỡng để ép tỷ lệ đầu ra. Muốn đổi ngưỡng, cập nhật policy rồi tạo đợt mới để lưu đầy đủ bằng chứng.

Artifact: [policy](runs/it3170_scored_v3/score_policy.json), [feature từng trang](runs/it3170_scored_v3/page_features.jsonl), [điểm từng vùng](runs/it3170_scored_v3/region_scores.jsonl), [report máy đọc](runs/it3170_scored_v3/scoring_report.json), [Review Queue](runs/it3170_scored_v3/review_queue.jsonl).

Kiểm thử kỹ thuật: 25 test PASS, gồm no-quota, native text coverage không tự làm E=1, xử lý alias có điểm cao, tránh bìa/nét chữ giả node và các cổng nguồn/cache/cấu trúc trước đó. Chưa chạy GPU cho gói scoring mới; chưa đo precision/recall hay chứng minh độ phủ kiến thức toàn tài liệu.
