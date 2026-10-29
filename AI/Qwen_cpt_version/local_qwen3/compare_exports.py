"""Review paired Colab or Ollama exports without inventing qualitative scores."""
import argparse
import csv
import hashlib
import json
import re
import statistics
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BENCH=ROOT.parents[1]/'qwen_quiz_evaluation'
sys.path.insert(0,str(BENCH))
from evaluate import objective
from validate import marked_value

PROBES=ROOT.parent/'colab_qwen3_1_7b/probes'
def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def analyze(export,cases,gold):
    ids=[r['case_id'] for r in export['results']]
    if len(ids)!=len(set(ids)) or set(ids)!={c['id'] for c in cases}:raise ValueError('Need each of the six cases exactly once')
    rows=[];checks=[]
    for case in cases:
        r=next(x for x in export['results'] if x['case_id']==case['id'])
        if r['messages_sha256']!=case['messages_sha256']:raise ValueError('Prompt hash mismatch')
        ok=r.get('request_status','ok')=='ok'
        obj=objective({'content':r['content'] if ok else ''},case);checks.append(obj)
        for slot in case['slots']:
            if slot['slot_id']=='unsupported_runtime':continue
            questions=obj['by_slot'].get(slot['slot_id'],[]);q=questions[0] if questions else None
            value=marked_value(q)
            rows.append({'case_id':case['id'],'slot_id':slot['slot_id'],
                         'oracle':gold[slot['slot_id']],'marked_literal':value,
                         'literal_match':value is not None and value==gold[slot['slot_id']],
                         'missing':q is None})
    summary={'strict_json':sum(x['strict_json'] for x in checks),'strict_schema':sum(x['strict_schema'] for x in checks),
             'count_and_slots_ok':sum(x['count_and_slots_ok'] for x in checks),
             'literal_key_matches':sum(r['literal_match'] for r in rows),'expected_slots':len(rows),
             'missing':sum(r['missing'] for r in rows),'exact_evidence':sum(x['exact_evidence_count'] for x in checks),
             'refusal_success':next(x['rejection_ok'] for c,x in zip(cases,checks) if c['id']=='P06'),
             'mean_seconds':statistics.mean(r['seconds'] for r in export['results'])}
    return summary,rows


def compare(before_path,after_path,out):
    before=load(before_path);after=load(after_path);cases=load(PROBES/'prompts.json');gold=load(PROBES/'gold.json')['facts']
    for key in ['model_id','revision','config','prompts_sha256','quantization','compute_dtype']:
        if before[key]!=after[key]:raise ValueError('Unmatched comparison setting: '+key)
    if before['prompts_sha256']!=hashlib.sha256((PROBES/'prompts.json').read_bytes()).hexdigest():
        raise ValueError('Exports use a different prompt suite')
    if before.get('adapter') is not None or not after.get('adapter'):
        raise ValueError('Expected baseline without adapter, then CPT result')
    if out.exists() and any(out.iterdir()):raise ValueError('Choose a new output directory to preserve existing reports')
    out.mkdir(parents=True,exist_ok=True)
    identity={'before_sha256':hashlib.sha256(before_path.read_bytes()).hexdigest(),
              'after_sha256':hashlib.sha256(after_path.read_bytes()).hexdigest(),
              'prompts_sha256':before['prompts_sha256'],
              'settings':{k:before[k] for k in ['model_id','revision','config','quantization','compute_dtype']}}
    (out/'comparison_identity.json').write_text(json.dumps(identity,ensure_ascii=False,indent=2),encoding='utf-8')
    summaries={};rows=[]
    for name,export in [('before',before),('after',after)]:
        summaries[name],items=analyze(export,cases,gold)
        rows.extend({'variant':name,**r} for r in items)
    (out/'summary.json').write_text(json.dumps(summaries,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'slots.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    lines=['# So sánh Qwen3 1.7B trước/sau CPT','',
           'Cùng bộ sáu prompt và cấu hình khai báo. Đây là regression probe trong miền học phần, không phải held-out evaluation.','',
           '| Biến thể | JSON /6 | Schema /6 | Đủ slot /6 | Key literal khớp oracle /11 | Slot thiếu | Từ chối đúng |',
           '|---|---:|---:|---:|---:|---:|---|']
    for name,s in summaries.items():
        lines.append(f'| {name} | {s["strict_json"]} | {s["strict_schema"]} | {s["count_and_slots_ok"]} | {s["literal_key_matches"]} | {s["missing"]} | {s["refusal_success"]} |')
    lines+=['','**Key literal khớp oracle không phải điểm chất lượng quiz**: chưa xác minh model giữ đúng đề bài, một đáp án duy nhất, lời giải và dữ kiện đầy đủ. Không tự gán điểm rubric hay kết luận CPT tốt hơn từ chỉ số này.',
            'Thời gian chỉ so được khi phần cứng, backend và chế độ chạy tương ứng; file Colab cũ không lưu đủ metadata GPU để chứng minh điều đó.','',
            'Đối với cặp Ollama, cùng Q4_K_M/template vẫn chưa chứng minh checkpoint gốc của tag giống hệt revision HF dùng để train. Cặp NF4 trước/sau trên Colab kiểm soát nguồn trọng số tốt hơn.','',
            f'Nguồn trước: `{before_path.resolve()}`',f'Nguồn sau: `{after_path.resolve()}`','',
            '## Output từng prompt để chấm nội dung','']
    for case in cases:
        lines += ['### '+case['id']+' — '+case['topic'],'','Nguồn:','```text',case['source'],'```','',
                  'Oracle: '+json.dumps({s['slot_id']:gold[s['slot_id']] for s in case['slots']},ensure_ascii=False),'']
        for name,export in [('Trước CPT',before),('Sau CPT',after)]:
            r=next(x for x in export['results'] if x['case_id']==case['id'])
            fence='`'*(max([len(m.group()) for m in re.finditer(r'`+',r['content'])]+[2])+1)
            lines += ['**'+name+'**','', fence+'text',r['content'],fence,'']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summaries,ensure_ascii=False,indent=2));print('Report:',out/'REPORT.md')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--before',type=Path,required=True)
    p.add_argument('--after',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();compare(a.before,a.after,a.out)
