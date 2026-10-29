# Trạng thái đối chứng bốn phiên bản — 25/10/2026

ZIP `D:\Download\sft_completed_adapter.zip` là **CPT+SFT**, không phải SFT-only.
Trọng số được train tiếp từ adapter CPT27 trên Qwen/Qwen3-1.7B revision
`70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`.

| Phiên bản | Khởi tạo / dữ liệu học thêm | Validation NLL hiện có | PPL exp(NLL) | Test chung40 câu |
|---|---|---:|---:|---|
| Base | Qwen3-1.7B cố định revision | Chưa đo | Chưa đo | Chưa chạy |
| CPT | Base + CPT27 | 0,482753 | 1,6205 | Chưa chạy |
| SFT | Base + fresh LoRA SFT, chưa có checkpoint | Chưa đo | Chưa đo | Chưa chạy |
| CPT+SFT | CPT27 + SFT281 train/40 validation | 0,246297 | 1,2793 | Chưa chạy |

Hai loss hiện có lấy từ cùng lần train của người dùng: đánh giá CPT trước SFT và
đánh giá adapter được chọn theo validation sau SFT. NLL giảm **48,98%**.
Đây là mức khớp assistant JSON trong ngữ cảnh Q&A đã chứa đáp án; không phải tăng
accuracy49%, không phải phép đo khả năng tự tạo câu hỏi mới từ giáo trình.
Validation đã dùng chọn checkpoint nên cần test chung để đối chứng cuối.

## Kiểm tra ZIP nhận về

- Tất cả hash trong completed.json khớp dữ liệu ZIP; manifest và4 file runtime khớp release đã khóa.
- Cùng392 tensor LoRA,8.716.288 tham số; tất cả hữu hạn; cả392 tensor thay đổi.
- 1epoch,36steps, checkpoint tốt nhất35; train371,87giây trên T4 FP16.
- Test chưa được yêu cầu và chưa chạy; không có đầu ra generation để chấm chất lượng học thuật.
- MODEL_PROVENANCE.json giữ một cờ chuẩn bị cũ `weights_loaded_or_training_started=false`;
  kết luận train đã hoàn tất dựa trên completed.json, trainer_state, metrics và tensor thực tế thay đổi.
- Adapter mới chứa CPT+SFT hoàn chỉnh: nạp một lần lên base, không chồng lại adapter CPT cũ.

## Bộ so sánh đã chuẩn bị

`BKQuiz_Compare_Base_CPT_SFT_CPTSFT.ipynb` và `bkquiz_four_way_input.zip` là cặp input mới,
không thay dataset hay notebook train trước. Chọn T4 GPU và Run all:

1. Kiểm tra hash,361 mẫu, tokenizer và assistant masks; giữ CUDA torch; bootstrap pip theo cách đã sửa.
2. Train nhánh SFT-only từ base với fresh LoRA, cùng cấu hình/seed/dataset và lựa chọn checkpoint qua validation.
   Không nạp tensor CPT vào nhánh này; test không tham gia lựa chọn.
3. Nạp riêng từng bản vào process GPU mới, cùng NF4 và dtype; đánh giá test40 câu.
4. Xuất `four_way_results.zip` gồm metrics, output/token nguyên văn, blind review, identity và adapter SFT-only.

Mặc định sinh quiz theo ngữ cảnh trên12 câu chọn trước, phủ các học phần có trong test;
đặt GENERATION_COUNT=40 trước lần đầu nếu muốn sinh cả40. NLL và MCQ luôn dùng đủ40.
Khi thay cấu hình phải đổi RUN_NAME; cùng cấu hình có thể tiếp tục cache từng câu.

Các số đo: assistant NLL/PPL, khớp khóa đáp án nguồn khi chỉ thấy câu hỏi + phương án,
tỷ lệ JSON/citations hợp lệ, output chạm giới hạn, token/s và VRAM. Có khoảng tin cậy Wilson
cho khớp đáp án và số câu thắng/thua từng cặp. Không tự chấm semantic quality bằng độ dài lời giải.
Thứ tự phương án MCQ giữ như nguồn, nên vẫn có thiên lệch vị trí.

Test nhỏ, một seed, nhiều PDF cùng nguồn với train; đáp án chưa được chuyên gia xác nhận.
Phép đo này chưa chứng minh năng lực giáo trình → câu hỏi mới/lời giải sâu hoặc hiệu năng GGUF triển khai.
Máy hiện tại không có CUDA: mới chạy kiểm thử CPU/preflight, chưa thực thi notebook GPU.

## Tham chiếu triển khai

Fresh LoRA dùng cùng cấu trúc được mô tả trong [PEFT LoraConfig](https://huggingface.co/docs/peft/v0.18.0/package_reference/lora).
Mọi bản sinh bằng cùng [Transformers GenerationConfig](https://huggingface.co/docs/transformers/v4.57.1/en/main_classes/text_generation), greedy, không sửa đầu ra rồi chấm lại.
