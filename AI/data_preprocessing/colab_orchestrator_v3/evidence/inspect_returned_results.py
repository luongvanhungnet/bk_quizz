"""Inspect nested Drive returns without expanding all logical image aliases."""
import collections
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from common import digest,load,atomic_json
from summarize_telemetry import summarize


def inspect(folder):
    folder=Path(folder);out=folder/'inspection';out.mkdir(exist_ok=True);results=[]
    for outer in sorted(folder.glob('*.zip')):
        with zipfile.ZipFile(outer) as z:
            for info in z.infolist():
                if not info.filename.endswith('.zip'):continue
                target=out/Path(info.filename).name
                if not target.exists():
                    temporary=target.with_suffix('.extracting')
                    with z.open(info) as src,temporary.open('wb') as dst:shutil.copyfileobj(src,dst,4*1024*1024)
                    temporary.replace(target)
                with zipfile.ZipFile(target) as inner:
                    m=json.loads(inner.read('return.json'));logical=m['logical_files'];bad=[]
                    assert len(inner.namelist())==len(set(inner.namelist()))
                    assert set(inner.namelist())==set(m['files'])|{'return.json'}
                    assert all(name=='objects/'+sha for name,sha in m['files'].items())
                    assert set(m['files'])=={'objects/'+sha for sha in logical.values()}
                    for name,wanted in m['files'].items():
                        h=hashlib.sha256()
                        with inner.open(name) as f:
                            for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
                        if h.hexdigest()!=wanted:bad.append(name)
                    assert not bad,bad
                    def read(name):return json.loads(inner.read('objects/'+logical[name]))
                    state=read('queue_state.json');summary=read('summary.json');jobs={x['job_id'] for x in m['phase_results']}
                    roles=collections.defaultdict(lambda:{'stages':0,'bad_stages':0,'worker_seconds':0.0})
                    for key,v in state['stages'].items():
                        if key.split(':')[0] not in jobs:continue
                        a=roles[key.split(':')[-1]];a['stages']+=1;a['bad_stages']+=not v.get('completed') or v.get('result',{}).get('status')!='ok'
                        a['worker_seconds']+=v.get('seconds',0)
                    counts=collections.Counter();errors=collections.Counter();examples={};observations=[];parser_errors=collections.Counter()
                    for name,sha in logical.items():
                        if not name.startswith('batch_audit/'):continue
                        with tempfile.SpooledTemporaryFile(max_size=1024*1024) as spool:
                            with inner.open('objects/'+sha) as src:shutil.copyfileobj(src,spool,1024*1024)
                            spool.seek(0)
                            with zipfile.ZipFile(spool) as batch:
                                bm=json.loads(batch.read('batch.json'));response=bm.get('response',{})
                                if not response.get('completed'):parser_errors[response.get('error','unknown')]+=1
                                for n in batch.namelist():
                                    if n.startswith('output/records/') and n.endswith('.json'):
                                        r=json.loads(batch.read(n));counts[r.get('mode','unknown')+':'+r['status']]+=1
                                        if r['status'] not in {'ok','skipped_seed'}:
                                            key=r.get('mode','unknown')+': '+r.get('error','unknown');errors[key]+=1
                                            examples.setdefault(key,{'id':r['id'],'page':r['page'],'traceback':r.get('traceback')})
                                    if n.startswith('output/vlm_results_') and n.endswith('.json'):
                                        observations.extend(json.loads(batch.read(n)).get('observations',[]))
                    documents=[]
                    for name in logical:
                        if name.startswith('runs/') and name.endswith('/manifest.json'):
                            run=name.rsplit('/',1)[0];metadata=read(name);records=inner.read('objects/'+logical[run+'/records.jsonl']).decode().splitlines()
                            buckets=collections.Counter();kind=collections.Counter();quality=collections.Counter();success=0;traced=0;verified=0;source_pages=set()
                            for line in records:
                                if not line.strip():continue
                                r=json.loads(line);buckets[r['machine_bucket']]+=1;kind[r['kind']]+=1
                                assert r['source_sha256']==metadata['document']['sha256']
                                for prefix in ['crop','context','render']:
                                    assert logical[run+'/'+r[prefix+'_path']]==r[prefix+'_sha256'],r['id']
                                traced+=1;verified+=bool(r.get('semantic_verified') or r.get('human_verified'));source_pages.add(r['page'])
                                success+=any(c.get('engine')=='vlm' and c.get('status')=='ok' for c in r['candidates'])
                            documents.append({'id':run.split('/')[1],'pages':metadata['document']['pages'],'records':sum(kind.values()),
                                              'buckets':dict(buckets),'kinds':dict(kind),'vlm_success_records':success,'layout_status':metadata.get('layout_inventory_status'),
                                              'records_with_valid_asset_hashes':traced,'records_marked_verified':verified,'represented_source_pages':len(source_pages)})
                    telemetry=[]
                    for name in logical:
                        if name.startswith('telemetry/'):
                            p=out/(target.stem+'_'+Path(name).name);p.write_bytes(inner.read('objects/'+logical[name]));telemetry.append(p)
                    resource=summarize(telemetry);timeline=[]
                    for p in telemetry:
                        with p.open(encoding='utf-8') as f:
                            for line in f:
                                try:r=json.loads(line)
                                except ValueError:continue
                                if r['event'] in {'command','stage_start','stage_end','resources'}:timeline.append(r)
                    gpu_names=set()
                    for name in logical:
                        if name.startswith('environment_logs/') and name.endswith('.txt'):pass
                    result={'archive':target.name,'sha256':digest(target),'bytes':target.stat().st_size,
                        'objects_verified':len(m['files']),'logical_files':len(logical),'logical_bytes':m['logical_bytes'],'unique_bytes':m['unique_bytes'],
                        'duplicate_bytes_avoided':m['duplicate_bytes_avoided'],'sequence_index':m['sequence_index'],'summary':summary,
                        'active_roles':dict(roles),'active_bad_stages':sum(v['bad_stages'] for v in roles.values()),
                        'record_status_counts':dict(counts),'errors':dict(errors),'error_examples':examples,'parser_batch_errors':dict(parser_errors),
                        'vlm_observations':len(observations),'vlm_ok':sum(o['status']=='ok' for o in observations),
                        'vlm_cache_hits':sum(bool(o.get('cache_hit')) for o in observations),'vlm_partial':sum(bool(o.get('partial_observation')) for o in observations),
                        'vlm_pages':sorted({o['page'] for o in observations}),
                        'unique_vlm_document_pages':len({(o['source_sha256'],o['page']) for o in observations}),'documents':documents,'telemetry':resource}
                    results.append(result)
                    print(json.dumps({k:v for k,v in result.items() if k not in {'telemetry','error_examples','parser_batch_errors'}},ensure_ascii=False),flush=True)
    results.sort(key=lambda r:r['sequence_index'])
    index=load(folder/'latest_index.json')
    assert any(r['sha256']==index['files'][0]['sha256'] and r['bytes']==index['files'][0]['bytes'] for r in results)
    report={'date':'2026-10-21','returns':results,'latest_index_matches':True,'source_archives_modified':False,
            'note':'Telemetry snapshots are cumulative within the session and end before final ZIP transfer. VLM ok is execution success, not semantic accuracy.'}
    atomic_json(out/'RESULT_ANALYSIS.json',report)
    return report


if __name__=='__main__':inspect(sys.argv[1])
