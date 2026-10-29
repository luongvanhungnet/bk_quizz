# Đánh giá Qwen local cho sinh quiz

Đợt chạy: `runs/2026-10-17/`. Các model được phát hiện từ Ollama chính và kho cũ `D:\ollama_models`. Không tải model mới. Bản Qwen3 1.7B trùng digest giữa hai kho được tính một lần; cache Hugging Face Qwen2.5-7B chỉ có tokenizer/config nên không được coi là một model chạy được.

Kết quả: [báo cáo đợt đánh giá](runs/2026-10-17/REPORT.md), [phụ lục chấm toàn bộ câu hỏi](runs/2026-10-17/QUESTION_REVIEWS.md).

## Phạm vi và phương pháp

- Sáu prompt nguồn cố định về Thuật toán ứng dụng: tìm kiếm, truy vết mã, đồ thị, quy hoạch động, tràn số/điều kiện thuật toán, bảng và dữ kiện thiếu.
- Mỗi model có 11 slot tạo câu hỏi và một slot phải từ chối vì không có số liệu thời gian chạy. Câu hỏi yêu cầu bốn lựa chọn, đúng một đáp án, lời giải, ID nguồn và trích dẫn nguyên văn.
- `build_suite.py` tạo và khóa prompt, oracle và rubric **trước** inference. Oracle tính kết quả bằng mô phỏng, liệt kê đường đi/cây khung/tập con và hai cách kiểm chứng LCS. Không chạy code do model sinh ra.
- Cùng messages, temperature=0, seed=42, num_ctx=4096, num_predict=1400, think=false, CPU bốn luồng. Dùng chat template gốc từng model. Không ép JSON bằng grammar/schema của server để còn đo khả năng tuân thủ định dạng.
- `think=false` là cờ yêu cầu, không chứng minh mọi model tắt suy luận: metadata của tag qwen3:4b nhận diện Thinking-2507, biến thể chỉ hỗ trợ thinking theo [model card Qwen](https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507). Điểm của bản này dưới ngân sách chung cần được đọc như kết quả vận hành; chưa phải phép đo năng lực với ngân sách suy luận phù hợp.
- Một lượt/model/prompt, chat mới, không sửa đáp án hay thử lại để nâng điểm. Mỗi model có warm-up riêng không chấm điểm. Chạy tuần tự, giải phóng model sau nhóm test.
- Tự động đo định dạng, cấu trúc, số câu/slot, trích dẫn nguyên văn, từ chối, kết thúc do giới hạn token, độ trễ và token/s.
- Codex đọc từng câu theo đáp án chuẩn và rubric: đúng kiến thức 35%, duy nhất một đáp án 15%, bám nguồn 15%, giải thích 15%, nhiễu 10%, rõ ràng 5%, tuân thủ yêu cầu 5%. Điểm từng chiều và ghi chú được lưu cho từng câu, ràng buộc với hash câu trả lời.
- Packet đánh giá được xáo trộn và ẩn tên model. Codex vẫn theo dõi tiến độ và đã đọc một số output mang nhãn khi kiểm lỗi, nên có thể suy ra danh tính model: **đây không phải chấm mù hay chấm bởi chuyên gia độc lập**. Không gọi một model Qwen tự chấm chính nó.
- Mẫu bị thiếu có điểm 0 trong mẫu số 11 slot/model. Câu trả lời lỗi định dạng được khôi phục để đọc nếu có thể, nhưng không được đổi thành đạt chỉ số JSON strict. Từ chối slot thiếu dữ kiện được đánh giá riêng.

Đây là benchmark nhỏ theo nguồn được cấp, không phải đánh giá tổng quát mọi năng lực Qwen, không phải pipeline RAG đầy đủ, và không đo tác dụng CPT/SFT. Dung lượng, lượng tử hóa và backend khác nhau được ghi rõ; không suy luận mọi khác biệt đều do số tham số hay kiến trúc.

## Tệp dữ liệu

| Tệp trong thư mục run | Vai trò |
|---|---|
| `protocol.json`, `rubric.json` | Cấu hình và quy tắc chấm |
| `prompts.json` | Messages gốc, nguồn, slot, hash cho cả sáu prompt |
| `gold.json` | Đáp án chuẩn và chứng cứ tính toán |
| `inventory.json`, `model_details/` | Tên, digest, lượng tử hóa, template, kho lưu của từng model |
| `responses/Mxx/Pxx.json` | Request và nguyên văn content/thinking, metadata và lỗi nếu có |
| `responses/Mxx/Pxx.stream.jsonl` | Từng chunk thô, kể cả output bị gián đoạn |
| `automatic_checks.json` | Các kiểm tra xác định bằng chương trình |
| `review_packet.json`, `review_packet.md` | Packet đã xáo trộn, ẩn tên model |
| `review_mapping.json` | Ánh xạ question ID về model/request |
| `reviews.json` | Điểm và nhận xét Codex cho từng câu có output |
| `question_scores.json` | Điểm từng slot, gồm cả câu thiếu |
| `summary.json`, `summary.csv` | So sánh model |
| `REPORT.md` | Báo cáo Markdown của đợt đánh giá |

## Chạy lại

Python 3.11+, dùng thư viện chuẩn, không cần cài framework inference Python:

```powershell
python .\build_suite.py
python -u .\run_benchmark.py
python .\evaluate.py prepare
# Đọc packet và nhập/kiểm tra reviews.json theo rubric; không tự điền điểm chưa chấm.
python .\evaluate.py score
python .\validate.py
python .\report.py
python -m unittest discover -s . -p test_evaluation.py -v
```

Chạy trong thư mục này. Model được phục vụ bằng Ollama local đang cài. Server phụ cổng 11435 đọc kho D với `OLLAMA_NOPRUNE=true`, `OLLAMA_NO_CLOUD=true` và được tắt sau chạy. Ollama chính không bị tắt hay đổi cấu hình. Lượt chấm không có retry; chạy lại script chỉ tiếp tục các request chưa có artifact. Muốn một đợt độc lập, đổi thư mục `RUN` trong mã trước khi tạo suite, không ghi đè câu trả lời rồi tái sử dụng điểm cũ.

Tham khảo API chính thức: [Ollama chat](https://docs.ollama.com/api/chat), [tham số model](https://docs.ollama.com/modelfile).
