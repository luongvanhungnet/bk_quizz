"""Validate source-bound benchmark annotations and export reviewed CPT separately."""
import argparse
import copy
import json
from pathlib import Path
from contracts import load,write_once,file_hash
from dataset import pack_dataset


def validate_benchmark(rows,queue):
    if not rows:raise ValueError('No completed gold annotations')
    expected={r['page']:r for r in queue};seen=set()
    for r in rows:
        page=r.get('page')
        if page not in expected or page in seen:raise ValueError('Unknown/duplicate benchmark page')
        seen.add(page);source=expected[page]
        if any(r.get(k)!=source[k] for k in ['document_sha256','render_sha256','group_id','split']):raise ValueError('Benchmark source/split changed')
        if r.get('annotation_status')!='verified' or not r.get('reviewer') or not r.get('evidence'):raise ValueError('Incomplete benchmark review')
        gold=r.get('gold')
        if not isinstance(gold,dict) or not gold:raise ValueError('Missing gold is not a correct answer')
        if type(gold.get('contains_knowledge_visual')) is not bool:raise ValueError('Gold requires contains_knowledge_visual bool for routing audit')
        if type(gold.get('requires_vlm')) is not bool:raise ValueError('Gold requires requires_vlm bool; a formula/table need not require VLM')
        if not isinstance(gold.get('reference'),dict) or not gold['reference']:raise ValueError('Gold needs a source-checked component reference')
    return True


def routing_metrics(rows,queue):
    validate_benchmark(rows,queue);scheduled={r['page']:r['scheduled_vlm'] for r in queue};by_split={}
    for split in ['development','holdout']:
        subset=[r for r in rows if r['split']==split]
        tp=sum(r['gold']['requires_vlm'] and scheduled[r['page']] for r in subset)
        fp=sum(not r['gold']['requires_vlm'] and scheduled[r['page']] for r in subset)
        fn=sum(r['gold']['requires_vlm'] and not scheduled[r['page']] for r in subset)
        by_split[split]={'annotated':len(subset),'TP':tp,'FP':fp,'FN':fn,
                        'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None}
    return {'scope':'stratified_annotated_subset_not_population_weighted_estimate','splits':by_split}


def export_reviews(run,reviews,out):
    m=load(run/'manifest.json');groups=load(run/'benchmark_groups.json');protected=set(groups['protected_holdout_pages'])
    rows=[json.loads(l) for l in (run/'carried_cpt_archive/train.metadata.jsonl').read_text(encoding='utf-8').splitlines()]
    seen=set()
    for review in reviews:
        page=review.get('page')
        if type(page) is not int or page in seen or page in protected:raise ValueError('Duplicate or protected holdout page')
        seen.add(page)
        if review.get('document_sha256')!=m['document']['sha256'] or review.get('render_sha256')!=m['source_render_hashes'].get(str(page)):raise ValueError('Wrong transcript source')
        if review.get('review_type')!='source_verified_transcript' or review.get('verified') is not True or not review.get('reviewer') or not review.get('evidence'):
            raise ValueError('Explicit source-verified transcript required; model confidence is insufficient')
        if not isinstance(review.get('text'),str) or not review['text'].strip():raise ValueError('Empty transcript')
        rows=[r for r in rows if r['page']!=page]
        rows.append({'id':f"{m['document']['id']}:p{page:04d}",'page':page,'text':review['text'],
            'source':{'page':page,'document_sha256':review['document_sha256'],'render_sha256':review['render_sha256'],'pdf_path':m['document']['path']},'review':copy.deepcopy(review)})
    tokenizer=load(run/'cpt/manifest.json')['tokenizer_source']
    return pack_dataset(rows,out,tokenizer,protected)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['check-benchmark','export-cpt']);p.add_argument('--run',type=Path,required=True)
    p.add_argument('--reviews',type=Path,required=True);p.add_argument('--out',type=Path)
    a=p.parse_args();rows=[json.loads(l) for l in a.reviews.read_text(encoding='utf-8').splitlines() if l.strip()]
    if a.mode=='check-benchmark':
        metrics=routing_metrics(rows,[json.loads(l) for l in (a.run/'benchmark_queue.jsonl').read_text(encoding='utf-8').splitlines()])
        if a.out:write_once(a.out,metrics)
        print(json.dumps(metrics,ensure_ascii=True))
    else:
        if not a.out:raise ValueError('--out required')
        export_reviews(a.run,rows,a.out)
