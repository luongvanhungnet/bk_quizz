# Báo cáo các phiên bản tiền xử lý dữ liệu SFT cho BKQuiz

**Ngày lập:** 28/10/2026, múi giờ Asia/Bangkok.  
**Phạm vi:** các snapshot, nhánh thử nghiệm và bản phát hành SFT có hồ sơ tại `D:\BKQuiz\AI\Qweun_sft_version`; các kết quả Colab đã được phân tích đến ngày 26/10/2026.

Báo cáo này trình bày lịch sử phát triển và thay đổi giữa các bộ dữ liệu. Tên phiên bản trong báo cáo dùng đúng thư mục trên đĩa; số thứ tự chỉ phục vụ trình bày, không phải tag phiên bản mới của dự án. Các nhánh có quan hệ kế thừa hoặc chạy song song, không phải mọi hàng bên dưới đều là một bộ dữ liệu mới thay thế hoàn toàn bộ trước.

Số **trang PDF**, **ảnh**, **tác vụ gửi model** và **mẫu SFT** là các đơn vị khác nhau. Một trang có thể tạo nhiều ảnh hoặc nhiều câu; một tác vụ sinh câu có thể bị chặn và không tạo được mẫu train. Dữ liệu CPT chỉ được đề cập trong vai trò nguồn lý thuyết, không được cộng vào số mẫu SFT.

## 1. Bảng tổng hợp

| Mốc | Phiên bản/nhánh | Quy mô tại snapshot | Thay đổi chính | Trạng thái có bằng chứng |
|---|---|---|---|---|
| 1 | `sft_exams_20261024` | 742 mẫu; 590 train / 76 validation / 76 test | Trích đề thi có đáp án, khử trùng, dựng chat và quiz JSON có nguồn | Bộ ứng viên SFT ban đầu |
| 2 | `sft_exams_20261024/rationale_core` | 73 mẫu; 55 / 10 / 8 | Chọn riêng câu có giải thích ngoài việc dẫn lại đáp án | Tập con của 742 mẫu, không cộng thêm |
| 3 | `sft_exams_20261024/document_holdout` | 742 mẫu; 592 / 79 / 71 | Chia lại theo tài liệu và nhóm tài liệu liên thông | Nhánh đánh giá thay thế, cùng ngân hàng câu |
| 4 | `review_workspaces/exams_20261024` | 7.305 ảnh từ 7.231 trang | Bổ sung duyệt ảnh → VLM → duyệt câu hỏi | Hàng đợi xử lý, chưa phải mẫu train |
| 5 | `auto_triage_20261025` và quyết định loại ảnh rủi ro | Hàng đợi thủ công 236 → 138; cuối đợt loại có 138 ảnh rejected | Sàng lọc native/OCR; giảm duyệt tay; sau đó áp dụng yêu cầu loại ảnh rủi ro | Không tự nhập câu đang chờ duyệt vào SFT |
| 6 | `pedagogical_workspaces/qwen7b_v1_20261025` — bản chuẩn | 2.949 context; 1.994 tác vụ; pilot 63 tác vụ | Thử teacher sinh lời giải sâu và câu mới từ lý thuyết | Kế hoạch và pipeline tạo dữ liệu; không phải 1.994 mẫu đã đạt |
| 7 | Cùng workspace, nhánh `colab_fast` | Cùng quy mô tác vụ; gói được đánh giá có 7 đầu ra | Gom batch, giới hạn phiên 55 phút, giảm lượt audit model theo rủi ro | 7/7 đầu ra trong gói được đánh giá bị chặn |
| 8 | `sft_completed_native_20261025` | 361 mẫu; 281 / 40 / 40 | Loại toàn bộ phụ thuộc trang còn cần LLM/VLM/duyệt, giữ câu đã hoàn tất | Đã đóng gói và có kết quả train/so sánh trả về |
| 9 | `theory_v2_20261025` — bản nháp | 650 mẫu; 450 / 50 / 150 | Chuyển sang lý thuyết native → câu hỏi phân biệt khái niệm, kèm QA/MCQ | Snapshot nháp cục bộ, chưa có dấu phát hành |
| 10 | `theory_v2_curated_20261025` — bản phát hành SFT-v2 | 400 mẫu; 270 / 30 / 100 | Siết chất lượng nguồn, phương án cùng môn, tách test khỏi gói train | Đã phát hành, train và nhận kết quả benchmark |

