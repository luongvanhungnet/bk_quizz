"""Write the human-readable run report from measured artifacts, not estimates."""
import argparse
import json
from pathlib import Path
from common import read_jsonl


def run(out):
    report=json.loads((out/'quality_report.json').read_text(encoding='utf-8'))
    validation=json.loads((out/'validation.json').read_text(encoding='utf-8'))
    tok=json.loads((out/'cpt/tokenization.json').read_text(encoding='utf-8'))
    counts=report['status_counts']
    component_rows=[]
    for path in (out/'components').glob('page_*.json'):
        component_rows.append(json.loads(path.read_text(encoding='utf-8')))
    from collections import Counter
    labels=Counter(b['label'] for r in component_rows for b in r['result']['layout_det_res'].get('boxes', []))
    lines=[
        '# Báo cáo dữ liệu CPT Thuật toán ứng dụng',
        '', 'Ngày: 17/10/2026 (Asia/Bangkok).', '',
        'Đầu vào là **một PDF IT3170**, gồm hai bộ bài giảng đã gộp. File nguồn được giữ nguyên. Mã học phần kế thừa từ manifest với trạng thái suy luận (`inferred`).',
        '', '## Kết quả thực tế', '',
        '| Hạng mục | Kết quả |', '|---|---:|',
        f'| Trang PDF được trích xuất và chuẩn hóa | {report["pages_total"]:,} |',
        f'| Trang chạy mô-đun layout/công thức Paddle | {report["paddle_component_pages"]:,} |',
        f'| Trang chạy PP-StructureV3 đầy đủ | {report["ppstructure_pages"]:,} |',
        f'| Trang đủ điều kiện trước loại trùng | {report["accepted_before_dedup"]:,} |',
        f'| Mẫu CPT sau loại trùng | {report["cpt_samples"]:,} |',
        f'| Trang cần rà soát | {counts.get("needs_review",0):,} |',
        f'| Trang logo/bìa/cảm ơn đã xem và loại khỏi train | {counts.get("excluded_non_content",0):,} |',
        f'| Bản trùng chính xác bỏ khỏi train | {report["exact_duplicates_removed"]:,} |',
        f'| Cặp gần trùng, giữ cùng split | {report["near_duplicate_pairs"]:,} |',
        f'| Bản ghi vùng công thức (gồm ứng viên chưa xác minh) | {report["formula_records"]:,} |',
        f'| Bản ghi bảng (gồm ứng viên chưa xác minh) | {report["table_records"]:,} |',
        f'| Trang được Codex kiểm tra ảnh trực tiếp | {report["reviewed_source_pages"]:,} |',
        f'| Token sau thêm EOS | {tok["total_tokens"]:,} |',
        f'| Chuỗi packed, tối đa {tok["sequence_length"]} token | {tok["sequences"]:,} |',
        '',
        f'Tokenizer: `{tok["tokenizer"]}`. Revision đã phân giải: `{tok.get("revision_resolved")}`. EOS: `{tok["eos_token"]}` / ID `{tok["eos_token_id"]}`. Không tải trọng số hay huấn luyện model ở bước này.',
        '',
        'Tệp dùng huấn luyện: [cpt/train.jsonl](cpt/train.jsonl) hoặc [cpt/train.packed.jsonl](cpt/train.packed.jsonl). Metadata nguồn: [cpt/train.metadata.jsonl](cpt/train.metadata.jsonl). Dataset đầy đủ trạng thái: [normalized.jsonl](normalized.jsonl).',
        '', '## Độ bao phủ và giới hạn', '',
        '**Chưa phải toàn bộ 1.060 trang đều được chuyển thành dữ liệu train đã sạch.** Tất cả trang vẫn có trong lớp chuẩn hóa. Các mẫu chứa hình/công thức/bảng hoặc glyph chưa xác minh được giữ trong [review_queue.jsonl](review_queue.jsonl).',
        '',
        'Người dùng chọn Qwen2.5 Base và chưa có endpoint VLM. Các ví dụ hình/bảng đã kiểm tra gồm trang 20 (số mũ và tràn số), 49/51 (bảng SMS), 300 (hướng cung), 500 (trọng số/cạnh đỏ của Kruskal), 753 (khung văn bản bị detector nhầm thành bảng), 800 (code). Những kiểm tra này do Codex đọc ảnh, không phải bộ gold được chuyên gia/người độc lập gán nhãn. Các hình khác giữ trạng thái pending.',
        '',
        'Tập này chỉ có train. Validation/test rỗng theo đơn vị tài liệu để tránh chia các phiên bản gần trùng sang hai tập. Cần nguồn đánh giá độc lập trước khi báo cáo chất lượng model.',
        '', '## Chất lượng và kiểm tra', '',
        f'- Source Traceability theo ánh xạ trang: {report["metrics"]["Source Traceability"]["value"]:.2%}.',
        f'- Duplicate Rate trong các mẫu đủ điều kiện: {report["metrics"]["Duplicate Rate"]["value"]:.2%} trước khử trùng lặp; train sau xử lý không có bản text trùng chính xác.',
        '- CER/WER toàn tập, Formula Accuracy, Diagram Fact Precision, Information Coverage: chưa đo vì chưa có ground truth độc lập. Không thay bằng điểm tự đánh giá của model.',
        '- QA phụ: hai trang 20 và 100 được chép từ ảnh bởi Codex, so với native text trước khi ghi đè annotation; xem [qa/reference_metrics.json](qa/reference_metrics.json). Kết quả chỉ áp dụng cho hai trang này.',
        f'- Kiểm tra tính toàn vẹn: **{"PASS" if validation["passed"] else "FAIL"}**, xem [validation.json](validation.json). Bao gồm SHA-256 PDF/ảnh, số trang, metadata, PII email, cổng chất lượng, split, labels và đối chiếu tất cả token sau packing.',
        '', 'Các nguyên nhân cần rà soát:', '', '| Cờ | Số trang |', '|---|---:|',
        *[f'| `{key}` | {value} |' for key,value in sorted(report['flag_counts'].items())],
        '', 'Một trang có thể mang nhiều cờ. Điểm confidence không được hiệu chuẩn được để null; điểm detector/OCR do backend trả về được lưu riêng.',
        '', '## Phát hiện kỹ thuật', '',
        '- Khoảng trắng tiếng Việt được phục hồi từ khoảng cách ký tự: `Sửdụng` → `Sử dụng`.',
        '- Chỉ số trên được giữ: `1018` trong bản text thô → `10^{18}` khi PDF xác nhận baseline/cờ superscript. Những trường hợp chưa chắc vẫn cần đối chiếu.',
        '- Ghép các dòng code bị chia block và giữ thụt lề. Dự đoán công thức chồng lên vùng native code được ghi nhận là ứng viên bị bỏ qua.',
        '- PP-StructureV3 nhận dạng đúng hai công thức ở ví dụ trang 20, nhưng có lỗi ở công thức trang 650 và từng nhầm code trang 800 là toán. Vì vậy không đưa mọi LaTeX OCR vào train tự động.',
        '- Dùng PaddlePaddle 3.2.2 sau khi gặp lỗi oneDNN/PIR trên 3.3.1; các mô-đun được thực thi trên CPU.',
        '- Alphabet thực tế của model Latin OCR thiếu một số chữ tiếng Việt có dấu; xem [ocr_capabilities.json](ocr_capabilities.json). Không dùng đầu ra OCR này thay chữ nguồn trong train khi chưa đối chiếu.',
        '', 'Nhãn layout phát hiện (số **vùng**, không phải số trang):', '',
        '| Nhãn | Số vùng |','|---|---:|',
        *[f'| `{key}` | {value} |' for key,value in sorted(labels.items())],
        '', 'Cách cài đặt, chạy lại, duyệt thêm mẫu và dùng dữ liệu: [README](../../README.md).',
    ]
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    samples=read_jsonl(out/'cpt/train.metadata.jsonl')
    selected=[r for r in samples if r['page'] in [20,49,51,100,300,500,800]]
    preview=['# Ví dụ dữ liệu CPT đã xuất','', 'Các bản ghi có đầy đủ nguồn trang trong train.metadata.jsonl.','']
    for row in selected:
        preview += [f'## Trang {row["page"]}', '', row['text'], '', f'Nguồn: `{row["source"]["document_sha256"]}`, trang `{row["page"]}`.', '']
    (out/'samples_preview.md').write_text('\n'.join(preview),encoding='utf-8')
    print('Wrote REPORT.md and samples_preview.md')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    run(a.out)
