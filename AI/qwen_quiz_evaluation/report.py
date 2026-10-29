"""Publish the measured run and explicit grading limitations as Markdown."""
from __future__ import annotations
import collections
import json
from pathlib import Path
from build_suite import RUN

def load(name):return json.loads((RUN/name).read_text(encoding='utf-8'))
def fmt(value,digits=2):return 'N/A' if value is None else f'{value:.{digits}f}'

def question_appendix(models,scores,gold):
    packet={p['question_id']:p for p in load('review_packet.json')}
    lines=['# Chi tiết chấm từng câu quiz','',
           'Gồm tất cả 11 slot được yêu cầu/model, kể cả slot thiếu. Điểm theo rubric đã khóa trước inference. Nội dung JSON gốc được liên kết ở từng câu.','']
    for m in models:
        lines += ['## '+m['name'],'']
        for row in [s for s in scores if s['eval_id']==m['eval_id']]:
            p=packet[row['question_id']];q=p['question']
            lines += [f'### {row["case_id"]} / {row["slot_id"]}', '',
                      f'ID: `{row["question_id"]}`. Chuẩn: **{gold["facts"][row["slot_id"]]}**. Điểm: **{row["quality_score"]:.2f}/100**. Qua cổng dùng được: **{"Có" if row["usable"] else "Không"}**.', '']
            if q is not None:
                lines += ['```json',json.dumps(q,ensure_ascii=False,indent=2),'```','']
            else:
                lines += ['Không có câu khôi phục được cho slot này; điểm 0 theo mẫu số đã định.','']
            lines += ['- Điểm chiều: '+', '.join(f'{k}={v}' for k,v in row['dimensions'].items())+'.',
                      '- Lỗi schema: '+(', '.join(p['automatic_schema_errors']) or 'không')+'.',
                      '- Nhận xét: '+row['notes'],
                      f'- [Request và output gốc](responses/{m["eval_id"]}/{row["case_id"]}.json).','']
    (RUN/'QUESTION_REVIEWS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

def main():
    summary=load('summary.json');scores=load('question_scores.json');checks=load('automatic_checks.json')
    models=load('inventory.json')['models'];protocol=load('protocol.json');gold=load('gold.json')
    validation=load('validation.json');complete=load('run_complete.json')
    if not validation['passed']:raise ValueError('Evaluation artifacts have not passed validation')
    question_appendix(models,scores,gold)
    ranked=sorted(summary,key=lambda r:(-r['usable_questions'],-r['correct_questions'],-r['quality_mean_expected_slots'],r['median_latency_seconds']))
    top=ranked[0]
    qcount=sum(s['expected_questions'] for s in summary)
    lines=[
      '# Đánh giá các model Qwen local cho sinh quiz', '',
      'Đợt đánh giá ngày 17/10/2026, múi giờ Asia/Bangkok. Lượt chạy và chấm được lưu đầy đủ để đối chiếu.', '',
      '## Kết quả chính', '',
      f'Đã thử **{len(models)} model Qwen có trọng số local**, mỗi model cùng **6 prompt**: tổng **{len(checks)} request chấm điểm**, **{qcount} slot câu hỏi có đáp án xác định** và {len(models)} slot kiểm tra từ chối khi thiếu dữ kiện. Đây là benchmark sinh quiz theo nguồn về Thuật toán ứng dụng, không phải điểm năng lực tổng quát của Qwen.', '',
      '| Model | Request OK | JSON strict | Đủ câu/đúng slot | Đáp án đúng /11 | Câu dùng được /11 | Điểm /100 | Từ chối thiếu dữ kiện |',
      '|---|---:|---:|---:|---:|---:|---:|---|',
    ]
    for r in ranked:
        lines.append(f'| `{r["model"]}` | {r["successes"]}/{r["requests"]} | {r["strict_json"]}/{r["requests"]} | {r["correct_count_requests"]}/{r["requests"]} | {r["correct_questions"]}/{r["expected_questions"]} | {r["usable_questions"]}/{r["expected_questions"]} | {r["quality_mean_expected_slots"]:.2f} | {"Đạt" if r["refusal_success"] else "Không đạt"} |')
    conclusion=(f'Xếp theo **số câu dùng được**, sau đó số đáp án đúng và điểm rubric, `{top["model"]}` đứng đầu bộ test này: {top["usable_questions"]}/{top["expected_questions"]} câu dùng được, {top["correct_questions"]}/{top["expected_questions"]} đáp án đúng, {top["quality_mean_expected_slots"]:.2f}/100. Thứ hạng này chỉ áp dụng cho các bản cài đặt, lượng tử hóa và cấu hình đã thử.'
                if top['usable_questions'] else 'Không model nào có câu vượt đầy đủ cổng dùng được với bộ prompt/cấu hình này. Vì vậy không có cơ sở đề xuất đưa model nào vào sinh quiz không giám sát; cần xem riêng kiến thức, định dạng và mức đủ dữ kiện, rồi cải thiện prompt/giải mã và kiểm thử lại.')
    lines += ['',conclusion,
      '',
      '**Lưu ý riêng Qwen3 4B:** metadata local ghi `finetune=Thinking`, `version=2507`, khớp Qwen3-4B-Thinking-2507. Bản này chỉ hỗ trợ thinking theo [model card Qwen](https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507); think=false không bảo đảm tắt suy luận. Đã thấy suy luận chiếm ngân sách trước JSON. Slot không xuất được quiz nhận 0 vận hành, không có nghĩa model tính sai mọi bài. Đây là phép thử chung ngân sách, chưa phải so sánh công bằng năng lực suy luận giữa các biến thể.',
      '',
      '**“Dùng được”** là cổng đã định trước: câu có schema hợp lệ, đáp án đánh dấu đúng, đúng một lựa chọn đúng về ngữ nghĩa, bám nguồn, lời giải đủ, câu có thể đọc hiểu và đúng yêu cầu slot. Chỉ số trích dẫn nguyên văn được báo riêng; việc trích dẫn khớp chuỗi không tự chứng minh kiến thức đúng.',
      'Đúng đáp án được đối chiếu với bài toán trong nguồn, tách khỏi việc stem có tự đủ dữ kiện hay không. Vì vậy một model có thể tăng số đáp án đúng nhưng vẫn không tăng số câu dùng được do lời giải sai, key mâu thuẫn hoặc thiếu dữ kiện trong câu hỏi.',
      '“Dùng được” ở đây chỉ là đạt ngưỡng rubric trong bộ test này, chưa phải chứng nhận đưa trực tiếp vào ngân hàng đề thi.',
      '', '## Tốc độ và khả năng vận hành', '',
      '| Model | Trung bình s/request | Trung vị s/request | Token sinh/s | Trích dẫn khớp nguyên văn | Kết thúc vì giới hạn token |',
      '|---|---:|---:|---:|---:|---:|',
    ]
    for r in summary:
        evidence=f'{r["exact_evidence"]}/{r["generated_questions_total"]}' if r['generated_questions_total'] else 'N/A (không parse được câu)'
        lines.append(f'| `{r["model"]}` | {r["mean_latency_seconds"]:.2f} | {r["median_latency_seconds"]:.2f} | {fmt(r["generation_tokens_per_second"])} | {evidence} | {r["truncated_responses"]} |')
    lines += ['',
      'Độ trễ là thời gian wall-clock mỗi request, tính cả prefill và tải lại model nếu xảy ra. Warm-up không nằm trong bảng. Token/s tính từ tổng eval_count / tổng eval_duration do Ollama trả về, không tính thời gian chấm; token giữa các tokenizer không hoàn toàn tương đương. Prompt ngắn/dài và độ dài lời giải khác nhau nên cần xem cả độ trễ lẫn chất lượng.',
      '', '## Phát hiện model và môi trường', '',
      '| Model | Tham số theo metadata local | Lượng tử hóa | Runner local | Digest Ollama |',
      '|---|---|---|---|---|',
    ]
    for r in summary:
        model=next(m for m in models if m['name']==r['model'])
        lines.append(f'| `{r["model"]}` | {r["parameter_size"]} | {r["quantization"]} | {model.get("details",{}).get("runner","N/A")} | `{r["digest"]}` |')
    lines += ['',
      '- Ollama 0.40.0; Intel Core i7-1165G7, 4 nhân/8 luồng, RAM khoảng 8 GB; dùng CPU 4 luồng, num_gpu=0. Phần cứng thực tế ghi tại `hardware.json`.',
      '- Năm model ở Ollama chính; thêm Qwen2.5 0.5B từ kho `D:\ollama_models` qua server local tạm. Qwen3 1.7B ở hai kho trùng digest nên chỉ thử một lần.',
      '- Qwen2.5-7B trong cache Hugging Face chỉ có tokenizer/config, không có trọng số. Trong AI chưa có checkpoint CPT/SFT chạy được; các JSONL tiền xử lý không phải model đã huấn luyện.',
      '- Tên tag không thể hiện đủ biến thể: qwen3:4b có metadata Thinking/2507 và license URL trỏ tới Qwen3-4B-Thinking-2507. Chi tiết được giữ trong model_details/M05.json.',
      '- Không tải model mới. Server chính được giữ nguyên; server tạm dùng để đọc kho D đã được dừng sau chạy. Một lần thăm dò khởi động server phụ bị timeout trước khi có lượt sinh chấm điểm; không được tính như lỗi model. Lần thăm dò đầu dùng mặc định của Ollama và tự dọn 2 blob không được tham chiếu; các trọng số model đăng ký vẫn đủ và chạy được. Những lần khởi động sau bật NOPRUNE và NO_CLOUD.',
      '- Thứ tự chạy tăng theo dung lượng lưu; mỗi lần chỉ một model và một request. Không có phép lặp nhiều thứ tự để tách ảnh hưởng nhiệt độ CPU/cache và tác vụ nền.',
      '', '## Bộ prompt và đáp án chuẩn', '',
      '| Prompt | Nội dung | Chuẩn độc lập |', '|---|---|---|',
      '| P01 | Tìm tuyến tính và nhị phân | 8 phần tử; 5 lần xét mid với dãy mid-value 8,12,14,15,16 |',
      '| P02 | Hàm đệ quy và hai vòng lặp | f(5)=15; counter=10 |',
      '| P03 | Đường đi A-D và MST | khoảng cách 4 qua A-B-C-D; MST trọng số 6 |',
      '| P04 | Ba lô 0/1 và LCS | giá trị 7, chọn vật 1+2; LCS dài 4, ví dụ BCBA |',
      '| P05 | Tràn số và cạnh âm | nhỏ nhất trong 16/32/64/128 là 64 bit; Bellman-Ford |',
      '| P06 | Đọc bảng và từ chối dữ kiện thiếu | Case #2 là 41; không được bịa số mili giây trên Intel i7 |',
      '',
      'Nguồn là các tình huống kiểm thử tổng hợp, không lấy ngẫu nhiên câu từ tập train. Oracle được viết và đóng hash trước inference: mô phỏng tìm kiếm/truy vết, liệt kê mọi đường đơn/cây khung/tập vật nhỏ và kiểm LCS bằng cả DP và liệt kê dãy con. Không dùng câu trả lời của model để tạo đáp án chuẩn. Xem [gold.json](gold.json), [prompts.json](prompts.json), [protocol.json](protocol.json).',
      '', '## Phương pháp đánh giá', '',
      '1. Giữ nguyên system/user messages và hash cho mọi model. Dùng template gốc tương ứng model; đây là so sánh cùng yêu cầu ngôn ngữ, không phải cùng chuỗi token sau chat template.',
      '2. temperature=0, seed=42, context=4096, max output=1400; gửi think=false trong mọi request. Đây là cấu hình yêu cầu qua API, không khẳng định tất cả template local thực sự tắt suy luận. Không ép grammar JSON để quan sát khả năng tuân thủ. Không sửa đáp án, không retry có chấm điểm.',
      '3. Kiểm tra tự động: HTTP/stream hoàn tất, JSON strict, schema, bốn options khác nhau, ID slot/số câu, nguồn và quote nguyên văn, việc từ chối, truncation và tốc độ. Chỉ khôi phục object có questions hoàn chỉnh từ lời dẫn/Markdown; không vá JSON bị cắt hay ghép các mảnh câu. Output khôi phục vẫn trượt JSON strict.',
      '4. Tạo packet câu hỏi xáo trộn, ẩn tên model, kèm nguồn và đáp án chuẩn. Codex chấm từng câu theo rubric cố định; không cho Qwen tự chấm mình. Rater theo dõi tiến độ chạy và đã đọc một số output mang nhãn khi kiểm lỗi, nên có thể suy ra model dù packet ẩn nhãn. Đây không phải đánh giá mù hoặc chấm bởi người độc lập.',
      '5. Tính điểm trên 11 slot được yêu cầu/model; câu thiếu hoặc request lỗi nhận 0 trong điểm thực dụng. Không bỏ câu thiếu để làm tăng trung bình. Điểm trung bình chỉ trên câu có output cũng được lưu riêng trong summary.json.',
      '',
      '| Tiêu chí | Thang gốc | Trọng số |', '|---|---:|---:|',
      '| Đáp án đúng theo oracle và đúng bài toán | 0–4 | 35% |',
      '| Có đúng một phương án đúng về ngữ nghĩa | 0–2 | 15% |',
      '| Bám nguồn, không bịa điều kiện/dữ kiện | 0–3 | 15% |',
      '| Lời giải đúng và đủ lập luận | 0–3 | 15% |',
      '| Phương án nhiễu khác nhau, hợp lý | 0–2 | 10% |',
      '| Tiếng Việt rõ, đủ dữ kiện trong câu hỏi | 0–2 | 5% |',
      '| Đúng slot, loại nhiệm vụ và độ khó yêu cầu | 0–2 | 5% |',
      '',
      'Điểm = tổng (điểm chiều / tối đa chiều × trọng số). Chi tiết thang điểm/cổng dùng được: [rubric.json](rubric.json). Các điểm nhận xét là đánh giá của Codex, không phải kết luận được chuyên gia xác nhận; đáp án số và điều kiện chuẩn được kiểm bằng chương trình riêng.',
      '', '## Kết quả theo nhóm bài', '',
      '| Model | P01 /2 | P02 /2 | P03 /2 | P04 /2 | P05 /2 | P06 /1 |', '|---|---:|---:|---:|---:|---:|---:|',
    ]
    for m in models:
        values=[sum(r['dimensions']['correctness']==4 for r in scores if r['eval_id']==m['eval_id'] and r['case_id']==f'P{i:02d}') for i in range(1,7)]
        lines.append('| `'+m['name']+'` | '+' | '.join(str(v) for v in values)+' |')
    error_counts=collections.Counter(e for c in checks for errors in c['schema_errors'] for e in errors)
    lines += ['', '## Lỗi định dạng ghi nhận tự động', '',
              f'Có {sum(r["missing"] for r in scores)} slot không có câu quiz chấm được, tính cả phản hồi không khôi phục được JSON. Các lỗi dưới đây tính trên câu đã parse; một câu có thể có nhiều lỗi.', '',
              '| Mã kiểm tra | Số lần |', '|---|---:|']
    for name,count in error_counts.most_common():lines.append(f'| `{name}` | {count} |')
    if not error_counts:lines.append('| Không có lỗi schema trên câu đã parse | 0 |')
    lines += ['', '## Nhận xét từng model và ví dụ cần chú ý', '']
    for m in models:
        rows=[r for r in scores if r['eval_id']==m['eval_id']]
        bad=sorted([r for r in rows if r['quality_score']<95 or not r['usable']],key=lambda r:(r['quality_score'],r['question_id']))[:4]
        s=next(r for r in summary if r['eval_id']==m['eval_id'])
        lines += [f'### {m["name"]}', '',f'Đúng {s["correct_questions"]}/11 đáp án; {s["usable_questions"]}/11 câu qua cổng dùng được; điểm {s["quality_mean_expected_slots"]:.2f}/100.']
        cs=[c for c in checks if c['eval_id']==m['eval_id']]
        truncated=[c['case_id'] for c in cs if c['finish_reason']=='length']
        unparseable=[c['case_id'] for c in cs if c['parse_mode']=='unparseable']
        lines.append(f'Chẩn đoán cấu trúc: {s["strict_json"]}/6 JSON thuần; {s["strict_schema"]}/6 đúng schema; lượt từ chối nhầm trên slot đủ dữ kiện: {s["unsupported_refusals_of_valid_slots"]}. Các request bị cắt theo token: {", ".join(truncated) or "không"}; không khôi phục được JSON object quiz: {", ".join(unparseable) or "không"}.')
        if m['name']=='qwen3.5:2b':
            lines += ['', 'Chẩn đoán P02 trước điểm cắt: model tạo options 10/21/36/42, đánh dấu B=21 nhưng trong explanation lại tự tính đúng f(5)=15. Nó tiếp tục viện giả thuyết nguồn ghi nhầm f(6), thay vì sửa bộ lựa chọn; object chưa hoàn tất nên hai slot vẫn nhận 0 theo quy tắc parse. Đây là nhận xét trên prefix gốc, không phải điểm kiến thức suy ra cho một câu quiz hoàn chỉnh. [Output P02](responses/M06/P02.json).']
            lines += ['', 'P06 có giá trị bảng 41 đúng và lựa chọn “Không thể xác định từ nguồn”, nhưng object sai cú pháp ở evidence_quote (dùng ký tự | thay dấu hai chấm). Slot thiếu thời gian còn bị biến thành câu trắc nghiệm thay vì đưa vào rejected. Vì không khôi phục được object hoàn chỉnh, slot bảng nhận 0 và kiểm tra từ chối không đạt; không được hiểu hai điểm này là model đọc sai số 41 hay đã bịa số mili giây. [Output P06](responses/M06/P06.json).']
        if not bad:lines.append('Không có lỗi đáng kể trong những câu được thử; mẫu nhỏ chưa đủ để khẳng định model không mắc lỗi.')
        for q in bad:
            lines += [f'- **{q["case_id"]} / {q["slot_id"]}**, {q["quality_score"]:.2f}/100: {q["notes"]} '
                      f'[Output gốc](responses/{m["eval_id"]}/{q["case_id"]}.json), ID chấm `{q["question_id"]}`.']
        correct=sorted([r for r in rows if r['dimensions']['correctness']==4],key=lambda r:-r['quality_score'])
        if correct:
            best=correct[0]
            lines += ['',f'Ví dụ có đáp án đúng đạt điểm cao nhất của model: **{best["case_id"]} / {best["slot_id"]}**, {best["quality_score"]:.2f}/100, qua cổng dùng được: {"có" if best["usable"] else "không"}. {best["notes"]} [Output gốc](responses/{m["eval_id"]}/{best["case_id"]}.json).']
        lines.append('')
    lines += ['## Giới hạn và cách dùng kết quả', '',
      '- Sáu prompt và một lần sinh/model là mẫu nhỏ. Không có kiểm định ý nghĩa thống kê, khoảng tin cậy hay kết luận bền vững qua seed/prompt khác.',
      '- Cùng cấu hình sampler không làm các bản khác kiến trúc/lượng tử hóa trở thành so sánh chỉ riêng số tham số. Qwen3.5 2B dùng Q8_0 trong khi phần lớn bản khác dùng Q4_K_M.',
      '- Các tham số được override nằm trong protocol.json; tham số khác có thể kế thừa Modelfile, được lưu nguyên trong model_details. Chẳng hạn Qwen3.5 2B có presence_penalty=1.5 trong cấu hình local. Đây là so sánh các bản cài chạy với cùng nhóm override, chưa kiểm soát mọi mặc định backend/model.',
      '- Prompt mô tả enum bằng chuỗi như `A|B|C|D`; một số output sao chép thành key nhiều giá trị dù đã yêu cầu một đáp án. Đây có thể là tương tác prompt/model. Chưa có đối chứng với ví dụ JSON hợp lệ dùng duy nhất `answer="A"` hoặc giải mã theo JSON Schema, nên không quy toàn bộ lỗi này thành thiếu kiến thức thuật toán.',
      '- Ngân sách 1.400 token chung có thể cắt phản hồi dài; điểm 0 cho slot mất vì truncation phản ánh cấu hình vận hành này, không chứng minh model không biết đáp án khi được thêm token.',
      '- Template local 4B luôn mở `<think>`, còn 1.7B có nhánh `/no_think` và thẻ đóng sẵn. P01 của 4B trả suy luận tiếng Anh trong content rồi bị cắt. Cần lượt đánh giá riêng với ngân sách suy luận đủ và parser thinking phù hợp; không thể chỉ sửa cờ để coi Thinking-2507 là bản non-thinking. [Metadata/template 4B](model_details/M05.json), [template 1.7B](model_details/M03.json), [output P01 4B](responses/M05/P01.json).',
      '- P06 báo rõ nguồn thiếu thời gian chạy và nhắc phải từ chối. Đây là phép thử từ chối có gợi ý trực tiếp, chưa đo khả năng chống bịa khi dữ kiện thiếu kín đáo hoặc câu hỏi đánh lừa.',
      '- Có nguồn ngắn, rõ và đáp án chuẩn; chưa thử PDF/OCR lỗi, truy hồi RAG, ngữ cảnh dài, nhiều môn hay sinh hàng chục câu một lượt.',
      '- EASY/MEDIUM/HARD là nhãn nhiệm vụ đặt trước. Chưa kiểm định độ khó, khả năng phân hóa hay hiệu quả học tập trên người học thực tế.',
      '- Không có quyền truy cập tập huấn luyện gốc của các model nên không chứng minh các dạng bài phổ biến này chưa từng xuất hiện khi huấn luyện.',
      '- Chưa đo độ đa dạng qua nhiều lần sinh hay độ ổn định dưới tải; không dùng kết quả này để kết luận chất lượng một checkpoint Base/CPT/SFT chưa chạy.',
      '- Trước triển khai, cần bộ test lớn hơn, nguồn độc lập và chấm mù bởi ít nhất hai người; giữ kiểm tra đáp án duy nhất, điều kiện thuật toán và trích dẫn trong ứng dụng.',
      '', '## Hồ sơ tái hiện và kiểm tra', '',
      f'- Kiểm tra tính toàn vẹn: **PASS**, {validation["requests"]} request, {validation["expected_slots"]} slot, toàn bộ hash/request/options/review và tính điểm được đối chiếu.',
      '- [Tổng hợp JSON](summary.json), [CSV](summary.csv), [điểm từng câu](question_scores.json), [nhận xét gốc](reviews.json), [kiểm tra tự động](automatic_checks.json).',
      '- [Phụ lục Markdown: toàn bộ câu hỏi, điểm và nhận xét](QUESTION_REVIEWS.md).',
      '- [Packet đã ẩn tên](review_packet.md), [mapping để audit](review_mapping.json), [inventory](inventory.json), [validation](validation.json).',
      '- Cách chạy: [README](../../README.md). API dùng theo [Ollama chat](https://docs.ollama.com/api/chat) và [tham số inference](https://docs.ollama.com/modelfile).',
      '',f'Hoàn tất inference lúc `{complete["completed_at"]}`. Không có lượt sinh sửa đáp án được dùng trong điểm tổng hợp.',
    ]
    (RUN/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Report:',RUN/'REPORT.md')

if __name__=='__main__':main()