**Quan hệ chính:** bộ đề thi 742 mẫu sinh ra hai nhánh con 73 mẫu và chia theo tài liệu; bộ 361 mẫu là tập con được lọc theo trạng thái trang của bộ 742. Nhánh teacher là một thử nghiệm sinh dữ liệu riêng. SFT-v2 sử dụng lý thuyết native từ corpus giáo trình để đổi tác vụ học, không phải chỉ nối thêm câu vào bộ 361.

## 2. Mốc 1 — Bộ đề thi ban đầu: `sft_exams_20261024`

**Nguồn và mục tiêu.** Đầu vào là thư mục `D:\bk_quizz_data\đề thi`, gồm 374 PDF, 7.444 trang và 49 nhóm tên môn. Tác vụ được dựng là **Q&A tham chiếu có đáp án → quiz JSON có nguồn**, chưa phải đọc giáo trình và tự sáng tạo câu hỏi mới. [S01]

**Những xử lý được hình thành ở phiên bản này:**

- Đọc lớp chữ PDF; dùng parser tương ứng với các dạng đáp án hiển thị của Moodle, biểu mẫu, đáp án chữ cái và các kiểu đánh dấu được hỗ trợ.
- Tách câu hỏi, lựa chọn và khóa đáp án; cách ly trường hợp thiếu khóa, phụ thuộc hình, lựa chọn trùng, ký hiệu hỏng hoặc mâu thuẫn rõ ràng đã phát hiện.
- Trích được 1.673 đoạn câu hỏi: 1.051 ứng viên và 622 đoạn bị cách ly. Từ các ứng viên, loại tiếp 70 trường hợp và khử 239 bản trùng chính xác, còn **742 mẫu**.
- Gom 699 họ câu hỏi và 32 cặp gần giống được nhóm ở mức họ; chia tập theo họ câu hỏi, phân tầng theo môn. Cùng PDF có thể xuất hiện ở nhiều split, nhưng các biến thể cùng họ được giữ cùng split.
- Tạo chat `system/user/assistant`, metadata nguồn và tokenized JSONL; kiểm tra lại tokenizer và loss mask. [S01] [S02]

**Quy mô:** 8 nhóm môn, 590 train / 76 validation / 76 test.

**Hạn chế còn lại:** 669/742 mẫu dùng `source_answer_attribution`, chủ yếu dẫn lại đáp án nguồn. Bộ này mạnh về chuẩn hóa dữ liệu/định dạng hơn là dạy lời giải sư phạm sâu. Đáp án nguồn chưa được chuyên gia xác minh toàn bộ. [S01]

## 3. Mốc 2 — Nhánh lời giải: `rationale_core`

**Thay đổi so với tập chính:** chọn ra **73 mẫu** không thuộc nhóm chỉ dẫn lại đáp án; gồm 62 mẫu Codex viết có căn cứ trong nguồn, 9 mẫu có căn cứ từ đáp án nguồn hiển thị và 2 mẫu có lời giải nguồn. Giữ nguyên split của tập chính: 55 train / 10 validation / 8 test. [S03]

Nhánh này giúp thử việc học giải thích với dữ liệu có tín hiệu rõ hơn, nhưng **không tạo thêm 73 mẫu độc lập ngoài bộ 742**. Các cờ `human_verified=false` và `expert_semantically_verified=false` vẫn được giữ. Quy mô nhỏ và nội dung tập trung vào một số môn; chưa chứng minh chất lượng lời giải chuyên gia.

