"""Recompute the original rubric and report from completed, hash-bound reviews.

Does not generate model answers or automatically invent qualitative grades.
"""
import argparse
import hashlib
import json
from pathlib import Path
from compare_exports import BENCH,load
import evaluate
import validate


def main(run):
    run=run.resolve()
    if not (run/'reviews.json').is_file():
        raise ValueError('Complete source-and-oracle reviews.json before scoring')
    evaluate.RUN=run
    validate.RUN=run
    evaluate.score()
    validate.main()
    summary=load(run/'summary.json');rows=load(run/'question_scores.json')
    rubric=load(run/'rubric.json');cases=load(run/'prompts.json')
    packet={r['question_id']:r for r in load(run/'review_packet.json')}
    before,after=summary
    delta=after['quality_mean_expected_slots']-before['quality_mean_expected_slots']
    text=['# Chấm điểm Qwen3 trước và sau CPT theo rubric cũ','',
          'Ngày chấm: 2026-10-18. Dùng 12 response đã lưu của đợt `ollama_pair_001`; không sinh lại, sửa hoặc retry câu trả lời.','',
          f"**Model gốc: {before['quality_mean_expected_slots']:.2f}/100. Model CPT: {after['quality_mean_expected_slots']:.2f}/100. Chênh lệch: {delta:+.2f} điểm.**",'',
          'Điểm tổng gần như ngang nhau. CPT hoàn tất JSON và các slot tốt hơn, nhưng số đáp án đúng không tăng và số câu qua cổng dùng được giảm từ 1 xuống 0. Chưa có bằng chứng chất lượng sinh quiz tăng sau CPT.','',
          '## Phương pháp','',
          'Tái sử dụng chính `evaluate.py`, `validate.py` và rubric v1.0 của đợt đánh giá trước. Mỗi model có 6 prompt và 11 slot có đủ dữ kiện. Điểm model là trung bình điểm của cả 11 slot; slot thiếu hoặc JSON cắt dở không khôi phục được nhận 0. Slot thiếu dữ kiện `unsupported_runtime` chấm hành vi từ chối riêng, không thêm vào mẫu số hay điểm /100.','',
          'Điểm câu = tổng (điểm tiêu chí / mức tối đa × trọng số). Không cho điểm đáp án chỉ vì lời giải có nhắc kết quả đúng: phải xét option mà answer thực sự trỏ tới.','',
          '| Tiêu chí | Thang điểm | Trọng số |','|---|---:|---:|']
    labels={'correctness':'Đáp án đúng','single_answer':'Một lựa chọn đúng','grounding':'Bám nguồn',
            'explanation':'Lời giải','distractors':'Nhiễu','clarity':'Rõ ràng','adherence':'Tuân thủ'}
    for k,v in rubric['dimensions'].items():text.append(f"| {labels[k]} | 0–{v['max']} | {v['weight']}% |")
    text += ['',
        'Cổng dùng được giữ nguyên: response thành công, JSON strict, đúng schema của câu và root; correctness=4, single_answer=2, grounding≥2, explanation≥2, clarity≥1, adherence=2. Điểm /100 và việc qua cổng là hai kết quả khác nhau.','',
        'Codex chấm nội dung theo nguồn và oracle; danh tính model đã được nhìn thấy, vì vậy đây không phải đánh giá mù hoặc đánh giá bởi chuyên gia độc lập. Toàn bộ nội dung baseline trùng SHA256 với lượt cũ, nên tái sử dụng đúng điểm và nhận xét cũ để tránh đổi chuẩn chấm. CPT được đọc và chấm từng câu.','',
        '## Kết quả tổng hợp','',
        '| Chỉ số | Gốc | CPT |','|---|---:|---:|']
    metrics=[('Điểm rubric /100','quality_mean_expected_slots',None),('Request thành công /6','successes',6),
             ('JSON strict /6','strict_json',6),('Schema hợp lệ /6','strict_schema',6),
             ('Đúng số câu và slot /6','correct_count_requests',6),('Slot hợp lệ được sinh /11','generated_expected_slots',11),
             ('Đáp án đúng /11','correct_questions',11),('Câu qua cổng dùng được /11','usable_questions',11),
             ('Quote nguyên văn /tổng câu sinh','exact_evidence','quotes'),('Response bị cắt','truncated_responses',None),
             ('Từ chối đúng slot thiếu dữ kiện','refusal_success',None)]
    for label,key,denominator in metrics:
        values=[]
        for s in summary:
            value=s[key]
            if key=='quality_mean_expected_slots':value=f'{value:.2f}'
            elif isinstance(value,bool):value='Có' if value else 'Không'
            if denominator=='quotes':value=f"{value}/{s['generated_questions_total']}"
            elif denominator:value=f'{value}/{denominator}'
            values.append(str(value))
        text.append(f"| {label} | {' | '.join(values)} |")
    text += ['', '## Điểm theo tiêu chí đã quy đổi trọng số','',
             '| Tiêu chí | Điểm tối đa | Gốc | CPT |','|---|---:|---:|---:|']
    for key,rule in rubric['dimensions'].items():
        means=[sum(r['dimensions'][key]/rule['max']*rule['weight'] for r in rows if r['eval_id']==s['eval_id'])/11 for s in summary]
        text.append(f"| {labels[key]} | {rule['weight']} | {means[0]:.2f} | {means[1]:.2f} |")
    text += ['', '## Điểm từng slot','', '| Prompt / slot | Chuẩn | Gốc /100 | CPT /100 |','|---|---|---:|---:|']
    for a in [r for r in rows if r['eval_id']=='before']:
        b=next(r for r in rows if r['eval_id']=='after' and r['slot_id']==a['slot_id'])
        text.append(f"| {a['case_id']} / {a['slot_id']} | {packet[a['question_id']]['gold_value']} | {a['quality_score']:.2f} | {b['quality_score']:.2f} |")
    text += ['', '## Những thay đổi đáng chú ý','',
        '- P04: baseline bị cắt dở, mất cả hai slot. CPT xuất đủ hai câu nhưng ba lô chọn 9 thay vì 7; LCS chọn 3 thay vì 4. Hoàn tất JSON làm tăng điểm độ phủ, chưa chứng minh giải toán tốt hơn.',
        '- P02: CPT sửa key đệ quy thành 15, nhưng lời giải tính ra 12 rồi tự mâu thuẫn. Ở vòng lặp, lời giải tính đúng 10 nhưng lại chọn B=11, làm mất một đáp án đúng.',
        '- P05: cả hai chọn đúng 64 bit nhưng đều giải thích sai sang 128 bit. CPT còn viết Bellman-Ford bảo đảm đường đi ngắn nhất khi có chu trình âm; câu này mất cổng dùng được vốn baseline đạt.',
        '- P06: cả hai nhận biết thiếu dữ kiện thời gian chạy trong lời giải, nhưng vẫn sinh quiz cho unsupported_runtime thay vì trả rejected theo hợp đồng. Không chấm thành công từ chối chỉ vì có câu “không thể xác định”.','',
        '## Điều kiện và giới hạn','',
        'Cùng messages, seed=42, temperature=0, think=false, context=4096, giới hạn 1400 token, CPU 4 luồng, num_gpu=0, Q4_K_M và cùng template/default parameters. Hash response, model digest, oracle, công thức tính điểm và mẫu số đã được validate lại; xem validation.json.','',
        'Đây là 6 prompt tổng hợp trong miền học phần, mỗi model chạy một lượt; không phải tập held-out độc lập và không đủ để khẳng định khác biệt có ý nghĩa thống kê. Mức tăng 0,23 điểm không phải bằng chứng CPT tốt hơn.','',
        'Cùng tag dòng Qwen3 và lượng tử hóa chưa chứng minh cùng revision HF ban đầu. Metadata parameter_count trong snapshot cũng khác: baseline 2.031.739.904, CPT 1.720.574.976; chưa xác minh nguyên nhân cách đếm/biểu diễn tensor. Vì vậy kết quả là so sánh hai bản triển khai thực tế; không quy toàn bộ chênh lệch cho CPT. Cặp NF4 cùng revision trước/sau trên Colab là đối chứng phù hợp hơn để cô lập tác động train.','',
        '## Nhận xét từng câu và bằng chứng','']
    for s in summary:
        text += [f"### {s['model']}",'']
        for r in [x for x in rows if x['eval_id']==s['eval_id']]:
            p=packet[r['question_id']]
            dims=', '.join(f'{labels[k]}={v}/{rubric["dimensions"][k]["max"]}' for k,v in r['dimensions'].items())
            text += [f"#### {r['case_id']} / {r['slot_id']} — {r['quality_score']:.2f}/100",'',
                     f"Chuẩn: **{p['gold_value']}**. Qua cổng dùng được: **{'Có' if r['usable'] else 'Không'}**.",'',dims,'',r['notes'],'',
                     f"[Response gốc](../responses/{r['eval_id']}/{r['case_id']}.json). SHA256: `{r['content_sha256']}`.",'']
    text += ['## Tái lập việc tính điểm','',
             '```powershell',f'python AI\\Qwen_cpt_version\\local_qwen3\\score_pair.py --run "{run}"','```','',
             'Script chỉ tính lại điểm từ reviews.json đã chấm, kiểm định bằng evaluator cũ và dựng báo cáo; không tự chấm nội dung hay gọi model.','',
             'Artifact: [reviews.json](reviews.json), [question_scores.json](question_scores.json), [summary.csv](summary.csv), [rubric.json](rubric.json), [validation.json](validation.json). Nguồn và đáp án từng câu nằm trong [review_packet.json](review_packet.json); output đầy đủ đặt cạnh nhau trong [báo cáo kiểm tra tự động](../comparison/REPORT.md).','']
    (run/'REPORT_100.md').write_text('\n'.join(text),encoding='utf-8')
    identity={str(p.relative_to(run)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [run/'reviews.json',run/'rubric.json',run/'prompts.json',run/'gold.json',run/'question_scores.json',run/'summary.json',run/'REPORT_100.md']}
    (run/'scoring_artifacts_sha256.json').write_text(json.dumps(identity,indent=2),encoding='utf-8')
    print('Report:',run/'REPORT_100.md')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',type=Path,required=True)
    main(parser.parse_args().run)
