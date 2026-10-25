"""Package checks and a clearly labeled fake-model integration run; no GPU metrics."""
import argparse
import ast
import copy
import json
from pathlib import Path
import tempfile
import zipfile
from contracts import check_package,file_hash,load,write_once
from worker import run,collect
from prompts import prompt

ROOT=Path(__file__).resolve().parent

class SimulatedModel:
    """Exercise contracts only. These responses are NOT semantic annotations."""
    loaded=None
    telemetry={'simulation_only':True,'GPU_inference_executed':False}
    def infer(self,image,text,profile,limit):
        payload=json.loads(text.split('Source candidates (unverified; check against image):\n')[1].split('\nPrevious attempt')[0])
        if '"node_ids"' in text.split('One valid nonempty example')[0]:
            p={'node_ids':[n['id'] for n in payload['nodes']],'edge_ids':[e['id'] for e in payload['edges']],'complete':True,'uncertain':[]}
        elif '"attributes"' in text.split('One valid nonempty example')[0]:
            from schema import ATTR_EXAMPLE
            p={'attributes':[{**copy.deepcopy(ATTR_EXAMPLE),'edge_id':e['id']} for e in payload['edges']],'uncertain':[]}
        elif '"is_board"' in text.split('One valid nonempty example')[0]:
            p={'id':payload['id'],'is_board':True,'board_size':payload['board_size'],'queens':[],'removed_cells':[],'uncertain':['Simulation, not a source annotation']}
        elif '"relations"' in text.split('One valid nonempty example')[0]:
            p={'relations':[],'complete':False,'uncertain':['Simulation, not a source annotation']}
        elif '"nodes"' in text.split('One valid nonempty example')[0]:
            p={'nodes':[{'id':'n1','label':'a','bbox':[100,100,150,150]},{'id':'n2','label':'b','bbox':[600,600,650,650]}],'uncertain':['Simulation']}
        else:p={'edges':[{'id':'e1','source':'n1','target':'n2','bbox':[120,120,620,620]}],'uncertain':['Simulation']}
        return json.dumps(p),False

def main(a):
    m=check_package(a.run)
    with zipfile.ZipFile(a.run/'region_v4_input.zip') as z:assert z.testzip() is None
    for path,sha in load(a.run/'preserved_source_hashes.json').items():assert file_hash(Path(path))==sha,path
    for name,sha in m['code_sha256'].items():assert file_hash(ROOT/name)==sha,'Rebuild package after runtime change: '+name
    for path in ROOT.glob('*.py'):ast.parse(path.read_text(encoding='utf-8'))
    for c in load(ROOT/'IT3170_Region_V4_7B.ipynb')['cells']:
        if c['cell_type']=='code':ast.parse(''.join(c['source']))
    protected=set(load(a.run/'benchmark_groups.json')['protected_holdout_pages'])
    train=[json.loads(l) for l in (a.run/'cpt/train.metadata.jsonl').read_text(encoding='utf-8').splitlines()]
    assert all(r['page'] not in protected for r in train)
    cpt=load(a.run/'cpt/manifest.json')
    packs=[json.loads(l) for l in (a.run/'cpt/train.packed.jsonl').read_text(encoding='utf-8').splitlines()]
    assert sum(len(p['input_ids']) for p in packs)==cpt['tokens']
    queue=[json.loads(l) for l in (a.run/'benchmark_queue.jsonl').read_text(encoding='utf-8').splitlines()]
    assert all(r.get('gold') is None and r['annotation_status']=='pending' for r in queue)
    lengths={}
    for t in m['tasks']:lengths[t['stage']]=max(lengths.get(t['stage'],0),len(prompt(t['stage'],load(a.run/t['context']))))
    with tempfile.TemporaryDirectory(prefix='bkquiz_v4_simulation_') as folder:
        out=Path(folder)
        pilot=run(a.run,out,m,'pilot',model=SimulatedModel())
        pp=[r for r in pilot['records'] if r['engine']=='vlm' and r['source']['page'] in m['pilot_pages']]
        assert len(pp)==6 and all(r['status']=='ok' for r in pp),[(r['id'],r['status']) for r in pp]
        full=run(a.run,out,m,'all',model=SimulatedModel())
        assert all(r['status']=='ok' for r in full['records'] if r['engine']=='vlm')
        assert all(r.get('semantic_verified') is False for r in full['records'])
        # Validate the real import path and old metric adapter, using synthetic
        # results only in this temporary directory; never produce training facts.
        from review import import_results
        from types import SimpleNamespace
        result_zip=out/'simulation_results.zip'
        with zipfile.ZipFile(result_zip,'w',zipfile.ZIP_DEFLATED) as z:
            for p in out.glob('results_*.json'):z.write(p,p.name)
        import_results(SimpleNamespace(run=a.run,results=result_zip,out=out/'review'))
        assert load(out/'review/summary.json')['new_verified_CPT_samples']==0
        from evaluate import evaluate
        evaluate(SimpleNamespace(run=a.run,results=out/'review/results.json',out=out/'simulation_diagnostics.json',annotations=None))
        assert load(out/'simulation_diagnostics.json')['benchmark_gold_completed']==0
        simulation={'simulation_only':True,'actual_model_accuracy':None,'pilot_parent_contracts_ok':len(pp),
                    'all_parent_contracts_ok':sum(r['engine']=='vlm' and r['status']=='ok' for r in full['records']),
                    'task_contracts_ok':len(full['tasks']),'old_metric_adapter_checked':True,'new_verified_CPT_samples':0}
    report={'passed':True,'manifest_sha256':file_hash(a.run/'manifest.json'),'input_zip_sha256':file_hash(a.run/'region_v4_input.zip'),
        'checks':['ZIP CRC','source/runtime/crop/context/seed hashes','source preservation','holdout exclusion','token accounting','Python/notebook syntax','simulated workflow + import'],
        'maximum_prompt_characters_by_stage':lengths,'simulation':simulation,'CPT_samples':len(train),'CPT_tokens':cpt['tokens'],
        'new_GPU_inference_executed':False,'new_semantically_verified':0}
    write_once(a.out/'metrics.json',report);print(json.dumps(report,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,default=ROOT/'runs/it3170_v4_20261019_final');p.add_argument('--out',type=Path,default=ROOT/'evidence/final_validation')
    main(p.parse_args())