## 4. Mốc 3 — Nhánh chia theo tài liệu: `document_holdout`

**Thay đổi so với tập chính:** giữ cùng 742 mẫu nhưng thay đơn vị chia tập từ họ câu hỏi sang **toàn bộ tài liệu/nhóm tài liệu liên thông bởi câu trùng**. Số mẫu trở thành 592 train / 79 validation / 71 test. [S04]

Cách chia này phục vụ kiểm tra trên tài liệu chưa dùng trong nhánh train tương ứng. Đổi lại, phân bố môn lệch mạnh: validation chỉ có Công nghệ phần mềm, còn test tập trung vào các môn khác.

Đây là **nhánh chia tập thay thế**, không phải phiên bản có thêm câu. Không được lấy train từ cách chia theo họ rồi dùng test của cách chia theo tài liệu để tuyên bố độc lập.

## 5. Mốc 4 — Luồng mở rộng bằng duyệt hai đợt

**Workspace:** `review_workspaces/exams_20261024`.

**Lý do bổ sung:** phần lớn trang chưa tạo được câu có khóa đáp án đáng tin bằng parser native. Workspace gom trang cần OCR/đối chiếu, câu bị cách ly và các trường hợp bị loại khi dựng SFT để xem xét riêng.

**Thay đổi xử lý:**

1. Đợt 1: hiển thị ảnh nguồn để xác định trang được tiếp tục xử lý hoặc bị loại.
2. Xuất ảnh đủ điều kiện sang Colab để VLM trích chữ/câu hỏi.
3. Nhập kết quả và duyệt đợt 2 ở mức câu hỏi trước khi xuất dữ liệu.
4. Giữ lịch sử duyệt riêng, gắn danh tính tài liệu/trang/vùng ảnh và hash; thay đổi nguồn làm kết quả duyệt cũ cần được kiểm tra lại.

Danh mục có **7.305 ảnh từ 7.231 trang PDF**; 7 trang cuộn dài được chia thành nhiều ảnh nên số ảnh lớn hơn số trang. Bản chuẩn bị ban đầu sử dụng Qwen2.5-VL-7B-Instruct, NF4. [S05]

**Khác biệt quan trọng:** đây là luồng thu hồi dữ liệu chưa đủ điều kiện, không phải một bộ SFT 7.305 mẫu. Release 742 mẫu đã đóng gói được giữ nguyên trong quá trình mở rộng hàng đợi.

## 6. Mốc 5 — Tự động sàng lọc native/OCR và loại ảnh rủi ro

**Thay đổi so với duyệt hai đợt ban đầu:** thêm kiểm tra lớp chữ PDF, OCR tiếng Việt + tiếng Anh, đặc trưng ảnh và bằng chứng footer để giảm lượng ảnh cần người xem.

OCR probe v3 đã xử lý đủ 7.305 ảnh: 2.992 ảnh bỏ qua OCR vì đủ native text, 4.282 trường hợp OCR trả trạng thái `ok`, 31 ứng viên trang trắng. Đây là kết quả bước đo OCR, **không đồng nghĩa 4.282 trang đã tạo được câu đủ điều kiện train**. [S07]

Hai snapshot phân luồng cho thấy hàng đợi thủ công giảm từ 236 xuống **138 ảnh**, đạt mục tiêu dưới 500. Snapshot cuối trước đợt loại ghi: 7.138 ảnh tự chuyển VLM, 4 ảnh giữ quyết định cho phép trước đó, 5 trang lấy TXT và 20 trang trắng. Từ 5 trang TXT tách được 18 câu đang chờ duyệt đợt 2, chưa có câu được tự chấp nhận. [S06]

Sau yêu cầu loại ảnh rủi ro, receipt bulk ghi **132 ảnh được chọn và chuyển trạng thái trong lượt đó**; cộng các ảnh đã bị loại trước đó, trạng thái cuối có **138 ảnh rejected**, không còn ảnh pending của đợt này. Không diễn giải thành 138 quyết định mới trong một lượt. [S08]

