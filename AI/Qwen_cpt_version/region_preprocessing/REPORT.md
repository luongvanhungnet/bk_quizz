# Region routing IT3170 — kết quả triển khai và giới hạn mục tiêu VLM <5%

Ngày: 2026-10-18. Đợt giao cho người dùng: **`runs/it3170_regions_v4`**. Nguồn PDF 1.060 trang, SHA-256 `c6c829f14bf2a8a1e42b6919d729fdf23865ef4734eb25817f183103dd877087`.

**Đã triển khai 8 bước theo vùng và chạy lập kế hoạch/kiểm định local. Scheduler giữ VLM ở 52/1.060 trang = 4,91%. Chưa đạt <5% bằng lọc tự nhiên: vẫn có ứng viên trên 370 trang (34,91%), trong đó 318 trang bị hoãn sang Review Queue. Không coi giới hạn ngân sách là đã xử lý đủ kiến thức.**

## Kết quả thực tế

| Hạng mục | Kết quả |
|---|---:|
| Native/PDF và ảnh nguồn được kiểm tra | 1.060 trang |
| Layout cache PP-DocLayout-M khớp SHA nguồn/ảnh | 1.060 trang |
| Layout thiếu | 0 |
| Vùng nhận diện/giữ sau quy tắc ban đầu | 1.367 |
| Vùng lề trang được loại khỏi routing | 2.339 phát hiện, không phải 2.339 trang/hình duy nhất |
| Trang bìa/non-content đã đối chiếu hash | 22 |
| Nền tô từng dòng code được định tuyến native | 98 nhóm vector |
| Dự đoán chồng vùng code giữ ở native | 12 vùng |
| Crop trùng pixel chính xác không cần inference lặp | 310: 268 formula + 42 VLM |
| FormulaNet được lập lịch | 644 crop |
| Table Recognition được lập lịch | 16 crop |
| VLM được lập lịch | 55 crop trên 52 trang |
| Batch VLM mặc định | 28 batch, batch size 2, batch cuối 1 |
| Trang có thể liên kết crop VLM trùng chính xác | 55, gồm trang alias không gửi inference mới |
| Ảnh minh họa đã phân loại riêng để review | 8 vùng |
| Trang có source review cũ hoặc routing review được tái sử dụng | 29, trong đó 22 non-content |
| Thời gian lập routing/crop/bundle local | 29,48 giây, không gồm chạy layout detector từ đầu hay GPU |
| Gói Colab | 13.817.050 byte, khoảng 13,8 MB |

Tỷ lệ 4,91% tính trên số trang thực sự lập lịch cho VLM, không tính formula/table. Số crop không bằng số trang. Số trang alias có thể lớn hơn số trang inference vì một crop được liên kết tới nhiều nguồn giống pixel. 370 là ứng viên còn chưa giải quyết theo bộ định tuyến bảo thủ, không phải đã chứng minh cả 370 trang đều bắt buộc VLM.

## Dữ liệu CPT và phần còn thiếu

- Kế thừa đúng **264 mẫu** đã qua cổng cũ và còn an toàn theo routing mới; **29.771 token**, **30 sequence** tối đa 1.024 token, dùng tokenizer Qwen3 của HF export hiện có. Đây chưa phải dữ liệu kiến thức mới từ VLM.
- Giữ **774 trang trong Review Queue**, gồm vùng chưa xử lý, cần duyệt, nguồn còn cờ chất lượng và phần vượt ngân sách. 318 trang hoãn VLM là một tập con, không phải toàn bộ queue.
- 264 trang CPT + 774 trang review + 22 trang non-content = 1.060 trang; ba nhóm không chồng nhau.
- Toàn bộ token nguồn và EOS được bảo toàn; có metadata/source-map, không chat template, không validation/test độc lập từ cùng một PDF.
- `all_pdf_content_complete=false`. Không train trực tiếp từ các crop/prediction chưa duyệt hoặc từ danh sách source page đang hoãn.

## Cách thực hiện 8 bước

