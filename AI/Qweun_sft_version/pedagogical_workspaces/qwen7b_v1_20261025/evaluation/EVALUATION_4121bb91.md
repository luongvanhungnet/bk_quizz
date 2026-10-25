# Đánh giá kết quả Colab 4121bb91

Ngày đánh giá: 25/10/2026. Đọc toàn bộ 7 kết quả và đối chiếu với context thực tế của từng job. Đây là đánh giá nội dung của trợ lý, không phải bộ đáp án chuyên gia đã được xác minh độc lập.

## Kết luận

**Chưa đạt điều kiện làm dữ liệu SFT. Có 0/7 câu sử dụng được trực tiếp.** Cả 7 bị chặn từ giai đoạn bản nháp, chưa có câu nào đi đến lượt giải lại hoặc critic. Cơ chế chặn đang bảo vệ dữ liệu, nhưng bộ sinh hiện tại chưa tạo được mẫu đạt chuẩn trong lần chạy này. Không nên mở rộng chạy 1.994 tác vụ với cùng cấu hình trước khi sửa và đo lại trên nhóm nhỏ.

Số 0/7 là tỷ lệ vượt kiểm tra của gói này, không phải khẳng định teacher có độ chính xác 0% trên tất cả 27 môn. Hàng đợi FAST ưu tiên context ngắn; 7 mẫu không phải mẫu ngẫu nhiên đại diện cho toàn bộ corpus.

## Nguồn gốc và tính toàn vẹn

- Tệp: `D:\Download\pedagogy_results_4121bb91e2e6b31a96e1.zip`.
- SHA256: `740a99e8ec099afced28b45bf85647f68ab644d2210293607452e31cb2c10555`.
- Packet đã đăng ký: `packet_c6f61b023d8ff117c75562fa`, gói FAST full 1.994 tác vụ.
- Kiểm tra đúng hash results.jsonl, packet manifest, result từng job, phiên bản teacher và hash runtime theo packet; không thấy sai khác.
- Hash đầu vào generation của cả 7 mẫu khớp `fast_draft_messages` với context đúng của từng job, bao gồm hướng dẫn FAST mới.
- Metadata ghi teacher Qwen2.5-7B-Instruct revision `a09a35458c702b33eeacc393d103063234e8bc28`, NF4, Tesla T4, torch2.11.0+cu130, Python3.13.17 và `torch.bfloat16`.
- Cả 7 thuộc tác vụ theory_to_quiz, 7 môn khác nhau; train5, validation1, test1. Gói này không cung cấp bằng chứng về năng lực bổ sung lời giải cho 669 câu cũ.
- Không sửa, tự chấp nhận hoặc tự đưa các câu vào tập train khi đánh giá.

## Kiểm tra kỹ thuật

| Chỉ số | Kết quả |
|---|---:|
| Kết quả có trong ZIP | 7 |
| JSON đọc được | 5/7 |
| Generated sau kiểm tra CPU | 0/7 |
| Blocked | 7/7 |
| Có lượt giải lại / critic | 0/7 |

Lỗi đầu tiên chặn mỗi mẫu:

| Lỗi | Số mẫu |
|---|---:|
| Thiếu citations | 2 |
| Trích dẫn không khớp nguyên văn | 2 |
| SINGLE_CHOICE có nhiều đáp án đúng | 1 |
| JSON thiếu dấu phẩy | 1 |
| JSON có escape LaTeX không hợp lệ | 1 |

Đây là thống kê lỗi đầu tiên, không phải tất cả lỗi của từng câu. Qua 5 JSON đọc được, có 30 phần giải thích cần dẫn chứng (concept, application và 4 options mỗi câu): **23 phần thiếu citations**. Có 7 trích dẫn được cung cấp nhưng **0/7 khớp nguyên văn** theo giao thức hiện tại. Trong đó **5/7 khớp sau khi chuẩn hóa khoảng trắng/xuống dòng**, nên cần phân biệt lỗi bố cục với trích dẫn bịa. Điều này không cứu được các mẫu vì vẫn có thiếu dẫn chứng và lỗi nội dung khác.

## Đánh giá từng câu