**Hạn chế:** trạng thái tự chuyển VLM chỉ là quyền/phân luồng xử lý, không phải VLM đã chạy hoặc tách chữ thành công. Điểm OCR cũng chưa được hiệu chuẩn thành xác suất VLM thất bại. Các bước này không tự bổ sung dữ liệu vào release train.

## 7. Mốc 6 — Teacher Qwen 7B, bản chuẩn

**Workspace có hồ sơ:** `pedagogical_workspaces/qwen7b_20261025` và `qwen7b_v1_20261025`. Hai báo cáo chuẩn bị có cùng thống kê chính; báo cáo này xem chúng là các snapshot của cùng nhánh, không cộng hai lần dữ liệu.

**Mục tiêu thay đổi:** xử lý hai điểm yếu của bộ 742: lời giải nông và tác vụ thiên về biên tập đề cũ.

Nguồn lý thuyết được lấy từ **37.133 bản ghi CPT của 27 giáo trình**, lọc thành 2.949 context. Teacher là **Qwen2.5-7B-Instruct chuyên văn bản**, khác với model VL phục vụ trích ảnh. [S09] [S10]

**Hai nhóm tác vụ:**

- Bổ sung lời giải cho 669 câu có lời giải nông: 654 câu có context ứng viên để thử, 15 câu bị chặn vì thiếu căn cứ. Teacher tự giải từ câu hỏi, lựa chọn và lý thuyết; khóa nguồn chỉ dùng đối chiếu sau đó.
- Sinh câu hỏi mới từ lý thuyết: 1.340 tác vụ, hướng tới nhiều mức độ và single/multiple choice.

Tổng cộng **1.994 tác vụ**, pilot 63 tác vụ. Tác vụ khác với mẫu SFT đã hoàn tất.

**Thay đổi về kiểm tra:** lời giải công khai ba phần — căn cứ/khái niệm, áp dụng, phân tích lựa chọn sai; giải lại hai lượt, một lượt đảo lựa chọn; critic; kiểm tra JSON, trích dẫn, trùng câu và khớp đáp án. Chia lý thuyết theo khối 8 trang và nhóm gần trùng, giữ họ câu hỏi cũ. Thiết kế train chính dự kiến ít nhất 80% câu mới từ lý thuyết, tối đa 20% câu cũ bổ sung lời giải. [S10]

**Trạng thái:** tỷ lệ 80/20 là chính sách xuất dự kiến, không phải tỷ lệ dữ liệu đã tạo. Snapshot `approved_sft/113cb...` có 0 ứng viên được duyệt và trạng thái chờ đủ mẫu train/validation/test; không có bộ train student mới đạt điều kiện từ snapshot này. [S13]

## 8. Mốc 7 — Nhánh teacher FAST

**Thay đổi so với bản chuẩn:** giữ nguồn và số tác vụ, thay cách thực thi để giới hạn chi phí một phiên:

- Gom đầu vào gần độ dài, batch mặc định 2, padding bên trái.
- Ngân sách phiên 55 phút, cache/checkpoint và tiếp tục phần chưa hoàn tất.
- CPU kiểm tra mọi câu; giải lại/critic tập trung vào trường hợp rủi ro và mẫu 10% chọn ổn định.
- Tách nhãn chỉ qua CPU với nhãn đã được model audit; kết quả vẫn chờ người dùng duyệt. [S10] [S11]

**Kết quả đã quan sát:** gói Colab `pedagogy_results_4121bb91...` chứa 7 kết quả sinh câu mới thuộc 7 môn: 5 JSON đọc được, **7/7 bị chặn ở draft, 0/7 dùng trực tiếp**, chưa tới giải lại/critic. Lỗi gồm thiếu nguồn, quote không khớp, sai số đáp án, JSON lỗi và mâu thuẫn kiến thức. [S12]

