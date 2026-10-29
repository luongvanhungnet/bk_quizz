# Train CPT Qwen3 1.7B trên Google Colab Pro

Đã cấu hình cho **Qwen/Qwen3-1.7B**, revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`, dùng đúng dòng model đã chốt. Bản HF này đã qua post-training; không tự chuyển sang `Qwen3-1.7B-Base`. Trọng số GGUF Q4_K_M trong Ollama không phải đầu vào của trainer này. [Model card chính thức](https://huggingface.co/Qwen/Qwen3-1.7B).

Mục tiêu train là dự đoán token tiếp theo trên văn bản học phần, không phải cặp hỏi–đáp. Cách cập nhật mặc định là **QLoRA CPT**: model nền nạp NF4 4-bit và đóng băng, chỉ cập nhật LoRA adapter. Đây không phải full-parameter CPT. Cấu hình này ưu tiên một lượt thử gọn trên Colab trước khi mở rộng dữ liệu.

## 1. Dữ liệu dùng trong đợt này

- Học phần Thuật toán ứng dụng, mã IT3170 được suy ra từ manifest nguồn.
- Một PDF tổng hợp 1.060 trang, **264 mẫu text đã chấp nhận sau khử trùng**, 89.773 ký tự. **753 trang needs_review không vào train**.
- Đầu vào lấy từ `../data_preprocessing/outputs/it3170/cpt/train.jsonl`, kiểm tra đối chiếu metadata theo từng dòng.
- Không đưa ảnh PDF, output OCR chưa xác minh, quiz do model sinh hay file packed Qwen2.5 vào gói train.
- Gói chỉ chứa text đã làm sạch và metadata truy vết rút gọn. Không cần upload cả thư mục tiền xử lý lên Drive.
- Tokenize lại bằng tokenizer Qwen3 tại revision đã khóa; thêm EOS của chính tokenizer. Train không áp dụng chat template. Packing bảo toàn token và đoạn cuối; attention có thể đi qua ranh giới mẫu, có EOS phân cách.
- Giữ nguyên document-group train-only. Validation/test rỗng vì chưa có tài liệu độc lập, không chia ngẫu nhiên trang của hai phiên bản chồng lặp.

Tập này nhỏ: đây là pilot CPT, chưa đủ để hứa model sinh quiz tốt hơn. Số sequence/token thực tế xuất trong cell prepare và `prepared/manifest.json`; số optimizer steps thực tế xem `train/trainer_state.json`.

## 2. Hai tệp cần mang lên Colab

Trong thư mục thiết lập này có sẵn:

1. `Qwen3_1_7B_IT3170_CPT.ipynb`: notebook.
2. `qwen3_it3170_colab.zip`: mã train, dữ liệu và sáu prompt probe; không chứa model weights.

Trên Google Drive tạo thư mục **MyDrive/BKQuiz_CPT**, upload ZIP vào đó. Vào [Google Colab](https://colab.research.google.com/), chọn **File → Upload notebook**, chọn tệp `.ipynb` trên máy. Lưu một bản notebook vào Drive để giữ các thay đổi.

Notebook khóa SHA-256 của ZIP: luôn dùng cặp notebook/ZIP tạo cùng lần. Khi thay dữ liệu hoặc code và chạy lại `build_bundle.py`, cần upload lại cả hai tệp.

## 3. Chọn runtime và chạy từng bước

Chọn **Runtime → Change runtime type → Python 3 → GPU**. Bắt đầu với T4 nếu được cấp; notebook tự chọn FP16 trên T4 hoặc BF16 trên GPU hỗ trợ. Colab Pro không bảo đảm một loại GPU cố định và compute units/thời gian phiên có thể thay đổi. [FAQ Colab](https://research.google.com/colaboratory/faq.html).

Chạy lần lượt:

1. **Mount Drive:** đăng nhập đúng tài khoản, cấp quyền khi Colab yêu cầu.
2. **Giải nén:** ZIP được copy sang `/content` rồi kiểm tra hash; data đọc từ ổ cục bộ của VM.
3. **Cài thư viện và kiểm GPU:** giữ bản PyTorch CUDA của Colab, cài các thư viện còn lại theo phiên bản đã khóa. Trainer yêu cầu PyTorch ≥2.6. Không cần cài Ollama trên Colab.
4. **Prepare:** kiểm tra hash/text/metadata rồi tokenize và packing bằng Qwen3. Xem thống kê được in, không dùng số token của Qwen2.5 để suy ra số bước.
5. **RUN_NAME:** mặc định `it3170_qwen3_1_7b_cpt_001`. Mỗi thí nghiệm khác dùng tên mới.
6. **Smoke test:** chạy 2 optimizer steps để kiểm GPU, loss, backward và lưu checkpoint. Kết quả nằm ở `runs/<RUN_NAME>/smoke/`.
7. **Baseline quiz:** xuất phản hồi của model HF chưa gắn adapter trên sáu prompt cố định.
8. **CPT:** chạy 1 epoch; khởi tạo mới từ model gốc, không lấy adapter smoke để train tiếp.
9. **Sau CPT:** gắn adapter chính thức và xuất cùng sáu prompt để chấm nội dung trước/sau.

Các lệnh model chạy bằng tiến trình Python riêng, nên sau khi mỗi lệnh kết thúc VRAM của tiến trình đó được giải phóng. Không để đồng thời một notebook khác chiếm GPU.

## 4. Cấu hình mặc định

| Tham số | Giá trị |
|---|---:|
| Sequence length | 1.024 |
| Batch trên GPU | 1 |
| Gradient accumulation | 4 |
| Effective batch, 1 GPU | 4 sequence/optimizer step |
| Epoch | 1 |
| Learning rate | 2e-5, constant, không warm-up do số bước rất ít |
| LoRA rank / alpha / dropout | 8 / 16 / 0,05 |
| Target modules | q/k/v/o_proj, gate/up/down_proj |
| Quantization | NF4 + double quantization |
| Optimizer | AdamW, chỉ nhận tham số LoRA |
| Gradient checkpointing | bật, use_reentrant=False |
| Checkpoint | mỗi optimizer step, giữ 2 bản gần nhất |
| Seed | 42 |

Đây là cấu hình khởi đầu được chọn cho tập nhỏ, không phải bộ siêu tham số đã tối ưu. Nếu tăng sequence lên 2.048, cần prepare lại và dùng run mới. Khi OOM, giữ batch=1, giảm sequence length rồi tạo run mới; không lặng lẽ đổi config khi resume.

Không tăng nhiều epoch chỉ để thấy train loss giảm. Loss trên cùng 264 mẫu có thể giảm do ghi nhớ; muốn chọn hyperparameter/checkpoint tốt nhất cần bổ sung tài liệu đánh giá độc lập.

## 5. Khi Colab bị ngắt

Checkpoint/optimizer lưu trực tiếp vào Drive, còn model cache và packed data ở `/content` có thể mất. Sau khi kết nối GPU mới:

1. Chạy lại mount, giải nén, cài thư viện và prepare từ cùng notebook/ZIP.
2. Giữ nguyên `RUN_NAME`.
3. Đặt `RESUME_TRAIN=True`, hoặc `RESUME_SMOKE=True` nếu tiếp tục bước smoke.
4. Chạy lại cell tương ứng. Script chọn checkpoint hoàn chỉnh mới nhất, bỏ qua checkpoint thiếu file do ngắt lúc đang ghi.

Resume kiểm tra model revision, config, dtype FP16/BF16, dữ liệu, mã train và phiên bản thư viện. Nếu Colab cấp GPU có dtype khác đợt cũ, cần runtime cùng dtype để resume theo thiết lập này. Nếu chưa có checkpoint hoàn chỉnh, bắt đầu bằng `RUN_NAME` mới. Nếu đã có `completed.json`, notebook giữ kết quả; không train lặp ngoài ý muốn. Không gọi adapter export là một checkpoint đủ optimizer để resume.

## 6. Kết quả và cách sử dụng

Đầu ra ở **MyDrive/BKQuiz_CPT/runs/<RUN_NAME>/**:

| Tệp/thư mục | Ý nghĩa |
|---|---|
| `train/adapter/` | LoRA adapter và tokenizer; cần model nền đúng revision để suy luận |
| `train/checkpoint-N/` | Adapter, optimizer, scheduler, RNG, Trainer state để resume |
| `train/run_identity.json` | Model/config/hash data/code và phiên bản thư viện |
| `train/environment.json`, `pip-freeze.txt` | GPU, dtype và môi trường thực tế |
| `train/train_results.json` | Chỉ số training |
| `train/train_diagnostic_results.json` | Loss trên chính tập train sau cập nhật; không phải validation |
| `train/completed.json` | Xác nhận script hoàn tất, số bước và vị trí adapter |
| `baseline_quiz.json`, `after_cpt_quiz.json` | Output trước/sau CPT để chấm theo oracle/rubric |

Giữ toàn bộ thư mục `train/adapter`, không chỉ một file trọng số. Notebook có cell **tùy chọn** `EXPORT_MERGED=True` để tạo `merged_hf_fp16/`, cần thêm vài GB RAM/Drive. Script tải lại model nền FP16 rồi merge adapter; không merge trên bản nạp 4-bit. Model xuất vẫn ở định dạng HF, chưa dùng trực tiếp như tag GGUF trong Ollama. [PEFT merge](https://huggingface.co/docs/peft/en/developer_guides/lora).

## 7. Đánh giá trước/sau

Các probe dùng cùng system/user messages của đợt 17/10 và hard switch `enable_thinking=False`. Cả baseline và adapter chạy cùng revision HF, cùng NF4 và cùng decoder greedy để tạo cặp so sánh. Bản GGUF Q4_K_M cũ khác lượng tử hóa/backend nên không dùng làm baseline đối chứng trực tiếp cho phép đo này.

Chấm từng câu theo `probes/gold.json` và `probes/rubric.json`: đáp án được đánh dấu, đúng một lựa chọn đúng, dữ kiện đầy đủ, lập luận, nhiễu, bám nguồn và schema. Script chỉ báo JSON strict và lưu output, không tự khẳng định chất lượng nội dung tăng.

Bộ sáu prompt nhỏ, có kiến thức trùng miền học phần; đây là regression probe chứ không phải held-out test. Prompt gốc có cách viết enum `A|B|C|D`, một hạn chế đã ghi ở báo cáo trước. Giữ nó cố định để so cặp trước/sau; chưa được dùng kết quả này để kết luận model tổng quát tốt hơn hay lựa chọn bản tốt nhất theo test.

CPT text không trực tiếp dạy hợp đồng JSON quiz. Chỉ kết luận có cải thiện sau khi chấm nội dung và dùng thêm tài liệu độc lập; SFT cho định dạng quiz là một giai đoạn khác, chưa thực hiện trong thiết lập này.

## 8. Tái tạo gói trên Windows

Từ `D:\BKQuiz`:

```powershell
python AI/Qwen_cpt_version/colab_qwen3_1_7b/build_bundle.py
python -m unittest discover -s AI/Qwen_cpt_version/colab_qwen3_1_7b -p test_data.py -v
```

`build_bundle.py` chỉ đọc tập accepted đã có, không chạy lại OCR hay đổi dữ liệu tiền xử lý. Tệp token cũ và benchmark gốc được giữ nguyên. Để kiểm tokenizer trên máy Windows cần môi trường có Transformers, còn train yêu cầu GPU Colab.

Thiết lập tham khảo API chính thức: [QLoRA/PEFT](https://huggingface.co/docs/peft/en/developer_guides/quantization), [Trainer](https://huggingface.co/docs/transformers/v4.57.1/en/main_classes/trainer), [Qwen3](https://huggingface.co/Qwen/Qwen3-1.7B). Gói được kiểm tra cấu trúc, packing và tokenizer tại máy local; chưa chạy backward trên GPU Colab của bạn. Cell smoke là bước kiểm chứng runtime thực tế trước lượt CPT.