| # | Môn, trang PDF | Nhận xét và hướng xử lý |
|---|---|---|
| 1 | IT3170,120 — quay lui | Có đủ ba phần lời giải nhưng citations rỗng. Các phát biểu về nhánh, trạng thái và tên lá khá mơ hồ; giải thích nhiều chỗ nhắc lại lựa chọn. Nguồn chỉ có sơ đồ thủ tục Try, không đủ để khẳng định mọi lá đều biểu diễn lời giải hoàn chỉnh. Nên sinh lại với bài toán/trạng thái cụ thể. |
| 2 | IT3323,288 — activation record | Khai báo SINGLE_CHOICE nhưng đánh dấu A,B,C đều đúng và đề yêu cầu chọn tất cả. Không đạt blueprint analyze/hard; chủ yếu hỏi nhớ thành phần. Trích dẫn và nguồn có lỗi OCR, phân tích từng phương án thiếu citations. Đổi type đơn thuần chưa giải quyết yêu cầu ban đầu; cần thiết kế lại câu. |
| 3 | IT4060,120 — WSAEventSelect | JSON thiếu dấu phẩy. Quan trọng hơn, lời giải tuyên bố hàm không tự chuyển socket sang non-blocking trong khi nguồn nói có; đánh sai phương án D. Đây là lỗi kiến thức, không phải chỉ sửa cú pháp JSON. Cần loại hoặc sinh lại. |
| 4 | IT4410,352 — đánh giá HCI | Trích dẫn bị nối dòng, khớp khi chuẩn hóa whitespace; bộ so khớp nguyên văn đang chặn lỗi hình thức này. Nhưng đáp án B tự thêm lý do 'không thể dự đoán kết quả kiểm thử trước khi triển khai', không được nguồn chứng minh. Nguồn nói cần phương pháp phân tích/phi hình thức chứ không cung cấp nguyên nhân model chọn. Không nên duyệt chỉ sau khi sửa quote. |
| 5 | IT4593,344 — nhiễu xuyên ký hiệu | Context công thức đã vỡ dòng/ký hiệu, có cận n=-8 và các mảnh X,T00,2. Model biến các mảnh OCR thành công thức đáp án chắc chắn; lời giải dùng khái niệm mơ hồ như 'tổng tích chéo', các phương án phụ thuộc ký hiệu chưa được xác định rõ. Chưa đủ căn cứ xác nhận đúng; cần đối chiếu PDF và trích xuất lại nguồn trước. |
| 6 | IT4788,176 — Flutter widget | Leaf và child không loại trừ nhau trong cây được nêu: Text có thể là lá đồng thời là con của Column. Lời giải 'là leaf nên không phải child' sai về quan hệ cây. A(top-level) và C(root) cũng gần trùng ý. Dù bổ sung citations, câu vẫn cần thiết kế lại lựa chọn. |
| 7 | IT4906,208 — EPSO | JSON có escape không hợp lệ. Nguồn cho phép learning parameters cố định hoặc thay đổi động, nhưng model đánh phương án cố định là sai và tự thêm điều kiện dựa trên hiệu suất từng vòng lặp. Sai căn cứ, trộn Việt/Anh; không thể cứu chỉ bằng sửa escape. |