FAST là **biến thể runtime/kiểm tra**, không phải bộ corpus mới. Ngân sách 55 phút không bảo đảm hoàn thành 1.994 tác vụ trong một giờ. Kết quả 7 câu cũng không đại diện toàn bộ khả năng teacher trên 27 môn.

## 9. Mốc 8 — Bộ chỉ giữ trang đã hoàn tất: `sft_completed_native_20261025`

**Thay đổi chính sách:** theo yêu cầu của chủ dữ liệu, dừng sử dụng các trang còn cần LLM, VLM hoặc duyệt thủ công, chỉ đóng gói phần đã hoàn tất.

**So với bộ 742:**

- Loại 381 mẫu khi bất kỳ nguồn liên quan nào chạm trang trong danh sách loại.
- Giữ **361 mẫu từ 181 trang**, thuộc 8 nhóm môn và 342 họ câu hỏi.
- Giữ nguyên messages, đáp án, lời giải, tokenizer và split cũ của các mẫu còn lại: **281 train / 40 validation / 40 test**.
- Áp dụng danh sách loại 7.305 mục ảnh tương ứng 7.231 trang; không đưa 18 câu TXT đang chờ duyệt hoặc đầu ra teacher vào.
- Kiểm tra lại toàn bộ loss mask và tính nhất quán nguồn; không gọi model mới để viết lại câu. [S14] [S15]

Đây là **lọc tập con**, không phải sinh lại hoặc cải thiện sư phạm toàn bộ. Có 323/361 mẫu vẫn là lời giải dẫn đáp án nguồn. Nhiệm vụ tiếp tục là Q&A tham chiếu → quiz JSON; cùng PDF vẫn có thể nằm ở nhiều split.

Gói này đi kèm notebook tiếp tục adapter CPT27. Sau đó, các artifact Colab trả về đã được dùng đối chiếu Base/CPT/SFT/CPT+SFT. Báo cáo chuẩn bị cũ ghi chưa train tại máy chuẩn bị; trạng thái đó cần phân biệt với bằng chứng train/đánh giá đã trả về sau này. [S21]

## 10. Mốc 9 — SFT-v2 bản nháp: `theory_v2_20261025`

**Thay đổi hướng dữ liệu:** từ đề thi có đáp án sang **lý thuyết native → câu hỏi phân biệt khái niệm có giải thích**, kèm các mẫu QA có nguồn và MCQ giữ định dạng.

Snapshot nháp giữ **450 train / 50 validation / 150 test**, tổng 650 mẫu. Train gồm 400 theory-to-quiz, 25 QA có nguồn và 25 MCQ. Các số split được đối chiếu với manifest và đếm dòng của tệp samples. [S19] [S20]

Nhánh này đã chuyển sang source fact/evidence ID, đầu ra rút gọn và phương án được kiểm soát. Tuy nhiên, cần siết tiếp chất lượng các đoạn định nghĩa và nguồn phương án nhiễu.

**Trạng thái:** thư mục nháp không có `PUBLISHED.json`; bộ kết quả Colab đã phân tích ngày 26/10 khớp bản curated ở mốc sau. Vì vậy, không gán kết quả train của bản curated cho bộ nháp 650 mẫu.

## 11. Mốc 10 — SFT-v2 curated: `theory_v2_curated_20261025`

**Dữ liệu đầy đủ:** `datasets/theory_sft_v2_20261025`.  
**Bản input khóa và đã phát hành:** `sft_v2_releases/theory_v2_curated_20261025`.

**Thay đổi so với bản nháp:**

