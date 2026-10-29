# Phân tích kết quả Base / CPT / SFT / CPT+SFT

Ngày phân tích: 25/10/2026. Input: `D:\Download\four_way_results.zip`.
SHA256: `ef7777cbdbd1fd70e8c4e264647427f605497bf4d3d5bf1b5079754ec02d2345`.

**Đề xuất: ưu tiên nhánh Base → SFT có dữ liệu tốt hơn và ngữ cảnh lý thuyết từ retrieval.
Giữ base làm đối chứng. Chưa đưa adapter nào trong lần chạy này vào phục vụ tự động;
tạm dừng đầu tư thêm vào CPT+SFT hiện tại.**

## 1. Phép so sánh có nhất quán không?

Có, trong phạm vi các bản ghi được trả về:

- Đã đối chiếu hash, identity và tính lại điểm của160 mẫu MCQ:4 bản ×40 câu.
- Cả48 đầu ra trong blind review khớp các sample đã băm và đúng ngữ cảnh tham chiếu.
- Cùng base Qwen/Qwen3-1.7B revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`, NF4 double quant,
  FP16, Tesla T4, greedy, tắt thinking, cùng phiên bản thư viện và cùng input manifest.
- Hash adapter CPT/CPT+SFT khớp hai adapter đã đóng gói. Adapter SFT-only khớp artifact vừa train;
 392 tensor/8.716.288 tham số đều hữu hạn.
- Mã train SFT-only, cấu hình1epoch/LR2e-5/seed42/batch1/accumulation8 khớp bản đã chuẩn bị;
  provenance ghi fresh LoRA từ base, không nạp tensor CPT. Chọn checkpoint theo validation.
- Kết quả ZIP chỉ mang một phần file của run train SFT-only theo thiết kế packer: tokenizer,
  README, pip-freeze và training_args.bin không có trong ZIP này. Đây không phải lỗi mất
  sample benchmark; các hash của file train thực sự có mặt và hai file adapter đều khớp.

Đây là kiểm tra artifact và tái tính điểm offline, không phải chạy lại model trên GPU.
Chi tiết có trong `AUDIT.json`.

## 2. Số đo gốc, giữ nguyên cách chấm

| Bản | Test NLL ↓ | PPL ↓ | MCQ khớp đáp án nguồn và đúng format | MCQ sai format | Quiz JSON hợp lệ | Quiz qua schema + trích dẫn | tokens/s |
|---|---:|---:|---:|---:|---:|---:|---:|
| Base | 0,7575 | 2,133 | 20/40 =50% | 0/40 | 2/12 | 0/12 | 12,60 |
| CPT | 0,4869 | 1,627 | 8/40 =20% | 20/40 | 4/12 | 0/12 | 8,05 |
| SFT-only | 0,3565 | 1,428 | 18/40 =45% | 4/40 | 6/12 | **4/12** | 8,13 |
| CPT+SFT | **0,2549** | **1,290** | 1/40 =2,5% | **39/40** | 7/12 | 2/12 | 8,37 |

MCQ ở đây là closed-book: chỉ thấy câu hỏi và các phương án, phải trả đúng một JSON
`correct_labels`. Đây không phải expert accuracy. Quiz generation là một tác vụ khác:
model đã được thấy câu hỏi và đáp án nguồn trong ngữ cảnh.

Khoảng Wilson95% của MCQ strict: Base35,2–64,8%; SFT30,7–60,2%.
Base thắng SFT ở3 câu, SFT thắng base ở1 câu; McNemar exact p=0,625, chưa có bằng chứng
SFT làm tăng hoặc giảm khả năng làm MCQ một cách chắc chắn trên bộ nhỏ này.
Điểm quiz4/12 so với2/12 cũng chưa đủ để khẳng định ưu thế thống kê bền vững.

Tốc độ trung bình gộp cả câu ngắn/dài; warmup và load model không nằm trong tokens/s.
Generation của4 bản cộng lại48,85phút; riêng CPT+SFT19,00phút, SFT12,96phút.
SFT-only train thêm6,17phút. Tổng thời gian thực còn có setup, tải model, warmup và NLL.
Không dùng các số này làm benchmark GGUF hay cam kết tốc độ triển khai.

## 3. Vì sao loss tốt nhất nhưng đầu ra lại kém?

**Loss hiện tại đo khả năng dự đoán token của assistant với chuỗi đáp án đúng có sẵn ở
phía trước. Generation buộc model tiếp tục từ chính token nó vừa sinh.** Ngoài ra ngữ cảnh
NLL đã chứa đáp án nguồn và nhiều token của output là khuôn JSON, câu hỏi, sourceId hoặc
đáp án được chép lại. Loss giảm chưa chứng minh hiểu kiến thức, tự tạo câu hỏi mới hoặc
kiểm soát một chuỗi JSON dài khi tự sinh.

CPT+SFT có NLL thấp hơn SFT ở cả40 câu, nhưng kiểm tra generation lại tệ hơn. Vì vậy không
nên chọn checkpoint/model chỉ theo NLL. Chênh validation–test NLL cũng nhỏ:
SFT0,3411→0,3565, CPT+SFT0,2463→0,2549. Không đủ bằng chứng quy mọi lỗi cho overfitting
hay kết luận model đã quên kiến thức; kết luận chắc hơn là **mục tiêu loss không phản ánh
đầy đủ chất lượng sử dụng và khả năng tuân thủ chỉ dẫn đang có vấn đề**.

### Lỗi định dạng làm méo điểm MCQ

- CPT có19 câu chỉ thiếu dấu `}` cuối; cả40 output MCQ đã kết thúc bằng EOS,
  không phải bị chặn bởi max_new_tokens. Tăng giới hạn token không sửa nguyên nhân này.
- CPT+SFT có32/40 câu chép thêm cụm `dùng nhãn lựa chọn trong câu hỏi` từ system prompt.
  Có output chứa JSON hợp lệ nhưng thêm văn bản hoặc thêm object phía sau.
- Nếu chỉ đọc object JSON đầu tiên để chẩn đoán, CPT+SFT khớp khóa nguồn19/40;
  SFT20/40 trên39 output có object đọc được. **Không thay thế điểm gốc bằng các số này**:
  đây là hậu kiểm có bỏ qua nội dung dư, không phải một lượt benchmark mới.
- SFT1/40 MCQ chạm128tokens vì chuyển sang giải thích bằng văn bản. CPT+SFT0/40 MCQ
  chạm giới hạn, nên mức1/40 chủ yếu phản ánh yêu cầu output strict, không chứng minh
  kiến thức chỉ còn2,5%.

## 4. Đọc nội dung: lỗi vượt ra ngoài JSON

Đã đọc12 nhóm câu hỏi ×4 đầu ra, xem cả schema lỗi và nội dung đọc được. Các ví dụ nổi bật:

| Mẫu | Bản | Quan sát |
|---|---|---|
| `q_f8855879e729fa186ffa` — visual words | CPT+SFT | Lặp5 lựa chọn đều là k-means, đều `correct:true`, trong SINGLE_CHOICE. Explanation chỉ là ID nguồn. |
| `q_b11768515fa6a886cd5b` — ghép cặp đặc trưng | CPT+SFT | Lặp4 phương án giống hệt, tất cả đúng; không tạo được distractor. |
| `q_29bff460b959acfe4731` — PKI | CPT+SFT | Lặp distractor; tự viết câu về tài nguyên mã hóa/xác minh danh bạ rồi đưa chính câu đó vào evidenceQuote dù ngữ cảnh không có. |
| `q_7d4d3f67f83e1945cd46` — địa chỉ logic15bit | SFT | Qua validator nhưng prompt chỉ còn “Hỏi có bao nhiêu bit trong địa chỉ logic:”, làm mất32pages/1KB. Người làm quiz không có đủ dữ kiện. |
| `q_b11768515fa6a886cd5b` — ghép cặp đặc trưng | SFT | Qua validator nhưng explanation chỉ nhắc lại yêu cầu câu hỏi; quote là câu hỏi, không giải thích cơ chế vì sao đáp án đúng. |
| `q_205f3f5c7c5c9cb3aa80` — SSTF | SFT | Sinh lời giải tính khoảng cách sai, chỉ có1 option; không đạt yêu cầu quiz dù lấy đúng đáp án nguồn60. |
| `q_efd89bb157dfb59c16cf` — VirtualBox | CPT+SFT | Qua validator nhưng VDI đúng và “VirtualBox VDI” được gắn sai: có nguy cơ hai phương án cùng ý nghĩa. |
| `q_6b701b05610c7b4299ba` — Sprint | CPT+SFT | Một mẫu tương đối gọn, theo khóa nguồn, đủ cấu trúc; lời giải vẫn nhắc lại đáp án, chưa sâu. |

Các nhận xét trên là đánh giá đọc của trợ lý theo ngữ cảnh và output, không phải chứng nhận
của chuyên gia học phần hoặc một điểm semantic đã được thẩm định.

Nguồn đầu vào cũng còn lỗi: mẫu DoS `q_df8dc5cc73f42cbf0d34` có khóa đáp án bắt đầu bằng
`= 1987 (prime)` thiếu tên biến, trong khi câu hỏi phân biệt r và h. Các đầu ra có mẫu đổi
nhầm thành r=1987. Vì vậy “trang đã hoàn tất trích xuất” chưa đồng nghĩa “mẫu đã đúng học thuật”;
cần kiểm tra cả dữ liệu gốc, không chỉ quy mọi lỗi cho model.

### Bộ chấm hiện tại có giới hạn cần sửa

- Bỏ riêng hàng rào markdown làm JSON đọc được thành11/12 Base,12/12 CPT,11/12 SFT,
  7/12 CPT+SFT; nhưng số qua toàn bộ kiểm tra chỉ0/12,0/12,5/12,2/12.
  Do đó strip ```json không đủ để làm quiz dùng được.
