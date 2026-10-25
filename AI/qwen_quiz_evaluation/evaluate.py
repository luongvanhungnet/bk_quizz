"""Separate deterministic format/provenance checks from qualitative answer review."""
from __future__ import annotations
import argparse
import collections
import csv
import json
import random
import re
from pathlib import Path
from build_suite import RUN,save,sha

QUESTION_KEYS={'slot_id','difficulty','question','options','answer','explanation','source_id','evidence_quote'}

def parse(content):
    def reject_nonfinite(value):raise ValueError('Non-JSON number '+value)
    try:return json.loads(content,parse_constant=reject_nonfinite),True,'strict_json'
    except (ValueError,TypeError):pass
    # Recovery is for inspecting content only, never retroactively makes strict JSON pass.
    decoder=json.JSONDecoder(parse_constant=reject_nonfinite)
    for match in re.finditer(r'\{',content):
        try:
            value,_=decoder.raw_decode(content[match.start():])
            if isinstance(value,dict) and 'questions' in value:return value,False,'recovered_object'
        except ValueError:pass
    return None,False,'unparseable'

def question_schema(q,case):
    errors=[]
    if not isinstance(q,dict):return ['not_an_object']
    if set(q)!=QUESTION_KEYS:errors.append('question_keys')
    for field in QUESTION_KEYS-{'options'}:
        if not isinstance(q.get(field),str) or not q[field].strip():errors.append(field+'_empty_or_type')
    if not isinstance(q.get('difficulty'),str) or q['difficulty'] not in {'EASY','MEDIUM','HARD'}:errors.append('difficulty_enum')
    options=q.get('options')
    if not isinstance(options,list) or len(options)!=4:errors.append('four_options')
    else:
        if not all(isinstance(o,dict) and set(o)=={'id','text'} and isinstance(o.get('text'),str) and o['text'].strip() for o in options):errors.append('option_schema')
        ids=[o.get('id') if isinstance(o,dict) else None for o in options]
        if ids!=list('ABCD'):errors.append('option_ids')
        texts=[o.get('text','').strip().casefold() if isinstance(o,dict) and isinstance(o.get('text'),str)
               else o.strip().casefold() if isinstance(o,str) else '' for o in options]
        if len(set(texts))!=4:errors.append('duplicate_option_text')
    if q.get('answer') not in list('ABCD'):errors.append('answer_id')
    if not isinstance(q.get('slot_id'),str) or q['slot_id'] not in {s['slot_id'] for s in case['slots']}:errors.append('unknown_slot')
    return errors

def objective(record,case):
    parsed,strict,mode=parse(record.get('content',''))
    data=parsed if isinstance(parsed,dict) else {}
    qs=data.get('questions',[]);qs=qs if isinstance(qs,list) else []
    rejected=data.get('rejected',[]);rejected=rejected if isinstance(rejected,list) else []
    expected={s['slot_id']:s for s in case['slots'] if s['slot_id']!='unsupported_runtime'}
    by_slot=collections.defaultdict(list)
    for q in qs:
        if isinstance(q,dict):by_slot[q.get('slot_id') if isinstance(q.get('slot_id'),str) else '__invalid_slot__'].append(q)
    root_valid=isinstance(parsed,dict) and set(parsed)=={'questions','rejected'} and isinstance(parsed.get('questions'),list) and isinstance(parsed.get('rejected'),list)
    root_valid=root_valid and all(isinstance(r,dict) and set(r)=={'slot_id','reason'} and isinstance(r.get('slot_id'),str) and r.get('reason')=='INSUFFICIENT_CONTEXT' for r in rejected)
    schemas=[question_schema(q,case) for q in qs]
    schema_ok=bool(strict and root_valid and all(not x for x in schemas))
    count_ok=len(qs)==len(expected) and set(by_slot)==set(expected) and all(len(v)==1 for v in by_slot.values())
    quote_ok=[isinstance(q,dict) and q.get('source_id')==case['source_id'] and isinstance(q.get('evidence_quote'),str) and bool(q['evidence_quote'].strip()) and q['evidence_quote'] in case['source'] for q in qs]
    required_reject=case['id']=='P06'
    rejection_ok=(any(r.get('slot_id')=='unsupported_runtime' and r.get('reason')=='INSUFFICIENT_CONTEXT' for r in rejected if isinstance(r,dict)) and not by_slot.get('unsupported_runtime')) if required_reject else None
    return {'strict_json':strict,'parse_mode':mode,'strict_schema':schema_ok,'schema_errors':schemas,
            'question_count':len(qs),'count_and_slots_ok':count_ok,'exact_evidence_count':sum(quote_ok),
            'rejection_ok':rejection_ok,'root_valid':root_valid,'questions':qs,'by_slot':dict(by_slot),
            'finish_reason':record.get('response_metadata',{}).get('done_reason'),
            'unexpected_rejections':[r for r in rejected if isinstance(r,dict) and isinstance(r.get('slot_id'),str) and r['slot_id'] in expected]}

