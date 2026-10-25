"""Import an append-only Colab snapshot; recompute gates and keep all output in review."""
import argparse
from collections import Counter
import json
from pathlib import Path
import zipfile
from contracts import check_package,file_hash,load,write_once
from validation import validate_prediction
from quality import assess


def import_results(a):
    if a.out.exists():raise ValueError('Choose a fresh review directory')
    m=check_package(a.run);requests={r['id']:r for r in m['requests']};a.out.mkdir(parents=True)
    with zipfile.ZipFile(a.results) as z:
        if z.testzip():raise ValueError('Corrupt ZIP')
        snapshots=[(name,json.loads(z.read(name))) for name in z.namelist() if name.startswith('results_') and name.endswith('.json')]
        if not snapshots:raise ValueError('No v3 results snapshot')
        name,result=max(snapshots,key=lambda item:(sum(r['status']!='not_run' for r in item[1]['records']),item[0]))
        if result['manifest_sha256']!=file_hash(a.run/'manifest.json'):raise ValueError('Manifest mismatch')
        rows=result['records']
        if len(rows)!=len(requests) or {r['id'] for r in rows}!=set(requests):raise ValueError('Missing/duplicate requests')
        checked=[]
        for r in rows:
            q=requests[r['id']]
            if r.get('cache_key')!=q['cache_key'] or r['engine']!=q['engine']:raise ValueError('Wrong inference identity')
            if r['status']!='not_run' and r.get('input_file_sha256')!=q['input_file_sha256']:raise ValueError('Wrong source crop')
            errors=validate_prediction(q['engine'],r.get('prediction'))
            context=load(a.run/q['context']);context['_image_path']=str(a.run/q['image']);context['native_ocr']=q.get('native_ocr',[])
            quality=assess(q['engine'],r['prediction'],context) if not errors else {'flags':['invalid_or_missing_prediction'],'evidence_gate_pass':False}
            checked.append({'request':q,'result':r,'structural_errors':errors,'quality':quality,
                'semantic_verified':False,'destination':'review_queue'})
        (a.out/'prediction_review.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in checked),encoding='utf-8')
        write_once(a.out/'results.json',result)
        write_once(a.out/'summary.json',{'selected_snapshot':name,'archive_sha256':file_hash(a.results),
            'statuses':dict(Counter(r['result']['status'] for r in checked)),
            'heuristic_evidence_gate_pass':sum(r['result']['status']=='ok' and not r['structural_errors'] and r['quality']['evidence_gate_pass'] for r in checked),
            'flags':dict(Counter(flag for r in checked for flag in r['quality']['flags'])),
            'new_verified_CPT_samples':0,'note':'No automatic promotion or source correction.'})
    print(a.out)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--results',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    import_results(p.parse_args())