- Sau khi bỏ fence, Base và CPT vẫn có11/12 mẫu thiếu answerCitations.
- Validator hiện cho sourceId khớp kiểu substring trong context. Ví dụ SFT VirtualBox dùng
  `exam_afbb096feaa4b9f1` thay vì ID context đầy đủ có `:q_...` nhưng vẫn qua.
  Nếu buộc ID bằng đúng ID context,4 mẫu SFT strict-valid chỉ còn3. Đây là chẩn đoán thêm,
  không thay đổi bảng điểm gốc.
- Quote nguyên văn không bảo đảm quote chứng minh đáp án hoặc lời giải. Quote chỉ là câu hỏi
  vẫn có thể qua validator. Prompt mất dữ kiện và distractor trùng nghĩa cũng chưa được bắt.
- `grounded_reference_matches=0` ở mọi bản không có nghĩa0 câu đúng: metric chỉ chấm khi
  stem và toàn bộ options trùng reference. Generation tạo distractor khác nên cả12 đều
  không thuộc tập assessable. Cần một phép chấm semantic phù hợp hơn.

## 5. Hướng đi tiếp theo, theo thứ tự ưu tiên

### Bước1 — Tận dụng checkpoint hiện có, chưa train lại

Giữ nguyên bốn adapter và điểm strict làm bằng chứng hồi quy. Dùng Base và SFT-only làm
hai đối chứng chính; CPT/CPT+SFT giữ để chẩn đoán thay vì xóa.