1. **Siết nguồn:** chỉ lấy span native nguyên văn đã hoàn tất từ corpus giáo trình; loại 24.528 bản ghi không thuộc native hoàn tất và 1.416 bản native đã sửa/redact. Bổ sung danh sách loại biên tập cho định nghĩa không độc lập/sai nhãn, đoạn đứt hoặc lỗi native, phát biểu cần chuyên gia kiểm tra; báo cáo có 80 trường hợp thuộc ba nhóm này và 8 trường hợp lặp định nghĩa đã loại.
2. **Thu hẹp có căn cứ:** giữ 238 source fact; dữ liệu được chọn phủ 13 học phần. Phương án phải có nguồn liên quan từ cùng môn và cùng split; không bù thiếu bằng distractor khác miền chỉ để đủ số lượng.
3. **Đổi cách chống rò rỉ:** chia trước khi dựng câu, theo khối 16 trang và nhóm khái niệm/văn bản trùng; giữ riêng hai tài liệu IT3100 và IT4788 cho test SFT-v2.
4. **Giảm quy mô:** từ 650 xuống **400 mẫu** — 270 train / 30 validation / 100 test. Train gồm **243 theory-to-quiz, 14 QA có nguồn và 13 MCQ**.
5. **Chuẩn hóa đầu ra:** model dùng `evidence_ids`; code gắn lại sourceId và quote nguyên văn. Lời giải có `principle`, `application`, `distractor_explanations`.
6. **Tách gói:** test 100 mẫu không nằm trong input train; manifest và checksum khóa từng gói. [S16] [S17] [S18]

**Phạm vi thực tế:** ba dạng câu là mô tả → thuật ngữ, thuật ngữ → mô tả và ghép hai mô tả → chọn hai khái niệm. Đây là pilot có bốn phương án được kiểm soát, chưa phải tập sinh tình huống/tính toán mở hoặc lời giải sâu được chuyên gia chứng nhận.

Test có 62 họ fact, thuộc 3 học phần. 85/100 mẫu từ hai PDF chưa dùng trong SFT-v2; 15 mẫu từ các nhóm trang giữ lại của IT4060. Corpus CPT cũ đã thấy các PDF này nên tính độc lập chỉ áp dụng đối với SFT-v2.

**Trạng thái huấn luyện và hạn chế sau chạy:** bản curated được dùng train LoRA mới từ Base, khác đường tiếp tục CPT của bộ 361. Kết quả trả về xác nhận chạy đủ 34 step/1 epoch, đúng adapter. Tuy nhiên, Base/SFT-v2 lần lượt đạt 31/100 và 35/100 MCQ; cả hai có 0/100 quiz qua toàn bộ kiểm tra. Đã phát hiện lỗi Unicode/EOS trong lớp grammar cùng các lỗi gắn nguồn và phương án. Đây là kết quả của pipeline đã chạy, chưa phải chứng nhận chất lượng dữ liệu hoặc model. [S22]

## 12. Những thay đổi xuyên suốt cần phân biệt

| Khía cạnh | Bộ đề thi 742 và tập con 361 | Nhánh teacher 7B | SFT-v2 curated |
|---|---|---|---|
| Nguồn chính | Câu hỏi/đáp án từ PDF đề thi | Câu cũ và lý thuyết của 27 giáo trình CPT | Chỉ lý thuyết native được lọc |
| Tác vụ | Biên soạn Q&A thành quiz có nguồn | Bổ sung lời giải và sinh câu mới | Sinh câu phân biệt khái niệm theo ngữ cảnh |
| Cách tạo nhãn | Khóa đáp án nguồn, có giải thích nguồn/Codex được đánh dấu | Model teacher sinh, qua kiểm tra và chờ duyệt | Dựng có kiểm soát từ ánh xạ fact–khái niệm |
| Lời giải | Phần lớn dẫn lại đáp án; nhánh rationale chọn phần tốt hơn | Dự kiến ba phần sư phạm, còn lỗi ở mẫu đã chạy | Ba phần theo căn cứ nguồn, còn tính mẫu/định nghĩa |
| Chia tập | Theo họ câu; có nhánh riêng theo tài liệu | Khối 8 trang, gần trùng và họ câu cũ | Khối 16 trang, nhóm khái niệm/văn bản trùng, hai PDF giữ riêng |
| Duyệt/kiểm chứng | Không mặc định khóa nguồn là expert gold | Qua gate vẫn cần người duyệt | Có kiểm tra máy và biên tập nguồn; chưa có chứng nhận chuyên gia |
| Định dạng | messages + metadata + tokenized JSONL | Job/result/audit, chỉ xuất chat khi đủ điều kiện | facts + samples + messages + tokenized + quiz preview |
| Quan hệ với CPT | Bộ 361 có gói train tiếp CPT | CPT là nguồn lý thuyết, teacher riêng | Nguồn lấy từ corpus CPT; lượt train student mới bắt đầu từ Base |

