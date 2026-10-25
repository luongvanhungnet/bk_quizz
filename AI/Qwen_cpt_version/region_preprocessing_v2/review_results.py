"""Import v2 Colab return for review, never export predictions into CPT."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from validation import validate_prediction
from semantic_eval import evaluate


def load(p):return json.loads(p.read_text(encoding='utf-8'))


def run(a):
    if a.out.exists():raise ValueError('Use a new review output path; do not overwrite audits')
    a.out.mkdir(parents=True)
    report={}
    with zipfile.ZipFile(a.results) as z:
        if z.testzip() is not None:raise ValueError('Corrupt ZIP')
        for size in ['3B','7B']:
            manifest_path=a.run/size/'manifest.json';m=load(manifest_path)
            results=json.loads(z.read(size+'/results.json'))
            if results['manifest_sha256']!=hashlib.sha256(manifest_path.read_bytes()).hexdigest():raise ValueError('Wrong manifest')
            requests={r['id']:r for r in m['requests']};records=results['records']
            if len({r['id'] for r in records})!=len(records) or {r['id'] for r in records}!=set(requests):raise ValueError('Missing/duplicate records')
            checked=[]
            for r in records:
                q=requests[r['id']]
                if r['engine']!=q['engine'] or r['cache_key']!=q['cache_key']:raise ValueError('Stale prediction')
                if r['status']!='not_run' and r.get('raw_pixel_sha256')!=q['raw_pixel_sha256']:raise ValueError('Wrong source pixels')
                errors=validate_prediction(q['engine'],r.get('prediction'))
                checked.append({'request':q,'result':r,'structural_errors':errors,
                    'semantic_verified':False,'destination':'review_queue'})
            (a.out/(size+'_prediction_review.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in checked),encoding='utf-8')
            diagnostic=evaluate(results,m,load(a.run/size/'gold_cases.json'))
            (a.out/(size+'_semantic_diagnostics.json')).write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2),encoding='utf-8')
            report[size]={'requests':len(records),'schema_ok':sum(r['result']['status']=='ok' and not r['structural_errors'] for r in checked),
                'new_verified_CPT_samples':0,'model':m['config']['vlm_model'],'note':'Schema and diagnostic metrics do not authorize CPT export'}
    report['archive_sha256']=hashlib.sha256(a.results.read_bytes()).hexdigest()
    (a.out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',required=True,type=Path);p.add_argument('--run',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    run(p.parse_args())
