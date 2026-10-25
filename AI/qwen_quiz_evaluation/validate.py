"""Validate evidence and score accounting without assuming all generations succeeded."""
import json
import math
import re
from build_suite import RUN,save,sha,independent_gold
from evaluate import objective

def load(name):return json.loads((RUN/name).read_text(encoding='utf-8'))

def marked_value(question):
    """Independent literal check; qualitative review still handles changed premises."""
    if not isinstance(question,dict):return None
    answer=question.get('answer');selected=answer
    if answer in ['A','B','C','D']:
        options=question.get('options')
        if not isinstance(options,list):return None
        selected=next((o.get('text') for o in options if isinstance(o,dict) and o.get('id')==answer),None)
    if not isinstance(selected,str):return None
    match=re.fullmatch(r'\s*(\d+)\s*(?:bit(?: có dấu)?|lần)?\s*',selected)
    if match:return int(match[1])
    if selected.strip().casefold().replace('–','-')=='bellman-ford':return 'Bellman-Ford'
    return None

def main():
    errors=[]
    def check(test,message):
        if not test:errors.append(message)
    protocol=load('protocol.json');cases=load('prompts.json');models=load('inventory.json')['models']
    complete=load('run_complete.json');reviews=load('reviews.json');scores=load('question_scores.json');summary=load('summary.json')
    mapping=load('review_mapping.json');packet=load('review_packet.json');checks=load('automatic_checks.json')
    for name,value in protocol['artifacts_sha256'].items():check(sha((RUN/name).read_text(encoding='utf-8'))==value,'Frozen artifact changed: '+name)
    check(load('gold.json')['facts']==independent_gold()['facts'],'Independent oracle changed')
    check(len({m['digest'] for m in models})==len(models),'Model digests not unique')
    expected=len(models)*len(cases);records={}
    for m in models:
        for case in cases:
            path=RUN/'responses'/m['eval_id']/f'{case["id"]}.json'
            check(path.exists(),'Missing response '+str(path))
            if not path.exists():continue
            r=json.loads(path.read_text(encoding='utf-8'));key=(m['eval_id'],case['id']);records[key]=r
            check(r['request']['messages']==case['messages'],'Messages differ '+str(key))
            check(r['messages_sha256']==case['messages_sha256'],'Message hash differs '+str(key))
            check(r['request']['options']==protocol['options'],'Runtime options differ '+str(key))
            check(r['request']['think'] is False and r['warmup'] is False,'Thinking/warmup mismatch '+str(key))
            check(r['model_digest']==m['digest'],'Model digest mismatch '+str(key))
            check(r['content_sha256']==sha(r['content']),'Content checksum differs '+str(key))
            check(r['request_sha256']==sha(json.dumps(r['request'],ensure_ascii=False,sort_keys=True,separators=(',',':'))),'Request checksum differs '+str(key))
            c=next((x for x in checks if x['eval_id']==key[0] and x['case_id']==key[1]),None)
            check(c is not None,'Missing automatic result '+str(key))
            if c:
                recomputed=objective(r,case)
                for field in ['strict_json','strict_schema','count_and_slots_ok','exact_evidence_count','rejection_ok']:
                    check(c[field]==recomputed[field],'Automatic metric mismatch '+str(key)+' '+field)
    expected_slots=len(models)*11
    check(len(records)==expected==complete['expected_responses'],'Request accounting mismatch')
    check(len(mapping)==len(packet)==len(scores)==expected_slots,'Expected slot accounting mismatch')
    check(len({r['question_id'] for r in scores})==expected_slots,'Duplicate scored IDs')
    mapped={r['question_id']:r for r in mapping};reviewed={r['question_id']:r for r in reviews}
    packed={r['question_id']:r for r in packet};gold=load('gold.json')['facts'];literal_checks=0
    rubric=load('rubric.json')
    for row in scores:
        link=mapped[row['question_id']];r=records[(link['eval_id'],link['case_id'])]
        case=next(c for c in cases if c['id']==link['case_id']);obj=objective(r,case)
        original_questions=obj['by_slot'].get(link['slot_id'],[])
        original=original_questions[0] if original_questions else None
        check(packed[row['question_id']]['question']==original,'Review packet differs from raw question '+row['question_id'])
        check(link['missing']==(original is None or r['status']!='ok'),'Missing status differs from raw output '+row['question_id'])
        check(link['content_sha256']==r['content_sha256'],'Mapping stale '+row['question_id'])
        check(row['question_id']=='Q'+sha(r['model_digest']+'|'+link['case_id']+'|'+link['slot_id'])[:12],'Question ID mismatch')
        if not link['missing']:
            review=reviewed.get(row['question_id'])
            check(review is not None and review['content_sha256']==r['content_sha256'],'Missing/stale qualitative review')
            if review:check(row['dimensions']==review['dimensions'],'Score dimensions differ from review '+row['question_id'])
            value=marked_value(packed[row['question_id']]['question'])
            if value is not None and row['dimensions']['correctness']==4:
                literal_checks+=1
                check(value==gold[row['slot_id']],'Correct grade conflicts with marked literal and oracle '+row['question_id'])
        points=sum(row['dimensions'][k]/v['max']*v['weight'] for k,v in rubric['dimensions'].items())
        check(abs(row['quality_score']-points)<.00011,'Weighted score mismatch')
        if link['missing']:check(row['quality_score']==0,'Missing question received points')
    for m in models:
        rows=[r for r in scores if r['eval_id']==m['eval_id']];s=next(x for x in summary if x['eval_id']==m['eval_id'])
        check(len(rows)==11,'Per-model denominator mismatch')
        check(abs(sum(r['quality_score'] for r in rows)/11-s['quality_mean_expected_slots'])<.0011,'Mean score mismatch')
        check(sum(r['dimensions']['correctness']==4 for r in rows)==s['correct_questions'],'Correct-answer count mismatch')
        check(sum(r['usable'] for r in rows)==s['usable_questions'],'Usable count mismatch')
    if (RUN/'temporary_server.json').exists():
        check((RUN/'temporary_server_stopped.json').exists(),'Owned temporary server not recorded as stopped')
        if (RUN/'temporary_server_stopped.json').exists():check(load('temporary_server.json')['pid']==load('temporary_server_stopped.json')['pid'],'Wrong temporary server cleanup identity')
    result={'passed':not errors,'errors':errors,'models':len(models),'requests':len(records),'expected_slots':expected_slots,
            'qualitative_reviews':len(reviews),'scored_missing_slots':sum(r['missing'] for r in scores),
            'correct_literal_answers_independently_checked':literal_checks,
            'checks':['frozen prompt/gold/rubric hashes','same messages/options for each model','raw content and model digest',
                      'objective metric recomputation','all expected slots including failures','source-bound qualitative reviews','correct marked literals versus independent oracle',
                      'weighted score recomputation','per-model denominators','temporary server cleanup identity']}
    save(RUN/'validation.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
    if errors:raise SystemExit(1)

if __name__=='__main__':main()