Các bộ được đóng gói cho student dùng tokenizer Qwen3, chỉ tính loss trên nội dung assistant và EOS; prompt/padding được mask `-100`, không cắt cụt mẫu để vừa giới hạn. Tệp tokenized là biểu diễn số của dữ liệu, **không phải một phiên bản nội dung mới**. [S01] [S10] [S14] [S17]

Các thay đổi notebook như sửa venv/pip, ghi log, chọn FP16/BF16, batch và structured decoding cần được ghi nhận ở runtime. Chúng không tự tạo thêm mẫu SFT. Tương tự, bảng so sánh Base/CPT/SFT/CPT+SFT và phân tích benchmark là hồ sơ đánh giá, không được đếm thành phiên bản tiền xử lý mới.

## 13. Cách sử dụng các hồ sơ hiện có

- Dùng bộ **742** để xem nguồn gốc ngân hàng đề thi, các trường hợp bị loại và hạn chế nhãn/lời giải.
- Dùng bộ **361** để tái lập các thí nghiệm SFT cũ từ phần đã hoàn tất; không diễn giải thành dữ liệu lý thuyết → câu mới.
- Giữ nhánh **teacher chuẩn/FAST** như hồ sơ thử nghiệm tạo dữ liệu. Quy mô job dự kiến không thay cho số mẫu đã duyệt.
- Dùng **SFT-v2 curated** khi đối chiếu lượt train và benchmark mới nhất đã trả về. Bản nháp 650 mẫu được giữ riêng để truy vết.
- Các cờ chưa được người/chuyên gia xác minh không được đổi thành đã xác minh chỉ vì parser, tokenizer hoặc notebook chạy thành công.

## 14. Hồ sơ nguồn

Các liên kết sau trỏ đến tệp thực tế trên máy. Số liệu trong báo cáo là snapshot ghi nhận trong các hồ sơ, không phải truy vấn thời gian thực từ mọi cơ sở dữ liệu duyệt.

| Nguồn | Nội dung |
|---|---|
| [S01] | Dataset card bộ 742: nguồn, nhiệm vụ, giới hạn và định dạng |
| [S02] | Thống kê lọc, khử trùng và chia họ câu của bộ 742 |
| [S03] | Nhánh rationale 73 mẫu |
| [S04] | Nhánh chia theo tài liệu 592/79/71 |
| [S05] | Workspace duyệt hai đợt và danh mục ảnh |
| [S06] | Snapshot phân luồng cuối, 138 ảnh thủ công |
| [S07] | OCR probe v3 trên 7.305 ảnh |
| [S08] | Receipt loại ảnh rủi ro: 132 mục trong lượt, 138 rejected tích lũy |
| [S09] | Chuẩn bị teacher 7B: context và tác vụ |
| [S10] | Thiết kế teacher chuẩn/FAST, quy trình audit và xuất SFT |
| [S11] | Cấu hình giao bản FAST và ngân sách phiên |
| [S12] | Đánh giá 7 đầu ra teacher FAST |
| [S13] | Snapshot xuất teacher chưa có ứng viên được duyệt |
| [S14] | Receipt dựng bộ 361 từ trang hoàn tất |
| [S15] | Kiểm toán độc lập bộ 361 và loại 381 mẫu |
| [S16] | Báo cáo tiền xử lý SFT-v2 curated |
| [S17] | Phạm vi ba gói input/notebook SFT-v2 |
| [S18] | Dấu phát hành bản curated |
| [S19] | Manifest train/validation bản nháp 450/50 |
| [S20] | Manifest test bản nháp 150 |
| [S21] | Phân tích bốn phiên bản model từ bộ SFT cũ |
| [S22] | Phân tích kết quả SFT-v2 và tái hiện lỗi decoder |


