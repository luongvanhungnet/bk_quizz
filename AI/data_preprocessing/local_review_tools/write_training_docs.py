"""Write the audit result and operating guide for a completed training export."""
import argparse
import json
from pathlib import Path


def write_docs(root):
    root=Path(root)
    stage=json.loads((root/'stage_report.json').read_text(encoding='utf-8'))
    export=json.loads((root/'export_report.json').read_text(encoding='utf-8'))
    audit=json.loads((root/'audit/findings.json').read_text(encoding='utf-8'))
    counts=stage['counts'];details=export['counts']
    rows=['| Mẫu | Học phần / trang | Kết luận | Xử lý / chứng cứ |','|---|---|---|---|']
    for f in audit['findings']:
        rows.append(f"| {f['sample_id']} | {f['course']} / {f['page']} | {f['verdict']} | {f['training_action']}: {f['note']} |")
    report=f'''# Kiểm tra và xuất CPT 27 học phần — 23/10/2026

Đã kiểm tra ngẫu nhiên phân tầng **24 vùng**: 6 VLM đã chấp nhận, 6 text mặc định, 4 OCR vùng ảnh, 4 bảng/công thức và 4 VLM đã loại. Seed **20261023** được khóa trước khi đọc mẫu. Chọn bằng SHA-256 của seed/nhóm/học phần/ID, không thay mẫu sau khi thấy lỗi. Đã đối chiếu crop và ảnh trang; 72 tham chiếu ảnh của mẫu khớp SHA-256.

Trong 20 ứng viên train: **10 mẫu không thấy lỗi đáng kể, 4 mẫu dùng được nhưng còn nhiễu định dạng hoặc mô tả đơn giản, 6 mẫu không phù hợp**. Sáu mẫu gồm OCR/font hỏng (S08), trang logo (S12), mất/sai ký hiệu toán (S14/S17/S19/S20). Đã cách ly sáu ID cùng bản trùng chính xác về nội dung; tổng vùng cách ly do audit: **{details.get('audit_quarantine',0)}**. Bốn mẫu VLM bị chủ dữ liệu loại vẫn bị loại. Mô tả S24 có phần khớp nguồn nhưng không đảo quyết định loại đã lưu.

Đây là kiểm tra nhỏ có phân tầng, không phải lấy mẫu đại diện để ước lượng độ chính xác toàn corpus. Không suy ra mọi công thức/OCR còn lại đều đúng. Việc duyệt VLM đã chặn nhiều mô tả yếu, nhưng không làm sạch hết text, công thức hoặc logo chưa duyệt. Dữ liệu mặc định vẫn có rủi ro nhiễu; đợt train đầu nên dùng 1 epoch và so kết quả trước/sau trước khi mở rộng.

## Lịch sử và chính sách chấp nhận

- {counts['records']:,} vùng / 27 học phần / 13.314 trang; {counts['review_events']:,} sự kiện duyệt.
- {counts['vlm_records']:,} VLM có quyết định hiện hành, khớp đầy đủ identity; {counts['review_approve']} chấp nhận, {counts['review_reject']} loại bỏ, không có stale.
- Chỉ thị chủ dữ liệu: các kết quả chưa từng kiểm tra mặc định đạt. Export gắn `owner_default_pass`, `human_verified=false`; không tạo sự kiện giả vào SQLite.
- Trước khử trùng: {counts['selected']:,} ứng viên train = {counts['accepted_review_approve']:,} VLM chấp nhận thuộc train + {counts['accepted_owner_default_pass']:,} vùng mặc định có nội dung thuộc train.
- Giữ ngoài train {counts['excluded_protected_development']} vùng development, {counts['excluded_protected_holdout']} vùng holdout; {counts['excluded_empty_text']:,} vùng train rỗng; {counts['excluded_review_reject']} quyết định reject thuộc train. Một reject và 10 approve còn lại nằm trong split bảo vệ, không xuất train.
- Snapshot SQLite nằm trong `snapshots/`; máy nguồn và lịch sử duyệt không bị sửa. `selection.jsonl` giữ nguồn đầy đủ tại máy; ZIP chỉ chứa text và metadata rút gọn, không chứa PDF/ảnh hay SQLite.

## Bộ dữ liệu cuối

**{export['samples']:,} mẫu / {len(export['courses'])} học phần / {export['characters']:,} ký tự**. Số mẫu là số vùng text, không phải số trang, không tuyên bố bao phủ toàn bộ tri thức của PDF.

Phân loại sau lọc: `{json.dumps(details,ensure_ascii=False)}`.

Đã kiểm SHA-256 **{export['unique_source_assets_sha256_verified']:,} đối tượng ảnh nguồn khác nhau** của các mẫu được giữ. Dedup ưu tiên văn bản có quyết định duyệt; khử trùng văn bản NFC, giữ nguyên chữ hoa/thường và khoảng trắng bên trong để bảo toàn ý nghĩa code/công thức. Loại trùng với split bảo vệ bằng text chính xác, render trang giống hệt và kiểm gần trùng pHash <=4 + Jaccard trigram >=0,85 (ít nhất 20 từ). Đây không phải kiểm trùng ngữ nghĩa toàn diện; không dùng bộ split trang cũ để tuyên bố có đánh giá tổng quát hóa độc lập.

Train là causal next-token loss trên text và EOS, không phải ảnh hoặc dữ liệu hỏi–đáp sinh thêm. Metadata có ID học phần/vùng, trang, hash nguồn, acceptance và review ID để truy nguyên. Email được che theo quy tắc exporter cũ; không tuyên bố đã phát hiện mọi thông tin cá nhân.

## Chi tiết mẫu

{chr(10).join(rows)}

Ảnh đối chiếu: `audit/contact_01.png` đến `audit/contact_06.png`; danh sách khóa trước khi đọc: `audit/sample.json`; kết luận có hash ảnh: `audit/findings.json`.

## Training

Dùng cấu hình Qwen3 1.7B đã có của dự án, revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`; không đổi sang bản Base. QLoRA NF4 r=8, sequence 1024, batch 1, accumulation 8, LR 2e-5, cosine/warmup 3%, 1 epoch. Checkpoint 25 bước, giữ 2 bản; smoke 2 bước nằm riêng.

Đã kiểm CPU việc xuất dữ liệu, hash, cú pháp notebook, Unicode, token packing và checkpoint selection. Chưa chạy backward/GPU Colab hoặc đo cải thiện model trong lượt đóng gói này. Loss chẩn đoán của notebook đo cùng tối đa 64 sequence train trước/sau, không phải validation loss. Quiz probe tùy chọn giữ riêng và không vào train.

Nguồn kỹ thuật: [model Qwen](https://huggingface.co/Qwen/Qwen3-1.7B), [Trainer 4.57](https://huggingface.co/docs/transformers/v4.57.1/en/main_classes/trainer), [PEFT quantization](https://huggingface.co/docs/peft/developer_guides/quantization).
'''
    (root/'AUDIT_REPORT.md').write_text(report,encoding='utf-8')
    guide='''# Train CPT Qwen3 1.7B trên Colab — 27 học phần

1. Trong Drive **MyDrive/BKQuiz_CPT**, dùng cặp mới `BKQuiz_Qwen3_1_7B_CPT_27courses.ipynb` và `bkquiz_cpt_27courses_20261023.zip`. Gói IT3170 cũ vẫn giữ riêng; không dùng ZIP cũ cho notebook mới.
2. Mở notebook bằng Google Colab. Chọn **Runtime → Change runtime type → Python 3 / GPU**; ưu tiên L4. Chạy từng cell từ trên xuống, mount đúng Drive và chấp nhận quyền truy cập khi Colab yêu cầu.
3. Notebook kiểm hash ZIP/nội dung, tạo venv, kiểm GPU và các thư viện đã khóa, tokenize đúng revision Qwen3 rồi chạy smoke 2 bước. Nếu smoke đạt, cell CPT chạy 1 epoch từ model gốc. Không dùng adapter smoke cho train chính.
4. Kết quả ở **MyDrive/BKQuiz_CPT/runs/cpt_27courses_20261023_001/train/adapter**; checkpoint đầy đủ và optimizer ở thư mục train. Giữ `completed.json`, `environment.json`, `pip-freeze.txt` và các metrics cùng adapter.

Mất phiên: chạy lại mount/extract/install/prepare, giữ RUN_NAME, đặt `RESUME_TRAIN=True`. Trainer chọn checkpoint đầy đủ gần nhất; không đổi dữ liệu, code, config hoặc phiên bản thư viện khi resume. Đổi RUN_NAME để thử cấu hình khác. Không tái sử dụng thư mục output cũ cho một thí nghiệm mới.

Mặc định: Qwen/Qwen3-1.7B, QLoRA NF4 (chỉ train LoRA), sequence 1024, batch 1, accumulation 8, LR 2e-5, warmup 3%, cosine, 1 epoch, r8/alpha16/dropout0.05. GPU/runtime thực tế do Colab cấp; smoke mới xác nhận khả năng chạy trên phiên của bạn.

`RUN_PROBES=False` và `EXPORT_MERGED=False` mặc định. Bật probe để xuất cùng sáu tình huống IT3170 trước/sau; chúng không phải benchmark độc lập. Bật merge khi cần model HF FP16 và còn đủ RAM/Drive. Không tự upload model lên Hugging Face; chưa tạo GGUF/Ollama ở bước này.

Đọc **AUDIT_REPORT.md** trước lượt train: còn rủi ro OCR/công thức trong nhóm chấp nhận mặc định. Chỉ train một epoch đầu; loss giảm không tự chứng minh model sinh quiz tốt hơn. Khi chạy xong, ngắt runtime để dừng tiêu thụ tài nguyên.
'''
    (root/'HUONG_DAN_COLAB.md').write_text(guide,encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--release',type=Path,required=True)
    write_docs(parser.parse_args().release)

