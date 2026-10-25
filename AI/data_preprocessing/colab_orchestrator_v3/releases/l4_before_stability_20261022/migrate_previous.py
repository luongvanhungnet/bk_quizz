"""Optional metadata migration; read old queues/checkpoints without changing them."""
import copy
from pathlib import Path
import time

from common import INPUT_VERSION,VERSION,atomic_json,digest,load,safe


def migrate(previous,base,inputs,batch_pages=20):
    previous,base=Path(previous),Path(base)
    if previous.resolve()==base.resolve():raise ValueError('Use a separate v3 BASE')
    if (base/'queue_state.json').exists():return {'status':'existing_v3_queue_unchanged'}
    path=previous/'queue_state.json';before=digest(path);state=load(path)
    if state.get('schema')!=INPUT_VERSION:raise ValueError('Previous queue is not orchestrator v2')
    if state['plan_sha256']!=inputs[0]['manifest']['plan_sha256']:raise ValueError('Previous queue plan mismatch')
    state=copy.deepcopy(state);state['schema']=VERSION;state['batch_pages']=batch_pages
    for index,info in state.get('received_inputs',{}).items():
        source=Path(inputs[int(index)-1]['path'])
        if digest(source)!=info['sha256']:raise ValueError('Previous input identity mismatch')
        info['path']=str(source)
    for result in state.get('finished_inputs',{}).values():
        if digest(result['archive'])!=result['archive_sha256']:raise ValueError('Previous result changed')
    state['legacy_stage_outputs']={}
    for key,response in state.get('stages',{}).items():
        job,phase,role=key.rsplit(':',2)
        if job+':'+phase in state.get('merged',{}):continue
        folder=previous/'raw_results'/job/phase/('vlm' if role=='vlm' else role if role=='docling' else 'paddle_'+role)
        if not folder.is_dir():raise ValueError('Previous unmerged outputs missing; not rerunning cached work: '+key)
        state['legacy_stage_outputs'][key]={'folder':str(folder),'response':response}
    checkpoints=[]
    for index in (previous/'checkpoints').glob('*/index.json'):
        old=load(index);new=copy.deepcopy(old);new['legacy_root']=str(index.parent.resolve())
        for item in new['archives']:
            archive=safe(index.parent,item['name'])
            if not archive.is_file():raise ValueError('Missing previous checkpoint')
            item['origin']=str(archive.resolve())
        checkpoints.append((base/'checkpoints'/index.parent.name/'index.json',new))
    if digest(path)!=before:raise RuntimeError('Previous queue is changing; stop its runtime before migration')
    for target,index in checkpoints:atomic_json(target,index)
    receipt={'status':'migrated','previous_base':str(previous),'previous_state_sha256':before,'unix':time.time(),
             'checkpoint_indices':len(checkpoints),'legacy_unmerged_stages':len(state['legacy_stage_outputs']),
             'last_acknowledged_index':state.get('last_acknowledged_index',0),'old_files_modified':False}
    state['migration']=receipt;atomic_json(base/'migration.json',receipt);atomic_json(base/'queue_state.json',state)
    return receipt
