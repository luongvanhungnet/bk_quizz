# Tải model CPT từ Colab, chạy Ollama và so sánh

`EXPORT_MERGED=True` tạo thư mục **`RUN_DIR/merged_hf_fp16/`** trên Drive. Đây là model Hugging Face đầy đủ. Cần tải **toàn bộ thư mục**, gồm config, tokenizer và mọi shard `.safetensors`; không chỉ lấy adapter hay một shard riêng lẻ.

Luồng dùng trên máy: **HF FP16 đã merge → llama.cpp chuyển GGUF F16 → llama-quantize Q4_K_M → Ollama import GGUF → tag mới `qwen3-it3170-cpt:1.7b`**. Model gốc `qwen3:1.7b` được giữ để đối chiếu. Phiên bản Ollama hiện tại trên máy không nhận `--quantize Q4_K_M` cho Safetensors; các loại int4/int8/nvfp4/mxfp4/mxfp8 của đường nhập đó không được coi tương đương Q4_K_M. Với GGUF cần lượng tử hóa trước khi import. [Tài liệu import chính thức](https://docs.ollama.com/import).

## 1. Tạo ZIP model ngay trong notebook Colab đã chạy

Thêm cell sau ở cuối notebook, nơi biến `RUN_DIR` vẫn tồn tại:

```python
from pathlib import Path
import zipfile

export_dir = RUN_DIR / 'merged_hf_fp16'
assert (export_dir / 'config.json').is_file()
assert list(export_dir.glob('*.safetensors'))
zip_path = RUN_DIR / 'qwen3_it3170_cpt_hf.zip'
assert not zip_path.exists(), 'ZIP đã có: dùng file hiện có hoặc đặt tên mới.'
with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as z:
    for p in sorted(export_dir.rglob('*')):
        if p.is_file():
            z.write(p, p.relative_to(export_dir).as_posix())
print('Tải file này từ Google Drive:', zip_path)
```

Nếu mở phiên mới và mất biến, mount Drive rồi gán `RUN_DIR` tới đúng thư mục đợt train của bạn, ví dụ:

```python
from google.colab import drive
from pathlib import Path
drive.mount('/content/drive')
RUN_DIR = Path('/content/drive/MyDrive/BKQuiz_CPT/runs/it3170_qwen3_1_7b_cpt_001')
```

Mở Google Drive trên trình duyệt, vào thư mục đợt chạy, tải `qwen3_it3170_cpt_hf.zip`. ZIP có thể vài GB; tải từ Drive phù hợp hơn widget `files.download` của Colab. Đồng thời tải hai file nhỏ **`baseline_quiz.json`** và **`after_cpt_quiz.json`** để so sánh cặp đã chạy trên Colab. Giữ adapter/checkpoint gốc trên Drive để có thể dùng lại sau.

## 2. Giải nén trên Windows

Mở PowerShell. Ví dụ ZIP được tải vào thư mục Downloads; thay đường dẫn nguồn nếu trình duyệt lưu ở nơi khác:

```powershell
Set-Location D:\BKQuiz
New-Item -ItemType Directory -Force AI\Qwen_cpt_version\local_qwen3\models\merged_hf_fp16
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\qwen3_it3170_cpt_hf.zip" -DestinationPath "D:\BKQuiz\AI\Qwen_cpt_version\local_qwen3\models\merged_hf_fp16"
```

Sau giải nén, `config.json` phải nằm trực tiếp ở `models/merged_hf_fp16/config.json`, cùng các shard. Nếu có `model.safetensors.index.json`, cần đủ mọi file được index tham chiếu. Không trộn file của hai đợt export trong một thư mục.

## 3. Nhập vào Ollama bằng tên mới

Mở ứng dụng Ollama. Từ `D:\BKQuiz`, chạy:

```powershell
python AI\Qwen_cpt_version\local_qwen3\import_ollama.py --model-path AI\Qwen_cpt_version\local_qwen3\models\merged_hf_fp16
```

Script kiểm tra đủ file model, tự tải llama.cpp b6500 và môi trường Python CPU riêng vào `tools/`, chuyển/lượng tử hóa trên máy, rồi lấy template và tham số của `qwen3:1.7b` để tạo Modelfile. Lần đầu cần tải thư viện CPU và thêm dung lượng cho GGUF F16 trung gian. Sau chuyển đổi, script gọi:

```powershell
ollama create qwen3-it3170-cpt:1.7b -f AI\Qwen_cpt_version\local_qwen3\imported\Modelfile
```

Lệnh này được script thực hiện; không thêm `--quantize`. Modelfile trỏ tới `models/qwen3-it3170-cpt-Q4_K_M.gguf`. File `.conversion.json` đi kèm ghi hash nguồn, GGUF, bản công cụ; `imported/import_record.json` lưu thông tin model/template/tham số thực tế. Script từ chối ghi đè tag có sẵn. Nếu làm đợt mới, dùng tên khác, ví dụ `--name qwen3-it3170-cpt-v2:1.7b`.

Có thể kiểm tra file và xem kế hoạch trước bằng cách thêm `--check-only`; chế độ này không tải công cụ hoặc chuyển đổi. Trên máy 8 GB RAM, bộ chuyển đổi dùng chế độ lazy/temp-file và bản PyTorch CPU riêng; không cài PyTorch vào môi trường train cũ.

File tạm chứa tensor được đặt cạnh đầu ra GGUF trên ổ D thay vì thư mục TEMP của Windows trên ổ C. Cần chừa dung lượng cho file tạm, GGUF F16 và GGUF Q4_K_M cùng lúc; các file HF gốc được giữ nguyên.

Nếu phiên bản Ollama báo không hỗ trợ kiến trúc/định dạng hoặc import bị hết RAM, có thể chuyển/quantize trên Colab bằng llama.cpp rồi chỉ tải GGUF Q4_K_M. Helper cũng nhận `--model-path duong_dan_model.gguf`; với GGUF nó không yêu cầu Ollama quantize lại. [Công cụ llama.cpp](https://github.com/ggml-org/llama.cpp). Đừng chỉ đổi đuôi `.safetensors` thành `.gguf`.

## 4. Chạy thử model mới

```powershell
ollama run qwen3-it3170-cpt:1.7b --think=false
```

Ví dụ hỏi: `Tạo một câu trắc nghiệm về tìm kiếm nhị phân, có bốn lựa chọn, đáp án và giải thích.`

Để hỏi model gốc:

```powershell
ollama run qwen3:1.7b --think=false
```

Đây chỉ là kiểm tra chạy được; vài câu chat không đủ để kết luận CPT tốt hơn. Bộ so sánh bên dưới dùng chat mới cho từng prompt, cùng cấu hình và `think=false`.

## 5. So sánh cặp trước/sau đã có trên Colab

Đặt hai JSON đã tải vào `AI/Qwen_cpt_version/local_qwen3/downloads/`, rồi chạy:

```powershell
python AI\Qwen_cpt_version\local_qwen3\compare_exports.py --before AI\Qwen_cpt_version\local_qwen3\downloads\baseline_quiz.json --after AI\Qwen_cpt_version\local_qwen3\downloads\after_cpt_quiz.json --out AI\Qwen_cpt_version\local_qwen3\results\colab_pair_001
```

Đọc `results/colab_pair_001/REPORT.md`. Hai file này được tạo bằng cùng revision HF, cùng NF4 và cùng decoder, nên đây là cặp đối chứng phù hợp hơn để xem thay đổi sau CPT. Script kiểm tra metadata/cấu hình, hash prompt, đủ sáu case và tính riêng các chỉ số xác định được tự động.

## 6. So sánh model gốc và CPT khi chạy trên máy

Sau khi import thành công, thoát các phiên chat đang sinh câu trả lời rồi chạy:

```powershell
python AI\Qwen_cpt_version\local_qwen3\run_compare.py --out AI\Qwen_cpt_version\local_qwen3\results\ollama_pair_001
```

Nếu dùng tag khác, thêm `--cpt ten-tag-moi:1.7b`. Script sẽ:

- Kiểm tra cả hai model cùng Q4_K_M, cùng template và tham số mặc định.
- Chạy **6 prompt/model = 12 request chấm điểm**, cùng messages, CPU, context, seed và giới hạn token của bộ test cũ.
- Chạy một warm-up riêng/model; giữ response thô và stream, giải phóng model sau mỗi nhóm.
- Giữ request đã lưu nếu chạy tiếp cùng thư mục; không tự sửa/retry câu trả lời lỗi để nâng điểm.
- Xuất `before.json`, `after.json` và `comparison/REPORT.md` kèm CSV từng slot.

Đây là so sánh triển khai thực tế. Cùng lượng tử hóa/template chưa chứng minh tag gốc Ollama dùng đúng hệt revision HF đã train; vì vậy cần đọc cùng cặp đối chứng Colab ở bước 5. Không lấy điểm/tốc độ NF4 Colab so trực tiếp với Q4_K_M trên CPU Windows để kết luận tác dụng CPT.

## 7. Chấm kết quả như thế nào?

Báo cáo tự động gồm JSON strict, schema, đủ slot, quote nguyên văn, từ chối khi thiếu dữ kiện và **key literal khớp oracle**. Chỉ số cuối chỉ kiểm tra giá trị mà key trỏ tới, không tự xác minh câu hỏi có giữ đúng dữ kiện hay lời giải có đúng không.

Trong báo cáo đã đặt nguồn, oracle và output trước/sau cạnh nhau theo từng prompt. Chấm tiếp theo rubric đợt trước: đáp án 35%, duy nhất một lựa chọn đúng 15%, bám nguồn 15%, lời giải 15%, nhiễu 10%, rõ ràng 5%, tuân thủ 5%. Không gán điểm chất lượng chỉ vì JSON hợp lệ hay lời giải có nhắc đúng kết quả.

Bộ prompt nhỏ, cùng miền học phần và có hạn chế enum đã ghi từ đợt trước; không phải held-out test độc lập. Trước hết dùng để kiểm tra CPT có làm mất khả năng tuân thủ/kiến thức đã có, rồi mở rộng với tài liệu độc lập để đánh giá tổng quát.