- Tách rõ ba điểm: tuân thủ JSON/schema, khớp đáp án, và chất lượng câu hỏi/lời giải.
- Chạy một lượt kiểm tra nhỏ với structured decoding/grammar để tách lỗi cú pháp khỏi
  lỗi nội dung; cùng cách decode cho tất cả model so sánh. Ép schema không sửa kiến thức.
- Kiểm tra ID context bằng so sánh chính xác, bool thật, đúng số đáp án, option không trùng,
  câu hỏi giữ đủ dữ kiện; quote phải thuộc đúng nguồn và liên quan mệnh đề đang chứng minh.
- Để model chọn evidence_id, sau đó code gắn sourceId và quote nguyên văn từ retrieval.
  Không bắt model gõ lại nhiều chuỗi ID/quote dài. Vẫn phải kiểm tra evidence có hỗ trợ câu trả lời.
- Với MCQ, thêm phép chấm nội dung ít phụ thuộc JSON: giới hạn nhãn hợp lệ hoặc chấm xác suất
  đáp án; kiểm tra đảo lựa chọn cho những câu không phụ thuộc nhãn/thứ tự.

[vLLM Structured Outputs](https://docs.vllm.ai/en/latest/features/structured_outputs/) hỗ trợ ràng buộc
JSON/schema. Đây là một lựa chọn kỹ thuật, không yêu cầu thay runtime Colab đang hoạt động
hoặc cài vLLM ngay. Nên thử riêng trước khi tích hợp.

### Bước2 — Xây SFT-v2 đúng tác vụ “lý thuyết → quiz”

Bộ hiện tại có323/361 mẫu lời giải chỉ dẫn lại đáp án, và prompt yêu cầu giải thích ngắn,
không bổ sung lời giải khi nguồn không có. Huấn luyện lâu hơn không tự tạo được tín hiệu
sư phạm mà dữ liệu chưa cung cấp.

Đề xuất một pilot **300–500 mẫu mới được kiểm tra chất lượng**, như một ngân sách thử nghiệm
ban đầu, không phải ngưỡng bảo đảm thành công:

1. Input là đoạn lý thuyết sạch từ27 giáo trình đã có, đủ căn cứ; không đưa sẵn câu hỏi và khóa đáp án.
2. Output có câu mới, distractor hợp lý; lời giải nêu căn cứ/khái niệm, áp dụng vào câu hỏi và
   phân biệt phương án sai. Không dùng lời giải không kiểm chứng do model tự bịa.
3. Có cả câu phủ định, tình huống, tính toán và nhiều lựa chọn; cân bằng học phần.
4. Thêm mẫu trả lời/giải thích từ ngữ cảnh, tuân thủ định dạng và xử lý thiếu bằng chứng để tránh
   quá hẹp vào một kiểu output. Chỉ dùng nguồn đã hoàn tất, không mở lại OCR/VLM hoặc trang bị loại.
5. Tạo đoạn lý thuyết và chia train/validation/test theo tài liệu/chương/nhóm khái niệm trước
   khi sinh câu; gom biến thể cùng họ về một split.

Ưu tiên thử **Base → SFT-v2**, với lý thuyết được đưa vào prompt qua retrieval/RAG.
So sánh ít cấu hình có kiểm soát (ví dụ1và2epoch sau khi sửa dữ liệu), chọn checkpoint theo
generation trên validation, độ đúng và khả năng tuân thủ; NLL là số đo bổ sung.
Chưa tăng epoch trên361 mẫu cũ rồi kỳ vọng khắc phục mục tiêu tác vụ bị lệch.

### Bước3 — Benchmark mới trước khi chọn model

40 câu hiện tại gồm17OS,13CNPM,7Thị giác,2An ninh,1An toàn;39single-choice và1multi-select.
Chỉ5 học phần có mặt trong test; không đại diện27 giáo trình.

Đề xuất100–200 mẫu test mới có kiểm tra đáp án, bao gồm lý thuyết chưa thấy → câu hỏi mới,
không chỉ làm lại trắc nghiệm có sẵn. Chấm cả độ độc lập/đủ dữ kiện của prompt, chất lượng
distractor và lời giải theo nguồn. Các câu đã dùng phân tích lỗi ở đây trở thành regression/dev;
không tiếp tục tối ưu chúng rồi gọi kết quả đó là test độc lập.

Có thể đặt mục tiêu nội bộ như≥95% schema/evidence-ID hợp lệ và≥90% quiz có đáp án đúng,
đủ dữ kiện, distractor không nhập nhằng sau duyệt nội dung. Đây là tiêu chí đề xuất cho sản phẩm,
không phải chuẩn nghiên cứu, không thay cho khoảng bất định hay độ bao phủ học phần.

### Khi nào quay lại CPT?

Chỉ sau khi nhánh SFT-only đã ổn mà còn thiếu kiến thức miền ở benchmark phù hợp.
Khi đó thử checkpoint CPT sớm hơn, ngân sách token/LR thấp hơn và giữ dữ liệu instruction;
đánh giá generation ở từng giai đoạn thay vì chỉ xem pretraining loss.
Lần thử này chưa chứng minh CPT hiện tại đáng giữ trong đường train chính, nhưng cũng
không chứng minh CPT luôn vô ích. Nghiên cứu [Don't Stop Pretraining](https://arxiv.org/abs/2004.10964)
cho thấy lợi ích có thể có trong các bối cảnh khác; cần kiểm chứng riêng cho Qwen/quiz này.

## 6. Quyết định đề xuất

- **Ưu tiên:** Base → SFT-v2 theo ngữ cảnh lý thuyết, kết hợp retrieval và kiểm tra output bằng code.
- **Đối chứng bắt buộc:** Base nguyên bản; SFT-only hiện tại làm mốc tiến độ.
- **Tạm hoãn:** train thêm trên CPT+SFT hiện tại hoặc tăng quy mô chỉ để giảm loss.
- **Chưa triển khai tự động:**4/12 quiz strict-valid vẫn quá thấp và có lỗi semantic chưa bị chặn.

Không sửa dữ liệu/điểm cũ, chưa chạy thêm GPU, chưa thay model đang phục vụ.
