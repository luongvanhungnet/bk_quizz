# BKQuiz SFT từ ngân hàng đề thi - 24/10/2026

## Kết quả

- Nguồn: `D:\bk_quizz_data\đề thi`; 374 PDF, 7,444 trang, 49 nhóm tên môn.
- Đã đọc native 373 tệp; 1 tệp trang cuộn rất dài hết thời gian trích xuất, giữ trong hàng đợi.
- 3,726 trang native có dưới 80 ký tự không trắng: cần OCR/đối chiếu, chưa dùng làm nhãn SFT.
- 1,673 đoạn câu hỏi có parser hỗ trợ; 622 được cách ly. Những trang khác có trong `pages_review_queue.jsonl`.
- Sau lọc và khử trùng: **742 mẫu**, **8 nhóm môn**. train: 590, validation: 76, test: 76.
- Tập `rationale_core/`: **73 mẫu có giải thích**, train: 55, validation: 10, test: 8. Dùng cho pilot về định dạng, dẫn nguồn và giải thích; lượng dữ liệu còn nhỏ.
- `document_holdout/` giữ một cách chia toàn tài liệu độc lập để đánh giá ngoài tài liệu. Không trộn train của cách chia này với test của cách chia khác.

## Mục tiêu và giới hạn

Model được xác định từ dự án là **Qwen3 1.7B**, tiếp nối CPT 27 môn; xem `MODEL_PROVENANCE.json` để đối chiếu adapter và revision. Chưa huấn luyện, tải model hay thay model đang phục vụ.

Một mẫu gồm ngữ cảnh Q&A tham chiếu đã dẫn trang nguồn và đầu ra quiz JSON tương thích `GroundedQuizOutput` của BKQuiz. Ngữ cảnh được dựng từ câu hỏi và đáp án có sẵn, không chứa các lựa chọn nhiễu gốc. Đây là tác vụ biên soạn/chuẩn hóa ngân hàng Q&A thành quiz theo ngữ cảnh; **chưa phải tập lý thuyết -> câu hỏi hoàn toàn mới**. Không dùng điểm trên tập này để khẳng định năng lực sáng tạo câu hỏi mới từ giáo trình.

Nguồn lời giải: source_answer_attribution: 669; codex_authored_grounded_in_visible_source_answer: 9; codex_authored_grounded_in_source: 62; source_rationale: 2. Phần `source_answer_attribution` chỉ diễn đạt lại khóa đáp án và dẫn nguồn, **không phải lời giải sư phạm chi tiết**. Giải thích do Codex viết được gắn cờ riêng; nội dung dẫn nguồn phái sinh cũng chứa giải thích đó để việc học vẫn dựa trên ngữ cảnh. `human_verified=false`, `expert_semantically_verified=false` được giữ rõ ràng.

Đã phát hiện và loại các lỗi kiến thức rõ ràng trong khóa đáp án gốc (xem audit). Phần còn lại là dữ liệu có đáp án nguồn và kiểm tra cấu trúc, **chưa được chuyên gia xác minh toàn bộ**. Tập đầy đủ thích hợp làm tập ứng viên/pilot; cần rà soát thêm kiến thức trước một lượt train quan trọng. Không tự sửa nhãn hoặc gắn cờ phê duyệt của người dùng.

## Phân chia và rò rỉ

Cách chia mặc định phân tầng theo môn và theo họ câu hỏi: khử trùng chính xác sau chuẩn hóa, nhóm cùng stem, biến thể số liệu và câu gần giống trước chia. `699` họ câu hỏi; `32` cặp gần giống đã nhóm. Không cắt ngẫu nhiên các dòng của tập đã có. Các PDF nguồn có thể xuất hiện ở nhiều split; họ câu hỏi và nội dung trùng không được xuất hiện ở nhiều split. Đây là đánh giá trong miền, không phải đánh giá tài liệu chưa thấy.

