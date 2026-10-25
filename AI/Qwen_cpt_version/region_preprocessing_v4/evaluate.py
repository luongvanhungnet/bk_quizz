"""Compare same source graph crops to old diagnostic gold; never score missing gold."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import importlib.util
from contracts import load,write_once,check_package,file_hash


def reference_metrics(annotations,queue,requests,records,native_pages):
    from annotations import validate_benchmark,routing_metrics
    from quality import GridParser,canonical
    from validation import validate_prediction
    validate_benchmark(annotations,queue)
    def distance(a,b):
        row=list(range(len(b)+1))
        for i,x in enumerate(a,1):
            nxt=[i]
            for j,y in enumerate(b,1):nxt.append(min(nxt[-1]+1,row[j]+1,row[j-1]+(x!=y)))
            row=nxt
        return row[-1]
    scored=[]
    for annotation in annotations:
        page=annotation['page'];ref=annotation['gold']['reference'];item={'page':page,'split':annotation['split'],'regions':[]}
        if isinstance(ref.get('text'),str):
            source=canonical(ref['text']);hyp=canonical('\n'.join(b['text'] for b in native_pages[page]['blocks']))
            item['native_text']={'CER':distance(source,hyp)/len(source) if source else None,
                                 'WER':distance(source.split(),hyp.split())/len(source.split()) if source.split() else None,
                                 'scope':'whole native page blocks, NFC/collapsed whitespace'}
        for region in ref.get('regions',[]):
            q=requests.get(region['request_id'])
            if q is None or q['page']!=page or region.get('input_file_sha256')!=q['input_file_sha256']:raise ValueError('Region reference/crop mismatch')
            prediction=records.get(q['id'],{}).get('prediction');component={'id':q['id'],'kind':q['kind']}
            if not isinstance(prediction,dict) or validate_prediction(q['engine'],prediction):component.update(correct=False,reason='missing_or_invalid_output')
            elif q['engine']=='formula':
                component.update(latex_exact=canonical(prediction.get('latex',''))==canonical(region['latex']),
                                 note='String exactness, not algebraic/semantic equivalence')
            elif q['engine']=='table':
                def grid(html):
                    parser=GridParser();parser.feed(html)
                    if not parser.rows:raise ValueError('Table reference/output has no rows')
                    return [[(canonical(c['text']),c['rowspan'],c['colspan']) for c in row] for row in parser.rows]
                component['table_cells_and_spans_exact']=grid(prediction.get('html',''))==grid(region['html'])
            elif q['kind']=='state_tree':
                gold=region['state_tree']
                if validate_prediction('vlm',{'image_type':'state_tree',**gold}):raise ValueError('Invalid state-tree gold')
                def iou(a,b):
                    area=lambda x:max(0,x[2]-x[0])*max(0,x[3]-x[1])
                    inter=area([max(a[0],b[0]),max(a[1],b[1]),min(a[2],b[2]),min(a[3],b[3])])
                    return inter/max(1,area(a)+area(b)-inter)
                unused={s['id']:s for s in gold['states']};mapping={};correct=0
                for state in prediction['states']:
                    ranked=sorted(((iou(state['bbox'],g['bbox']),key) for key,g in unused.items()),reverse=True)
                    if not ranked or ranked[0][0]<.5:continue
                    _,key=ranked[0];g=unused.pop(key);mapping[state['id']]=key
                    if state['board_size']==g['board_size'] and {tuple(c) for c in state['queens']}=={tuple(c) for c in g['queens']} and {tuple(c) for c in state['removed_cells']}=={tuple(c) for c in g['removed_cells']}:correct+=1
                gp={(e['parent'],e['child']) for e in gold['relations']}
                pp={(mapping.get(e['parent']),mapping.get(e['child'])) for e in prediction['relations']}
                component.update(complete_board_states_correct=correct,gold_states=len(gold['states']),predicted_states=len(prediction['states']),
                                 branch_correct=len(gp&pp),gold_branches=len(gp))
            elif q['kind'] in ['graph','diagram','flowchart']:
                from semantic_eval import score
                component['graph']=score(projection(prediction),region['graph'])
            else:component.update(manual_review_required=True)
            item['regions'].append(component)
        scored.append(item)
    return {'routing':routing_metrics(annotations,queue),'components':scored,
            'note':'Report dev and holdout separately; missing/pending gold is not an accuracy score.'}


def projection(p):
    return {'nodes':[{'id':n['id'],'label':n['label']} for n in p['nodes']],
        'edges':[{'source':e['source'],'target':e['target'],**{k:e['attributes'][k] for k in ['weight','directed','highlighted']}} for e in p['edges']]}


def evaluate(a):
    m=check_package(a.run);result=load(a.results)
    if result['manifest_sha256']!=file_hash(a.run/'manifest.json'):raise ValueError('Wrong result manifest')
    root=Path(__file__).resolve().parents[1];v2=root/'region_preprocessing_v2'
    # Reuse the prior metric definition, not a new metric chosen after the run.
    spec=importlib.util.spec_from_file_location('semantic_eval',v2/'semantic_eval.py')
    module=importlib.util.module_from_spec(spec);sys.modules['semantic_eval']=module;spec.loader.exec_module(module);score=module.score
    gold=load(v2/'gold_cases.json');requests={r['id']:r for r in m['requests']};rows=[]
    for r in result['records']:
        q=requests[r['id']]
        if q['engine']!='vlm' or q['page'] not in m['pilot_pages']:continue
        g=next(g for g in gold if g['page']==q['page']);item={'id':r['id'],'page':q['page'],'status':r['status']}
        if q['kind']=='state_tree':item.update(metrics=None,reason='Board/branch inventory still requires source annotation; do not score generic labels')
        elif r.get('status')=='ok' and isinstance(r.get('prediction'),dict):
            if any(q[k]!=g[k] for k in ['document_sha256','render_sha256','input_file_sha256']):raise ValueError('Gold/crop mismatch')
            item['metrics']=score(projection(r['prediction']),g)
        else:item.update(metrics=None,reason='No valid output')
        rows.append(item)
    report={'scope':'same_four_graph_diagnostic_not_independent_gold','rows':rows,
        'benchmark_gold_completed':0,'new_verified_CPT_samples':0,
        'note':'60-page annotation queue is pending; schema/evidence gates are not semantic accuracy.'}
    if getattr(a,'annotations',None):
        annotations=[json.loads(l) for l in a.annotations.read_text(encoding='utf-8').splitlines() if l.strip()]
        queue=[json.loads(l) for l in (a.run/'benchmark_queue.jsonl').read_text(encoding='utf-8').splitlines()]
        native_root=load(v2/'runs/it3170_v2_release/7B/manifest.json')['source_native_root']
        native={r['page']:r for r in map(json.loads,(Path(native_root)/'native_pages.jsonl').read_text(encoding='utf-8').splitlines())}
        report['benchmark']=reference_metrics(annotations,queue,requests,{r['id']:r for r in result['records']},native)
        report['benchmark_gold_completed']=len(annotations)
    write_once(a.out,report);print(a.out)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--results',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--annotations',type=Path)
    evaluate(p.parse_args())
