# BKQuiz · SFT-v2 từ lý thuyết native

Chạy ba notebook theo thứ tự **01 →02 →03**, mỗi notebook chọn **T4 GPU →Run all**.
ZIP input tương ứng đã nằm cùng thư mục trên Drive. Người dùng tự chạy Colab.

| Notebook | Thực hiện | Kết quả tải về |
|---|---|---|
| `01_Diagnose_Schema_4Models.ipynb` | Nạp riêng Base/CPT/SFT/CPT+SFT hiện có, sinh với JSON schema; so sánh raw và schema bằng cùng kiểm tra sourceId chính xác. Không train lại. | `schema_diagnostics_results.zip` |
| `02_Train_Base_SFTv2_RAG.ipynb` | Fresh LoRA từ base Qwen3-1.7B,270train/30validation; chọn checkpoint bằng generation validation; thử RAG trên source train. | `sft_v2_adapter.zip` |
| `03_Independent_Test_100.ipynb` | Đánh giá Base và SFT-v2 trên100MCQ+100quiz mỗi bản, không dùng để chọn checkpoint. | `sft_v2_final_test_results.zip` |

Notebook01 độc lập với02; notebook03 cần02 chạy hoàn tất trước.
Giữ `RUN_NAME` để tiếp tục cache/checkpoint. Khi đổi cấu hình dùng tên run mới.
Notebook02 có `EPOCHS=1`, có thể thử2với run mới; notebook03 phải trỏ đúng `TRAIN_RUN_NAME`
của run đã chọn từ validation. Không nhìn điểm test rồi chọn lại epoch/checkpoint.

Notebook03 mặc định batch2và chạy đầy đủ100quiz, có thể mất vài giờ trên T4.
Có thể chọn batch4nếu đủ VRAM. Nếu chỉ muốn smoke20/50quiz, đổi `GENERATION_LIMIT` và run name;
MCQ vẫn100, báo cáo quiz giữ đúng mẫu số thực tế. Không có cam kết cả ba notebook chạy dưới1h.

## Dữ liệu được triển khai

- **300mẫu phát triển:**270train gồm243mẫu theory→quiz,14QA có nguồn,13MCQ giữ định dạng;
  30validation chỉ dùng theory→quiz.
- **100mẫu test riêng:**62họ fact; không chứa trong ZIP train.85/100mẫu từ hai PDF chưa dùng
  trong SFT-v2 (IT3100 vàIT4788),15mẫu từ các nhóm trang giữ lại của IT4060.
- Tổng cộng13học phần có mặt; không đại diện đầy đủ27giáo trình. Các nguồn khác không được
  đưa vào pilot khi thiếu đoạn native/thuật ngữ/nhóm distractor phù hợp.
- Có ba kiểu câu: mô tả→khái niệm, khái niệm→mô tả, ghép hai mô tả→chọn hai khái niệm.
  Dùng bốn phương án kiểm soát từ cùng học phần; chưa phải sinh tình huống mở hoặc tự tìm
  mọi distractor từ đầu.
- Lời giải gồm căn cứ, áp dụng và đối chiếu từng phương án sai, đều có evidence ID.
- Chỉ dùng span text native nguyên văn từ corpus CPT đã hoàn tất; không chạy OCR/VLM/teacher7B.
  Có danh sách thuật ngữ được biên tập và80span bị cách ly sau đọc nội dung; biến thể lặp của
  các định nghĩa đã bị loại cũng bị chặn.

`human_verified=false` và `expert_semantically_verified=false` được giữ đúng. Đáp án tham chiếu
được kiểm tra bằng ánh xạ nguồn và cấu trúc; chưa có chứng nhận chuyên gia. Các mẫu biến thể
cùng fact/nhóm nguồn cùng split; thống kê test có gom cụm theo tài liệu, không coi100câu hoàn
toàn độc lập. Test chỉ phủ3học phần.

CPT cũ đã học27PDF. Bộ test này độc lập với **SFT-v2**, không phải unseen-CPT.
40câu/12quiz cũ trở thành regression/dev ở notebook01.

## Những thay đổi kỹ thuật

- Dùng LM Format Enforcer0.11.3 với Transformers đang pin, giữ NF4/FP16 trênT4.
  Bộ chấm bắt bool giả, lặp phương án, số đáp án sai, thiếu dữ kiện, evidence ID không tồn tại
  hoặc trỏ sai fact. Không sửa JSON hỏng rồi thay điểm raw cũ.
- Model chỉ chọn evidence ID; `hydrate()` của code gắn sourceId và quote chính xác.
  Quote có thật chưa chứng minh toàn bộ lời giải đúng về học thuật.
- LoRA mới r8/alpha16/dropout0,05 từ base pinned; tuyệt đối không nạp CPT vào train SFT-v2.
- Chọn checkpoint qua4mẫu validation generation cố định, cân nhắc đúng đáp án/nguồn/cấu trúc;
  NLL chỉ phá hòa. Đây là proxy nhỏ, không phải chấm chuyên gia.
- RAG CLI dùng SQLite FTS5, mặc định chỉ truy xuất nguồn train. Nguồn thiếu/đầu ra không qua
  proxy sẽ không được xuất thành quiz cho sử dụng. Chưa thay backend hoặc model đang phục vụ.
- Bộ test generation được cấp source cards chuẩn để đo model, chưa đo recall của retrieval.
- Setup Colab dùng bootstrap pip đã sửa, giữ CUDA torch, log đầy đủ, resume có kiểm tra identity.

## Xem và tái kiểm tra trên máy

`preview.html` cho xem toàn bộ câu tham chiếu, nguồn, phần giải thích và target SFT thực tế;
chế độ chỉ đọc, không tự tạo phê duyệt.

Code tại `D:\BKQuiz\AI\Qweun_sft_version\sft_v2_tools`.
Dataset đầy đủ tại `D:\BKQuiz\AI\Qweun_sft_version\datasets\theory_sft_v2_20261025`.
Ba input đã khóa nằm trong các thư mục `diagnostics_input`, `training_input`, `test_input`.
`COLAB_HANDOFF.json` ghi hash ZIP/notebook; `LOCAL_VALIDATION.json` ghi phạm vi kiểm tra.

Khi có các ZIP kết quả thật, phân tích generation và blind review trước khi quyết định triển khai.
Không suy ra chất lượng production từ việc notebook chạy xong hoặc schema hợp lệ.

Tài liệu triển khai: [LM Format Enforcer](https://github.com/noamgat/lm-format-enforcer),
[PEFT LoRA](https://huggingface.co/docs/peft/v0.18.0/package_reference/lora),
[Transformers generation](https://huggingface.co/docs/transformers/v4.57.1/en/main_classes/text_generation).
