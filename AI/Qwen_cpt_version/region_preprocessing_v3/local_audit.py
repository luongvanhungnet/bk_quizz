"""Reproducible local v3 smoke and before/after diagnostic report, no Qwen inference."""
import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import zipfile
from contracts import check_package,load,file_hash,write_once

ROOT=Path(__file__).resolve().parent


def run(a):
    m=check_package(a.run)
    for name,sha in m['code_sha256'].items():
        if file_hash(ROOT/name)!=sha:raise ValueError('Root/package code differs: '+name)
    for path,sha in load(a.run/'preserved_source_hashes.json').items():
        if file_hash(Path(path))!=sha:raise ValueError('Original artifact changed')
    with zipfile.ZipFile(a.run/'region_v3_input.zip') as z:
        if z.testzip():raise ValueError('Bad ZIP CRC')
        if z.read('manifest.json')!=(a.run/'manifest.json').read_bytes():raise ValueError('ZIP manifest differs')
    subprocess.run([sys.executable,str(a.run/'worker.py'),'collect','--input',str(a.run),'--out',str(a.out/'smoke')],check=True)
    records=[load(p) for p in (a.out/'smoke/records').glob('*.json')]
    specialist={}
    for engine in ['formula','table']:
        rows=[r for r in records if r['engine']==engine]
        specialist[engine]={'reused_records':len(rows),'status':dict(Counter(r['status'] for r in rows)),
            'heuristic_gate_pass':sum(r['quality'].get('evidence_gate_pass',False) for r in rows),
            'flag_counts':dict(Counter(f for r in rows for f in r['quality']['flags'])),
            'flagged_ids':[r['id'] for r in rows if r['quality']['flags']]}
    gold=load(ROOT.parent/'region_preprocessing_v2/gold_cases.json');geometry=[];boards=[]
    for r in m['requests']:
        if r['engine']!='vlm' or r['page'] not in m['pilot_pages']:continue
        c=load(a.run/r['context'])
        if r['kind']=='state_tree':boards.append({'id':r['id'],'detected_boards':len(c['board_candidates']),'semantic_verified':False});continue
        g=next(g for g in gold if g['page']==r['page']);native=c['native_graph_candidates'];labels={n['id']:n['label'] for n in native['nodes']}
        pairs={tuple(sorted([labels[e['source']],labels[e['target']]])) for e in native['edges']}
        actual={tuple(sorted([e['source'],e['target']])) for e in g['edges']}
        geometry.append({'page':r['page'],'node_labels':len(labels),'gold_node_labels':len(g['nodes']),
            'candidate_edge_pairs':len(pairs),'gold_pairs':len(actual),'correct_pairs':len(pairs&actual),
            'scope':'native proposal diagnostic on development crops; not final VLM accuracy'})
    groups=load(a.run/'benchmark_groups.json');protected=set(groups['protected_holdout_pages'])
    queue=[json.loads(l) for l in (a.run/'benchmark_queue.jsonl').read_text(encoding='utf-8').splitlines()]
    if any(r['annotation_status']!='pending' or r['gold'] is not None for r in queue):raise ValueError('Unexpected fabricated benchmark gold')
    if any(r['page'] in protected for r in queue if r['split']=='development'):raise ValueError('Development/holdout overlap')
    metadata=[json.loads(l) for l in (a.run/'cpt/train.metadata.jsonl').read_text(encoding='utf-8').splitlines()]
    if any(r['page'] in protected for r in metadata):raise ValueError('Protected page leaked into CPT')
    packed=[json.loads(l) for l in (a.run/'cpt/train.packed.jsonl').read_text(encoding='utf-8').splitlines()]
    count=sum(len(r['input_ids']) for r in packed)
    if count!=load(a.run/'cpt/manifest.json')['tokens']:raise ValueError('Packed token count mismatch')
    near=load(ROOT.parent/'hybrid_preprocessing/runs/it3170_test/deduplication.json')['near_pairs']
    for p in near:
        if groups['page_to_group'][str(p['page_a'])]!=groups['page_to_group'][str(p['page_b'])]:raise ValueError('Near pairs split across groups')
    for members in groups.get('exact_visual_groups',[]):
        if len({groups['page_to_group'][str(p)] for p in members})!=1:raise ValueError('Exact visual duplicates split across groups')
    for p in ROOT.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'))
    notebook=load(ROOT/'IT3170_Region_V3_7B.ipynb')
    for c in notebook['cells']:
        if c['cell_type']=='code':ast.parse(''.join(c['source']))
    before=load(ROOT.parent/'region_preprocessing_v2/evaluation_d682e3b25b0d/metrics.json')
    report={'passed':True,'source_manifest_sha256':file_hash(a.run/'manifest.json'),
        'zip_sha256':file_hash(a.run/'region_v3_input.zip'),'specialists':specialist,
        'native_geometry_diagnostic':geometry,'board_proposals':boards,
        'v2_7B_baseline':before['profiles']['7B']['diagnostic_four_graph_aggregate'],
        'benchmark':{'pages':len(queue),'splits':dict(Counter(r['split'] for r in queue)),
            'protected_group_pages':len(protected),'gold_completed':0},
        'cpt':load(a.run/'cpt/manifest.json'),'new_qwen_v3_inference_executed':False,
        'new_semantically_verified_predictions':0,'human_review_minutes':None,'new_verified_tokens_per_hour':None,
        'checks':['source/code/crop/context/seed hashes','ZIP CRC','snapshot collection without model',
                  'source preservation','CPT holdout exclusion','near-pair group consistency','token accounting','Python/notebook syntax']}
    write_once(a.out/'metrics.json',report)
    print(json.dumps({'passed':True,'manifest':report['source_manifest_sha256'][:12],
        'specialist_pass':{k:v['heuristic_gate_pass'] for k,v in specialist.items()},'cpt_samples':len(metadata),'cpt_tokens':count},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,default=ROOT/'runs/it3170_v3_20261019');p.add_argument('--out',type=Path,default=ROOT/'evidence/release_validation')
    run(p.parse_args())