`document_holdout/` dùng PDF và thành phần liên thông câu trùng làm đơn vị chia, nên loại hẳn dùng chung PDF giữa train/validation/test. Do nguồn có đáp án phân bố không đều, bộ này lệch môn; số liệu chi tiết ở `document_holdout/build_report.json`.

## Tệp chính

| Tệp | Ý nghĩa |
|---|---|
| `train.messages.jsonl`, `validation.messages.jsonl`, `test.messages.jsonl` | Chat gồm system, user, assistant; mỗi mẫu đúng một dòng JSON UTF-8 |
| `*.metadata.jsonl` | ID, học phần, trang, vùng hình, SHA-256 PDF, nguồn đáp án, nguồn lời giải, nhóm split |
| `tokenized/*.jsonl` | input_ids, attention_mask, labels đã mask assistant-only; không cắt mẫu dài |
| `rationale_core/` | Tập nhỏ có giải thích nguồn hoặc Codex viết có căn cứ; giữ split của tập chính |
| `questions_selected.jsonl` | Câu hỏi sạch cấu trúc trước khi dựng messages, đầy đủ dấu vết nguồn |
| `questions_quarantine.jsonl`, `release_excluded.jsonl` | Câu bị cách ly và lý do; không đưa vào train |
| `pages_review_queue.jsonl`, `source_coverage.jsonl` | Trang cần OCR/đáp án/đối chiếu; phạm vi đã thử cho mọi PDF |
| `audit/` | Lấy mẫu rủi ro, ảnh đối chiếu, phát hiện nhãn sai, lời giải có gắn xuất xứ |
| `release_manifest.json`, `validation_report.json` | Hash tệp và kiểm định cấu trúc/token/nguồn; không chứng minh toàn bộ nhãn đúng kiến thức |

Các trích xuất native đầy đủ nằm tại `extracted/` trên máy, không được chép vào ZIP train để giảm dung lượng. PDF gốc giữ nguyên. ZIP không có trọng số model hoặc tài liệu PDF gốc.

## Tái tạo và kiểm tra

Dùng Python đã có: `D:/BKQuiz/AI/Qwen_cpt_version/data_preprocessing/.venv/Scripts/python.exe`. Trong `D:/BKQuiz`:

```powershell
$py = 'AI/Qwen_cpt_version/data_preprocessing/.venv/Scripts/python.exe'
$data = 'AI/Qweun_sft_version/datasets/sft_exams_20261024'
$tools = 'AI/Qweun_sft_version/data_preparation'
$tokenizer = 'AI/data_preprocessing/training_releases/cpt_27courses_20261023/tokenizer_pinned'
& $py -X utf8 -m unittest discover -s $tools -p 'test_*.py' -v
& $py -X utf8 $tools/prepare_sft.py --dataset $data --tokenizer $tokenizer --max-length 4096 --allow-shared-source-documents
& $py -X utf8 $tools/validate_release.py --dataset $data --tokenizer $tokenizer --verify-sources --allow-shared-source-documents
```

Muốn xử lý lại nguồn: chạy `scan_sources.py --source 'D:/bk_quizz_data/đề thi' --out $data`, rồi `extract_questions.py --dataset $data` và `build_release.py --dataset $data`. Các quyết định loại cụ thể và giải thích có căn cứ được nạp lại từ audit. Nếu đã sửa code/dữ liệu, chạy lại bước tokenizer và tạo manifest trước validation; không tự sửa manifest để che lỗi. Thư mục `tools/` trong ZIP là snapshot mã tương ứng.

Không dùng runtime CPT cũ đọc trường `text` để train các tệp `messages`. Dùng `tokenized/` với collator bảo toàn labels=-100; không ghi đè labels bằng input_ids, không mask EOS theo token ID, không nối các split hay cắt/trộn lại từng dòng. Nếu dùng trainer khác, cần tái kiểm tra chat template, thinking và mask.
