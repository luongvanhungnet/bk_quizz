# Dữ liệu SFT: Qwen7B teacher, lý thuyết → câu hỏi mới

Workspace đang dùng: `D:\BKQuiz\AI\Qweun_sft_version\pedagogical_workspaces\qwen7b_v1_20261025`.

Web duyệt: http://127.0.0.1:8765/sft/pedagogy/

## Bản FAST giới hạn một phiên dưới một giờ

Đã triển khai `teacher_fast_runtime.py`, `package_fast_pedagogy.py` và notebook FAST riêng trong `colab_fast/`.
Notebook và gói dữ liệu cũ giữ nguyên để phiên đang chạy không bị thay đổi.
Mặc định FAST xử lý gói full, `BATCH_SIZE=2`, `MAX_JOBS=None`, `SESSION_MINUTES=55`.
Thời gian tính từ ô cấu hình, bao gồm cài thư viện và tải model; thời gian bạn đăng nhập/mount Drive nằm trước đó.
Runtime dừng mềm trước deadline và notebook có timeout cho các subprocess. Đây là ngân sách mỗi phiên,
không phải cam kết xử lý xong 1.994 tác vụ trong một giờ. Chưa đo throughput GPU thực tế.

FAST gom đầu vào có độ dài gần nhau, padding bên trái và batch generate trên CUDA.
Nếu OOM, giảm batch và thử lại; không chuyển model sang CPU. Tận dụng bản CUDA torch đang hoạt động của Colab,
không tải lại torch mỗi phiên. Giữ mức sinh tối đa và yêu cầu lời giải ba phần như bản cũ.
Tham khảo API: [Transformers batch generation](https://huggingface.co/docs/transformers/v4.57.1/llm_tutorial).

Mọi câu vẫn qua kiểm tra CPU. Kiểm tra hai thứ tự đáp án và critic chỉ chạy cho:
multiple-select, ghép môn liên quan, retrieval <0,2, câu có số/tính toán, và mẫu 10% chọn ổn định theo job hash.
Kết quả được gắn `cpu_only_pending_human` hoặc `model_audited_pending_human` và phải duyệt thủ công.
Không coi câu chỉ kiểm tra CPU là đã qua kiểm tra ngữ nghĩa bằng model. Import và export kiểm tra lại chính sách
theo packet đã đăng ký; không cho gói strict tự chuyển sang chế độ ít kiểm tra hơn.

Mỗi câu có cache riêng trên Drive, draft chờ audit được giữ nhưng chưa xuất. Chạy lại sẽ tiếp tục các lượt còn thiếu.
Mỗi batch cập nhật `pedagogy_checkpoint.zip`; kết thúc phiên có ZIP bất biến và `SESSION_REPORT.json` ghi số generated/blocked/failed.
Log bắt đầu từng phase và heartbeat mỗi 30 giây giúp phân biệt đang sinh với chưa có tác vụ hoàn tất.
Cache FAST riêng, không tự tái dùng hoặc ghi đè cache strict. ZIP strict cũ vẫn nhập được trên cùng web.

Chạy `package_fast_pedagogy.py --workspace ...` để đóng gói; registry packet cũ được giữ lại.
Liên kết Drive FAST nằm trong `FAST_DRIVE_UPLOAD.json`; hash các gói và notebook trong `FAST_COLAB_ASSETS.json`.

Notebook đã tải lên: https://colab.research.google.com/drive/1MeRM85vuMGxJEp3P619AGpd-smywBgvf

Thư mục Drive: https://drive.google.com/drive/folders/1xPje7tzLUT7z3YoB0xm5pIIg8thiBqId

## Dữ liệu đã chuẩn bị

Nguồn là đúng 37.133 bản ghi trong ZIP CPT27 đã huấn luyện, kiểm tra trùng khớp văn bản và ID span với bản đóng gói token thực tế. Chỉ dùng phần train CPT đã được chính sách của chủ dữ liệu chấp nhận; không lấy development/holdout bị bảo vệ. Kiểm tra SHA256 của cả 27 PDF gốc. Chấp nhận mặc định của chủ dữ liệu và người dùng trực tiếp duyệt là hai nguồn khác nhau, được giữ trong metadata.

Lọc văn bản lỗi, đoạn quá ngắn, ký hiệu hỏng, vùng trùng trong trang và dấu hiệu ngân hàng câu hỏi. Kết quả: **2.949 context lý thuyết**, 27 môn. Giữ riêng các cụm gần trùng và toàn bộ khối 8 trang khi chia train/validation/test. Các PDF đã xuất hiện trong CPT; cách chia này không chứng minh tổng quát hóa sang giáo trình chưa thấy.

- **Tác vụ A**: 654/669 câu có lời giải nông có đoạn lý thuyết ứng viên để thử bổ sung lời giải. Teacher chỉ thấy câu hỏi, toàn bộ lựa chọn và lý thuyết; không thấy đáp án đúng có sẵn. Khóa nguồn chỉ dùng đối chiếu sau khi teacher tự giải. 15 câu thiếu căn cứ được ghi trong `blocked_context_jobs.jsonl`, không ép sinh lời giải. Ghép môn có liên quan như IT4653 với thị giác máy tính chỉ là ứng viên tìm kiếm, không phải xác nhận phù hợp ngữ nghĩa.
- **Tác vụ B**: 1.340 tác vụ sinh câu hỏi mới từ lý thuyết; đầu vào không có đề cũ hoặc đáp án. Mỗi môn dự kiến 50 câu với mức hiểu/vận dụng/phân tích và single/multiple choice. IT4272 và IT4812 có 45 vì không có khối test phù hợp; không chuyển dữ liệu train sang test để đủ chỉ tiêu.
- 73 câu cũ đã có lời giải khác được giữ nguyên trong release 742 câu. Không tự coi chúng là kết quả distillation.

## Teacher và lời giải

Dùng [Qwen2.5-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct), revision `a09a35458c702b33eeacc393d103063234e8bc28`, NF4 double quantization, SDPA, CUDA ≥14 GiB. Bản văn bản này không thay cho Qwen2.5-VL dùng OCR trước đây.

Lời giải **công khai cho người học** có ba phần: khái niệm nền tảng; vận dụng để giải thích đáp án đúng; giải thích từng phương án và ngộ nhận của lựa chọn sai. Các phần đều phải trích nguyên văn từ context. Đây là lời giải sư phạm có căn cứ, không yêu cầu lưu suy luận nội bộ của model.

Sau bản nháp, model giải lại hai lần không có đáp án/lời giải trong đầu vào, lần hai đảo thứ tự lựa chọn. Cần cùng đáp án sau ánh xạ. Một lượt critic kiểm tra tính có căn cứ, không mơ hồ và giải thích mọi phương án. Chặn JSON lỗi, đáp án mâu thuẫn khóa nguồn, trích dẫn bịa, lý do nông, lựa chọn trùng và câu mới gần trùng 742 câu cũ (kể cả chỉ thay số).

Các kiểm tra này dùng cùng một Qwen7B nên không phải chuyên gia độc lập hoặc bằng chứng đáp án chắc chắn đúng. Kết quả đạt kiểm tra vẫn **chờ người dùng duyệt**. Không có phê duyệt tự động hoặc dữ liệu giả được đưa vào production.

## Chạy Colab và duyệt

1. Mở notebook trên Drive, chọn T4 hoặc GPU CUDA ≥14 GiB và đăng nhập cùng tài khoản có thư mục dữ liệu. Giữ bốn tệp `BKQuiz_Qwen7B_Pedagogy.ipynb`, `teacher_runtime.zip`, `teacher_pilot.zip`, `teacher_full.zip` trong thư mục `MyDrive/BKQuiz_CPT/SFT_PEDAGOGY_QWEN7B_20261025`.
2. Chạy các cell theo thứ tự. Mặc định `PACKET_KIND='pilot'`, `MAX_JOBS=3`: gồm hai câu mới và một câu bổ sung lời giải. Sau khi xem kết quả, dùng `MAX_JOBS=None` cho toàn bộ 63 tác vụ pilot. Chuyển `PACKET_KIND='full'` khi chất lượng pilot phù hợp. Notebook không tự chạy full hoặc mua tài nguyên.
3. Runtime/input phải khớp hash trong notebook. Không cắt cụt lý thuyết hay đầu ra cho vừa token. Mỗi job được lưu vào Drive; bản cache chỉ tái sử dụng khi hash nội dung, job, nguồn, model và runtime đều đúng. Kết quả bị lỗi CUDA dừng và giữ phần đã chạy. Đặt `RETRY_FAILED=True` để thử lại job lỗi thực thi; bản bị chặn nội dung cần sửa pipeline/prompt trong một snapshot mới.
4. Tải ZIP `pedagogy_results_*.zip` về rồi dùng nút **Nhập ZIP kết quả Colab** trên web. Nhập lại cùng kết quả không tạo bản sao hoặc quyết định duyệt. Log thô và ZIP gốc được giữ. Kết quả không đạt nằm ở bộ lọc **Bị kiểm tra chặn**.
5. Đối chiếu câu hỏi, đáp án, ba phần lời giải và từng trích dẫn với context. Chấp nhận, sửa lời giải, loại hoặc để xem lại. Đổi đáp án cần có lượt giải kiểm tra lại; không sửa nhãn để vượt kiểm tra. Mẫu bị chặn phải sinh lại trước khi chấp nhận.
6. Bấm **Xuất các mẫu đã chấp nhận**. Chỉ lấy phiên bản mới nhất của mỗi job và quyết định duyệt mới nhất. Lịch sử là append-only, tách riêng khỏi quyết định duyệt ảnh/OCR/CPT.

## Bản xuất cho student

Student vẫn là Qwen3-1.7B revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e` tiếp nối adapter CPT27, có SHA256 trong `MODEL_PROVENANCE.json`. Chưa huấn luyện hoặc đổi model phục vụ.

Train chính có **ít nhất 80% câu mới từ lý thuyết**, tối đa 20% câu cũ được bổ sung lời giải, tính bằng số mẫu duy nhất thật. Phần bổ sung dư nằm trong `auxiliary_enrichment.*`, không tự ghép vào train. Nếu chỉ có lời giải câu cũ, train chính tiếp tục chờ câu hỏi mới. Giữ nguyên split nhóm câu hỏi cũ, nhóm trang lý thuyết và lọc câu trùng; không đưa holdout vào train.

Mỗi mẫu gồm system/user/assistant, đầu ra tương thích `questions[].type/prompt/explanation/options/acceptedAnswers/*Citations`. Tokenizer Qwen3 được đối chiếu hash với release cũ, `enable_thinking=False`. Chỉ assistant content và `<|im_end|>` được tính loss; prompt và padding là -100. Mẫu dài hơn 4.096 token bị giữ ngoài tập chính, không cắt.

Khi chưa có mẫu được duyệt cho cả train/validation/test, chỉ xuất báo cáo trạng thái chờ, không tạo ZIP gắn nhãn sẵn sàng huấn luyện. Không nối thẳng release 742 câu cũ vào train mới vì sẽ làm lệch tỷ lệ tác vụ và có thể chồng holdout.

## Lệnh trên Windows

Từ `D:\BKQuiz`, dùng Python có sẵn `AI\data_preprocessing\.venv\Scripts\python.exe`:

```powershell
python -X utf8 AI\Qweun_sft_version\pedagogy_tools\package_pedagogy.py --workspace AI\Qweun_sft_version\pedagogical_workspaces\qwen7b_v1_20261025
python -X utf8 AI\Qweun_sft_version\pedagogy_tools\export_pedagogy.py --workspace AI\Qweun_sft_version\pedagogical_workspaces\qwen7b_v1_20261025
python -X utf8 -m unittest discover -s AI\Qweun_sft_version\pedagogy_tools -p "test_pedagogy*.py"
```

Không sửa input đã đóng băng sau khi teacher chạy. Nếu đổi corpus/model/prompt, tạo snapshot workspace và packet mới, giữ lại registry của packet cũ. Nếu đóng gói lại runtime, phải cập nhật gói và hash tương ứng trên Drive trước khi chạy notebook.

## Đo chất lượng sau SFT

Chạy student trước và sau SFT trên cùng các context test được giữ riêng; người duyệt đánh giá đáp án đúng, có căn cứ, câu mới, độ rõ và chất lượng phương án nhiễu. Đo riêng hai tác vụ, từng môn, single/multiple choice và tỷ lệ teacher bị chặn/loại. Tự đánh giá đồng ý của Qwen không thay thế độ chính xác do người đánh giá. Chưa có kết quả GPU hoặc mức cải thiện student được đo trong lần chuẩn bị này.