Lỗi Winsock được đối chiếu thêm với [Microsoft Learn — WSAEventSelect](https://learn.microsoft.com/en-us/windows/win32/api/winsock2/nf-winsock2-wsaeventselect): hàm tự đặt socket sang nonblocking bất kể lNetworkEvents. Chi tiết này cũng đã hiện ngay trong context của job3.

## Lời giải sư phạm và tác vụ mới

Điểm tích cực: 5 JSON đọc được có chia concept/application/options, tạo câu hỏi từ lý thuyết thay vì chỉ biên tập đề thi cũ; các lựa chọn có phân tích bằng văn bản.

Tuy nhiên, cấu trúc ba phần chưa đồng nghĩa lời giải sâu. Nhiều đoạn chỉ khẳng định lại lựa chọn, có giải thích sai hoặc thêm nguyên nhân không được nguồn hỗ trợ. Các mức Bloom và difficulty ghi trong blueprint chưa được đáp ứng đáng tin: câu gắn analyze/hard vẫn chỉ hỏi nhớ lại định nghĩa/thành phần. Chưa có ví dụ đủ tốt chứng minh đã khắc phục hai hạn chế ban đầu của tập quiz.

## Hiệu năng

Không cộng batch_seconds theo từng hàng vì các hàng cùng batch dùng chung thời gian. Có 4 batch phân biệt theo phase, seed và thời gian:

| Batch | Kết quả đã xuất trong batch | Thời gian |
|---|---|---:|
| 1 | Câu1 và6 | 433,983giây (~7,23phút) |
| 2 | Câu2; metadata khai báo batch2 | 812,738giây (~13,55phút) |
| 3 | Câu3 và7 | 496,390giây (~8,27phút) |
| 4 | Câu4 và5 | 538,716giây (~8,98phút) |

Tổng thời gian 4 batch được ghi: **2.281,827giây, khoảng38phút**. Đây không phải thời gian toàn phiên: không có log kết thúc/model-load/tác vụ dở dang đầy đủ trong ZIP. Batch2 khai báo2 đầu vào nhưng chỉ có1 kết quả được xuất, nên không suy diễn kết quả còn lại đã thành công hoặc bị mất.

Tất cả chỉ chạy phase draft. Vì vậy tốc độ thấp trong gói này chưa do hai lượt giải lại/critic; nút thắt đã ở sinh bản nháp. Số câu dùng được trên thời gian GPU hiện bằng0 trong mẫu đã đánh giá.

### Nghi vấn dtype đã xác minh trong cấu hình

Runtime tôi chuẩn bị dùng `torch.cuda.is_bf16_supported()` để chọn dtype. [PyTorch2.11 source](https://raw.githubusercontent.com/pytorch/pytorch/v2.11.0/torch/cuda/__init__.py) mặc định `including_emulation=True`; vì thế True không có nghĩa hỗ trợ nativeBF16. [NVIDIA](https://developer.nvidia.com/cuda/gpus) liệt kê T4 ở compute capability7.5, trong khi nhánh nativeBF16 của hàm yêu cầu major>=8. Metadata gói này xác nhận đã chọn bfloat16.

Đây là lỗi chọn cấu hình hiệu năng trong runtime, cần sửa sang FP16 trên T4 hoặc kiểm tra nativeBF16 với `including_emulation=False`. Chưa có phép đo A/B nên chưa thể khẳng định đây là nguyên nhân duy nhất hoặc hứa mức tăng tốc cụ thể. Batch1/batch2 cũng cần so trên cùng prompt và cùng dtype, vì batch2 chưa chứng minh hiệu quả ở log này.

## Ưu tiên cải thiện trước lần chạy tiếp

1. Sửa lựa chọn dtype cho T4 và benchmark có đối chứng FP16, batch1/batch2 trên cùng vài context sạch; báo cả thời gian và số câu thực sự đạt.
2. Ràng buộc schema ở bước giải mã thay vì chỉ nhắc bằng prompt: type/label/correct/citations bắt buộc, escape JSON hợp lệ. Sửa cú pháp không được tự sửa đáp án hoặc được xem như đã xác minh kiến thức.
3. Cung cấp các evidence span có ID đã chọn từ nguồn, để model tham chiếu; ghép lại quote nguyên văn ở CPU. Có thể nhận diện khớp chỉ khác whitespace nhưng phải ánh xạ về đúng span nguồn, không bỏ kiểm tra căn cứ.
4. Loại context OCR/công thức hỏng và trang quá thiếu nội dung trước khi sinh. Ưu tiên context sạch, đủ nguyên lý và giả định, thay vì chỉ ưu tiên ngắn nhất.
5. Kiểm tra tính loại trừ của phương án, số đáp án đúng, căn cứ thực sự và độ sâu lời giải. Với mức lỗi đang thấy, chưa có cơ sở coi 10% kiểm tra model là đã được hiệu chuẩn đủ tốt; cần một pilot sạch đạt chất lượng trước khi mở rộng.

Đánh giá này chỉ đọc và lập báo cáo; không thay đổi notebook, runtime, chính sách duyệt hoặc quyết định chấp nhận dữ liệu.