def prepare():
    models=json.loads((RUN/'inventory.json').read_text(encoding='utf-8'))['models']
    cases=json.loads((RUN/'prompts.json').read_text(encoding='utf-8'));gold=json.loads((RUN/'gold.json').read_text(encoding='utf-8'))
    packet=[];mapping=[];checks=[]
    for m in models:
        for case in cases:
            path=RUN/'responses'/m['eval_id']/f'{case["id"]}.json'
            if not path.exists():continue
            record=json.loads(path.read_text(encoding='utf-8'))
            obj=objective(record,case)
            checks.append({'model':m['name'],'eval_id':m['eval_id'],'case_id':case['id'],'status':record['status'],
                           **{k:v for k,v in obj.items() if k not in {'questions','by_slot'}},
                           'elapsed_seconds':record['elapsed_seconds'],'time_to_first_token_seconds':record.get('time_to_first_token_seconds'),
                           'eval_count':record.get('response_metadata',{}).get('eval_count'),
                           'eval_duration_ns':record.get('response_metadata',{}).get('eval_duration'),
                           'thinking_characters':len(record.get('thinking','')),'content_sha256':record.get('content_sha256')})
            for slot in case['slots']:
                if slot['slot_id']=='unsupported_runtime':continue
                qid='Q'+sha(m['digest']+'|'+case['id']+'|'+slot['slot_id'])[:12]
                items=obj['by_slot'].get(slot['slot_id'],[])
                q=items[0] if items else None
                packet.append({'question_id':qid,'case_id':case['id'],'slot':slot,'gold_value':gold['facts'][slot['slot_id']],
                               'source_id':case['source_id'],'source':case['source'],'question':q,
                               'request_status':record['status'],
                               'automatic_schema_errors':question_schema(q,case) if q is not None else ['missing_question'],
                               'strict_json':obj['strict_json']})
                mapping.append({'question_id':qid,'model':m['name'],'eval_id':m['eval_id'],'case_id':case['id'],
                                'slot_id':slot['slot_id'],'content_sha256':record['content_sha256'],
                                'missing':q is None or record['status']!='ok'})
    random.Random(731).shuffle(packet)
    save(RUN/'review_packet.json',packet);save(RUN/'review_mapping.json',mapping);save(RUN/'automatic_checks.json',checks)
    text=['# Shuffled review packet','','Model names are omitted. Missing slots receive zero automatically.','']
    for p in packet:
        text += [f'## {p["question_id"]} — {p["case_id"]} / {p["slot"]["slot_id"]}',
                 f'Gold: {p["gold_value"]}; requested difficulty: {p["slot"]["difficulty"]}',
                 '```json',json.dumps(p['question'],ensure_ascii=False,indent=2),'```','']
    (RUN/'review_packet.md').write_text('\n'.join(text),encoding='utf-8')
    print(f'Prepared {len(packet)} expected questions from {len(checks)} responses; missing {sum(p["question"] is None for p in packet)}')