[S01]: /D:/BKQuiz/AI/Qweun_sft_version/datasets/sft_exams_20261024/DATASET_CARD.md
[S02]: /D:/BKQuiz/AI/Qweun_sft_version/datasets/sft_exams_20261024/build_report.json
[S03]: /D:/BKQuiz/AI/Qweun_sft_version/datasets/sft_exams_20261024/rationale_core/build_report.json
[S04]: /D:/BKQuiz/AI/Qweun_sft_version/datasets/sft_exams_20261024/document_holdout/build_report.json
[S05]: /D:/BKQuiz/AI/Qweun_sft_version/review_workspaces/exams_20261024/VALIDATION_REPORT.json
[S06]: /D:/BKQuiz/AI/Qweun_sft_version/review_workspaces/exams_20261024/AUTO_TRIAGE_VALIDATION_REPORT.json
[S07]: /D:/BKQuiz/AI/Qweun_sft_version/review_workspaces/exams_20261024/auto_triage_20261025/ocr_report.json
[S08]: /D:/BKQuiz/AI/Qweun_sft_version/review_workspaces/exams_20261024/LATEST_BULK_REJECTION.json
[S09]: /D:/BKQuiz/AI/Qweun_sft_version/pedagogical_workspaces/qwen7b_v1_20261025/PREPARATION_REPORT.json
[S10]: /D:/BKQuiz/AI/Qweun_sft_version/pedagogy_tools/README.md
[S11]: /D:/BKQuiz/AI/Qweun_sft_version/pedagogical_workspaces/qwen7b_v1_20261025/FAST_DELIVERY_STATUS.json
[S12]: /D:/BKQuiz/AI/Qweun_sft_version/pedagogical_workspaces/qwen7b_v1_20261025/evaluation/EVALUATION_4121bb91.md
[S13]: /D:/BKQuiz/AI/Qweun_sft_version/pedagogical_workspaces/qwen7b_v1_20261025/approved_sft/113cb855679b0f0d897b5ec9/build_report.json
[S14]: /D:/BKQuiz/AI/Qweun_sft_version/datasets/sft_completed_native_20261025/DATA_BUILD_RECEIPT.json
[S15]: /D:/BKQuiz/AI/Qweun_sft_version/datasets/sft_completed_native_20261025/COMPLETED_DATA_AUDIT.json
[S16]: /D:/BKQuiz/AI/Qweun_sft_version/datasets/theory_sft_v2_20261025/PREPARATION_REPORT.json
[S17]: /D:/BKQuiz/AI/Qweun_sft_version/sft_v2_releases/theory_v2_curated_20261025/START_HERE.md
[S18]: /D:/BKQuiz/AI/Qweun_sft_version/sft_v2_releases/theory_v2_curated_20261025/PUBLISHED.json
[S19]: /D:/BKQuiz/AI/Qweun_sft_version/sft_v2_releases/theory_v2_20261025/training_input/data/manifest.json
[S20]: /D:/BKQuiz/AI/Qweun_sft_version/sft_v2_releases/theory_v2_20261025/test_input/data/manifest.json
[S21]: /D:/BKQuiz/AI/Qweun_sft_version/model_comparisons/four_way_20261025/returned_analysis/ANALYSIS_VI.md
[S22]: /D:/BKQuiz/AI/Qweun_sft_version/model_comparisons/theory_v2_20261026/returned_analysis/ANALYSIS_VI.md

