"""Source-bound graph diagnostic metrics, never CPT approval."""
import argparse
from collections import Counter
import json
from pathlib import Path


def score(prediction,gold):
    labels=[n['label'] for n in prediction.get('nodes',[])]
    label_map={n['id']:n['label'] for n in prediction.get('nodes',[])}
    correct_labels=sum((Counter(labels)&Counter(gold['nodes'])).values())
    predicted=[]
    for e in prediction.get('edges',[]):
        if e['source'] not in label_map or e['target'] not in label_map:continue
        predicted.append((label_map[e['source']],label_map[e['target']],e))
    def pair(a,b):return tuple(sorted([a,b]))
    actual={pair(e['source'],e['target']):e for e in gold['edges']}
    pc=Counter(pair(a,b) for a,b,e in predicted)
    topology_correct=sum((pc&Counter(actual.keys())).values())
    weight_gold=[e for e in gold['edges'] if e.get('weight') is not None]
    weight_claims=[(a,b,e) for a,b,e in predicted if e.get('weight') is not None]
    weight_correct=set()
    direction_correct=set();highlight_correct=set()
    for a,b,e in predicted:
        k=pair(a,b);g=actual.get(k)
        if not g:continue
        if g.get('weight') is not None and str(e.get('weight'))==str(g['weight']):weight_correct.add(k)
        if g.get('directed') is not None and e.get('directed') is g['directed']:
            if not g['directed'] or (a,b)==(g['source'],g['target']):direction_correct.add(k)
        if g.get('highlighted') is not None and e.get('highlighted') is g['highlighted']:highlight_correct.add(k)
    return {'node_labels':{'correct':correct_labels,'predicted':len(labels),'gold':len(gold['nodes'])},
            'topology':{'correct':topology_correct,'predicted':len(prediction.get('edges',[])),'gold':len(actual)},
            'weights':{'correct':len(weight_correct),'predicted':len(weight_claims),'gold':len(weight_gold)},
            'directions':{'correct':len(direction_correct),'gold':sum(e.get('directed') is not None for e in gold['edges'])},
            'highlights':{'correct':len(highlight_correct),'gold':sum(e.get('highlighted') is not None for e in gold['edges'])},
            'duplicate_visible_labels':len(labels)-len(set(labels)),
            'semantic_verified':False}


def evaluate(results,manifest,golds):
    requests={r['id']:r for r in manifest['requests']};out=[]
    for r in results['records']:
        if r['engine']!='vlm':continue
        q=requests[r['id']];gold=next((g for g in golds if g['page']==q['page']),None)
        if not gold:continue
        for key in ['document_sha256','render_sha256','input_file_sha256']:
            if gold[key]!=q[key]:raise ValueError('Gold/source identity mismatch')
        item={'id':r['id'],'page':q['page'],'inference_status':r['status']}
        if gold.get('manual_only'):
            item.update(manual_review_required=True,rubric=gold['rubric'],metrics=None)
        elif isinstance(r.get('prediction'),dict):item['metrics']=score(r['prediction'],gold)
        else:item.update(metrics=None,reason='missing_prediction')
        out.append(item)
    return {'scope':'agent_visual_gold_diagnostic_not_independent_benchmark',
            'model':manifest['config']['vlm_model'],'rows':out,'semantic_verified':False}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--gold',type=Path,default=Path(__file__).with_name('gold_cases.json'));p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=evaluate(json.loads(a.results.read_text(encoding='utf-8')),json.loads(a.manifest.read_text(encoding='utf-8')),json.loads(a.gold.read_text(encoding='utf-8')))
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