1. **PDF → Native + Layout:** dùng lớp PyMuPDF đã trích nguồn và cache layout cũ có ràng buộc SHA PDF/ảnh. Đợt này không chạy lại 1.060 lượt layout inference. PDF được kiểm tra hash/số trang và ảnh được kiểm tra SHA. Cache thiếu có thể chạy CPU bằng --detect-missing, nếu không phải review.
2. **Xác định vùng kiến thức:** nhãn formula/table/image/chart, math native và fallback vector. Bổ sung math native giúp không phụ thuộc hoàn toàn vào detector công thức; code vẫn giữ chữ native.
3. **Logo/nền/trùng:** lọc lề dựa cả hình học và nhãn; tái sử dụng non-content annotation nguồn; loại nền vector tô code khỏi VLM; exact hash pixel trước resize, không xóa gần trùng theo cảm giác. Một số ảnh minh họa/cover được đối chiếu có ghi source-bound routing annotation. Những hình chưa rõ vẫn tồn tại trong queue.
4. **Route:** text/code → PyMuPDF; formula → PP-FormulaNet-S; table → TableRecognitionPipelineV2 với native cell text; diagram/graph/chart ứng viên → Qwen2.5-VL-3B. Bảng thiếu chữ native vào review/OCR riêng, không tự chuyển sang VLM.
5. **Crop/resolution:** padding 8 px, lưu bbox và cả hash trước/sau tối ưu. VLM tối đa cạnh 1.024 px, khoảng 768 visual token. Nhãn quá nhỏ có thể cần crop/độ phân giải khác; chưa xác nhận chính xác bằng model ở đây.
6. **Batch:** batch 2, nhóm theo tỷ lệ/kích thước, FP16, SDPA, padding trái, max_new_tokens=1024. Chưa đo tốc độ và VRAM cấu hình mới trên Colab; không lấy tốc độ 30 giây/trang cũ nhân hoặc chia batch rồi coi là số đo.
7. **Cache:** input hash + pixel gốc + phiên bản model/prompt/schema/worker + cấu hình + native table text. Cache chung trên Drive, kiểm tra cấu trúc trước tái sử dụng. Wrapper Markdown có thể bỏ khi JSON đầy đủ, có lưu dấu phục hồi; nội dung cắt dở không tự sửa.
8. **Validate:** node ID phải duy nhất, cạnh phải tham chiếu node tồn tại, kiểu hướng/trọng số hợp lệ, không NaN/Infinity, có HTML cell và LaTeX cơ bản. Passing structure vẫn semantic_verified=false. Chỉ baseline đã lọc và transcript có review ràng buộc hash được đóng CPT.

## Những sửa lỗi phát hiện qua xem crop

- Một footer logo ở trang 112 vượt nhẹ ngưỡng lề cũ, bị coi nhầm là ảnh body. Đã sửa quy tắc vị trí/kích thước; native heading vẫn giữ nguyên.
- Một số khung màu của mã nguồn tạo nhiều rectangle vector, bị coi là graph. Đã bảo vệ toàn vùng algorithm khi có native code và nhận diện nền dạng stripe theo dòng; không xóa mã.
- Ảnh chân dung, đồng xu, tem và bìa nhìn thấy trong contact sheet được giữ nguồn và gắn routing review riêng thay vì đoán kiến thức qua VLM. Các annotation này do Codex đối chiếu, không phải gold do người độc lập gán nhãn; không áp dụng nếu hash nguồn khác.

Các vòng v1–v3 là bản nội bộ trước khi sửa những lỗi này. Chỉ dùng notebook/gói v4 được liên kết bên dưới.

## Kiểm định

13 kiểm thử hành vi đã PASS: giới hạn nghiêm ngặt <5%; hoãn phần dư vào review; formula/table không dùng ngân sách VLM; không hợp nhất pixel khác nhau; xử lý Markdown nhưng vẫn chặn schema thiếu; chặn cạnh treo; cache identity/schema; math detector bỏ sót; footer body bị nhận nhầm; không tự đưa graph chỉ đạt cấu trúc vào CPT; cache key cũ khi config đổi; logo cắt ngưỡng lề; vector nền code.

Kiểm định artifact đã PASS: SHA manifest/worker/prompt/schema, tất cả crop upload, config-bound cache key, identity crop trùng trước resize, pixel hash của tất cả crop lưu, CPT/review không chồng, đủ trang nguồn, token/EOS, Python và code cell notebook. Xem [validation.json](runs/it3170_regions_v4/validation.json).

**GPU chưa chạy cấu hình region/batch mới.** PP-FormulaNet-S và Qwen2.5-VL từng chạy được ở đợt cũ, nhưng TableRecognitionPipelineV2 trên crop với native cell text, batch 2 và cấu hình giảm resolution cần được kiểm chứng trên Colab. Chưa có CER/WER, formula accuracy, table structure accuracy hoặc diagram fact precision cho bản này. Không coi compile/unit test là chứng minh inference GPU thành công.

## Kết luận mục tiêu

- Giới hạn vận hành dưới 5% trang được lập lịch VLM: **đạt trong plan**.
- Tự động xử lý đủ kiến thức toàn PDF với VLM dưới 5%: **chưa đạt/chưa chứng minh**.
- Muốn nâng độ phủ mà giữ ngân sách cần thêm native vector/graph parsing, classifier vùng chuyên biệt, annotation/cache đã xác minh hoặc tiếp tục review. Không nên nới lọc để bỏ các bước/trọng số khác nhau giữa slide.

## Tệp để chạy tiếp

- [Notebook Colab](IT3170_Region_Routing.ipynb).
- [Gói region_input.zip đúng đợt v4](runs/it3170_regions_v4/region_input.zip).
- [Hướng dẫn chạy/merge/review](README.md).
- [Routing report đầy đủ](runs/it3170_regions_v4/routing_report.json).
- [Region inventory](runs/it3170_regions_v4/regions.jsonl), [Review Queue](runs/it3170_regions_v4/review_queue.jsonl), [CPT manifest](runs/it3170_regions_v4/cpt/manifest.json).

Tham khảo API chính thức: [Paddle Table Recognition v2](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/table_recognition_v2.html), [Qwen2.5-VL](https://huggingface.co/docs/transformers/v4.57.6/en/model_doc/qwen2_5_vl).