def score():
    rubric=json.loads((RUN/'rubric.json').read_text(encoding='utf-8'))
    reviews=json.loads((RUN/'reviews.json').read_text(encoding='utf-8'))
    mapping=json.loads((RUN/'review_mapping.json').read_text(encoding='utf-8'))
    packet={r['question_id']:r for r in json.loads((RUN/'review_packet.json').read_text(encoding='utf-8'))}
    checks=json.loads((RUN/'automatic_checks.json').read_text(encoding='utf-8'))
    reviewed={r['question_id']:r for r in reviews};results=[]
    for link in mapping:
        qid=link['question_id'];p=packet[qid]
        if link['missing']:
            dimensions={k:0 for k in rubric['dimensions']};notes='Slot thiếu hoặc không có object quiz hoàn tất để chấm; nhận 0 trong mẫu số gồm mọi slot được yêu cầu.'
        else:
            if qid not in reviewed:raise ValueError('Unreviewed question: '+qid)
            review=reviewed[qid]
            if review.get('content_sha256')!=link['content_sha256']:raise ValueError('Stale review: '+qid)
            dimensions=review['dimensions'];notes=review['notes']
        if set(dimensions)!=set(rubric['dimensions']):raise ValueError('Incorrect dimension set '+qid)
        points=0
        for key,rule in rubric['dimensions'].items():
            val=dimensions[key]
            if not isinstance(val,(int,float)) or not 0<=val<=rule['max']:raise ValueError('Invalid grade '+qid)
            points+=val/rule['max']*rule['weight']
        check=next(r for r in checks if r['eval_id']==link['eval_id'] and r['case_id']==link['case_id'])
        strict=check['status']=='ok' and check['strict_json'] and not p['automatic_schema_errors'] and check['root_valid']
        d=dimensions
        usable=bool(strict and d['correctness']==4 and d['single_answer']==2 and d['grounding']>=2 and
                    d['explanation']>=2 and d['clarity']>=1 and d['adherence']==2)
        results.append({**link,'dimensions':dimensions,'quality_score':round(points,4),'usable':usable,'notes':notes})
    save(RUN/'question_scores.json',results)
    models=json.loads((RUN/'inventory.json').read_text(encoding='utf-8'))['models'];summary=[]
    import statistics
    for m in models:
        rows=[r for r in results if r['eval_id']==m['eval_id']];cs=[c for c in checks if c['eval_id']==m['eval_id']]
        ok=[c for c in cs if c['status']=='ok'];total_tok=sum(c['eval_count'] or 0 for c in ok)
        duration=sum(c['eval_duration_ns'] or 0 for c in ok)/1e9
        generated=[r for r in rows if not r['missing']]
        summary.append({'model':m['name'],'eval_id':m['eval_id'],'digest':m['digest'],
             'parameter_size':m.get('details',{}).get('parameter_size'),'quantization':m.get('details',{}).get('quantization_level'),
             'requests':len(cs),'successes':len(ok),'strict_json':sum(c['strict_json'] for c in cs),
             'strict_schema':sum(c['strict_schema'] for c in cs),'correct_count_requests':sum(c['count_and_slots_ok'] for c in cs),
             'expected_questions':len(rows),'generated_expected_slots':len(generated),
             'correct_questions':sum(r['dimensions']['correctness']==4 for r in rows),
             'quality_mean_expected_slots':round(statistics.mean(r['quality_score'] for r in rows),3),
             'quality_mean_generated':round(statistics.mean(r['quality_score'] for r in generated),3) if generated else None,
             'usable_questions':sum(r['usable'] for r in rows),'exact_evidence':sum(c['exact_evidence_count'] for c in cs),
             'generated_questions_total':sum(c['question_count'] for c in cs),
             'refusal_success':next((c['rejection_ok'] for c in cs if c['case_id']=='P06'),None),
             'unsupported_refusals_of_valid_slots':sum(len(c['unexpected_rejections']) for c in cs),
             'truncated_responses':sum(c['finish_reason']=='length' for c in cs),
             'mean_latency_seconds':round(statistics.mean(c['elapsed_seconds'] for c in cs),3),
             'median_latency_seconds':round(statistics.median(c['elapsed_seconds'] for c in cs),3),
             'generation_tokens_per_second':round(total_tok/duration,3) if duration else None})
    save(RUN/'summary.json',summary)
    with (RUN/'summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(summary[0]));writer.writeheader();writer.writerows(summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','score']);a=p.parse_args()
    prepare() if a.action=='prepare' else score()
