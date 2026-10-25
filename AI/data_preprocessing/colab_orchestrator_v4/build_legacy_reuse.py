"""Repackage only fully covered units from verified previous returns, with no inference."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

from common import atomic_json,digest,load,write_compact_archive
from unit_store import RESULT_SCHEMA,inspect_result


class LegacyView:
    def __init__(self,path,expected):
        self.path=Path(path);self.sha=digest(path)
        if self.sha!=expected:raise ValueError('Legacy archive SHA-256 mismatch')
        self.zip=zipfile.ZipFile(path);self.m=json.loads(self.zip.read('return.json'))
        if self.m.get('diagnostic_only') or self.m.get('schema')!='v5-orchestrator-3-drive':raise ValueError('Not a completed v3 return')
        files=self.m['files'];self.logical=self.m['logical_files']
        if set(self.zip.namelist())!=set(files)|{'return.json'}:raise ValueError('Legacy inventory mismatch')
        for name,sha in files.items():
            h=hashlib.sha256()
            with self.zip.open(name) as src:
                for block in iter(lambda:src.read(1024*1024),b''):h.update(block)
            if h.hexdigest()!=sha:raise ValueError('Legacy object changed')
        self.summary=self.read_json('summary.json')
        if not self.summary.get('all_jobs_executed'):raise ValueError('Legacy run has incomplete jobs')
        self.covered=set();self.records={};self.pages={}
        for item in self.m['phase_results']:
            if item['phase']!='inference':continue
            prefix=item['packet_dir'];packet=self.read_json(prefix+'/manifest.json')
            self.covered.update((packet['document']['sha256'],p) for p in packet['page_map'].values())
        for did in self.m['runs']:
            self.records[did]=[json.loads(x) for x in self.read('runs/'+did+'/records.jsonl').decode('utf-8').splitlines() if x.strip()]
            self.pages[did]=[json.loads(x) for x in self.read('runs/'+did+'/document_pages.jsonl').decode('utf-8').splitlines() if x.strip()]

    def read(self,name):return self.zip.read('objects/'+self.logical[name])
    def read_json(self,name):return json.loads(self.read(name))
    def extract(self,name,target):
        target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
        with self.zip.open('objects/'+self.logical[name]) as src,target.open('wb') as dst:shutil.copyfileobj(src,dst,1024*1024)
        if digest(target)!=self.logical[name]:raise ValueError('Legacy asset changed')
    def close(self):self.zip.close()


def build(index_path,legacy_evidence,legacy_dir):
    index_path=Path(index_path);index=load(index_path);evidence=load(legacy_evidence)
    out=index_path.parent/'precompleted_results'
    if out.exists():raise FileExistsError('Legacy reuse bundles are immutable')
    views=[]
    try:
        for row in evidence['returns']:
            print('VERIFY LEGACY',row['archive'],flush=True)
            views.append(LegacyView(Path(legacy_dir)/row['archive'],row['sha256']))
        covered=set().union(*(v.covered for v in views));entries=[];out.mkdir()
        for entry in index['bundles']:
            refs={(s['source_sha256'],p) for s in entry['source_ranges'] for p in range(s['first_page'],s['last_page']+1)}
            if not refs.issubset(covered):continue
            folder=out/'_staging'/entry['unit_id'];files={};proofs=[]
            for scope in entry['source_ranges']:
                did=scope['document_id'];selected=set(range(scope['first_page'],scope['last_page']+1));rs={};ps={}
                for v in views:
                    for r in v.records.get(did,[]):
                        if r['page'] in selected and (r['source_sha256'],r['page']) in v.covered:
                            rs[r['id']]=(r,v)
                    for p in v.pages.get(did,[]):
                        if p['page'] in selected and (scope['source_sha256'],p['page']) in v.covered:ps[p['page']]=p
                if set(ps)!=selected:raise ValueError('Legacy page metadata incomplete')
                component=folder/did;component.mkdir(parents=True)
                records=[r for r,_ in sorted(rs.values(),key=lambda rv:(rv[0]['page'],rv[0]['id']))]
                if any(r.get('semantic_verified') or r.get('human_verified') for r in records):raise ValueError('Cannot republish human decisions as machine outputs')
                for name,values in [('records.jsonl',records),('document_pages.jsonl',[ps[p] for p in sorted(ps)])]:
                    target=component/name;target.write_text(''.join(json.dumps(v,ensure_ascii=False)+'\n' for v in values),encoding='utf-8')
                    files[f'runs/{did}/{name}']=target
                source_view=next(v for v in reversed(views) if did in v.records)
                m=source_view.read_json(f'runs/{did}/manifest.json')
                m.update(processing_scope={**scope,'pages':len(selected)},document_layout_complete=False,
                         completion_method='verified_legacy_page_coverage',layout_scope='unit_pages_only')
                atomic_json(component/'manifest.json',m);files[f'runs/{did}/manifest.json']=component/'manifest.json'
                for r,v in rs.values():
                    for field in ['crop','context','render']:
                        logical=f'runs/{did}/'+r[field+'_path']
                        if logical not in files:
                            target=component/r[field+'_path'];v.extract(logical,target);files[logical]=target
                    proof={'archive':v.path.name,'archive_sha256':v.sha,'source_records_sha256':v.logical[f'runs/{did}/records.jsonl'],
                           'source_sha256':scope['source_sha256']}
                    if proof not in proofs:proofs.append(proof)
            atomic_json(folder/'legacy_provenance.json',{'legacy_archives_preserved':True,'proofs':proofs,
                'new_inference_calls':0,'old_nonfatal_errors_and_unverified_facts_preserved':True})
            files['legacy_provenance.json']=folder/'legacy_provenance.json'
            path=out/(entry['unit_id']+'_legacy.zip')
            write_compact_archive(path,files,{'schema':RESULT_SCHEMA,'unit_id':entry['unit_id'],'bundle_index':entry['bundle_index'],
                'pages':entry['pages'],'source_ranges':entry['source_ranges'],'plan_sha256':index['plan_sha256'],
                'input_sha256':entry['sha256'],'processing_complete':True,'training_exported':False,'human_verified':False,
                'semantic_verified':False,'quality_certified':False,'completion_method':'verified_legacy_page_coverage',
                'runs':[s['document_id'] for s in entry['source_ranges']],'phase_results':[],
                'summary':{'all_jobs_executed':True,'all_stages_successful':False,'quality_certified':False,
                           'completion_method':'verified_legacy_page_coverage','new_inference_calls':0}})
            inspect_result(path,entry,index['plan_sha256'])
            entries.append({'unit_id':entry['unit_id'],'filename':path.name,'sha256':digest(path),'bytes':path.stat().st_size,'pages':entry['pages']})
            print('REUSE',entry['unit_id'],entry['pages'],'pages',flush=True)
        result={'schema':'v5-unit-precompleted-v1','plan_sha256':index['plan_sha256'],'units':entries,
                'covered_legacy_pages':len(covered),'reused_pages':sum(e['pages'] for e in entries),
                'legacy_sources':[{'name':v.path.name,'sha256':v.sha} for v in views],'new_inference_calls':0}
        atomic_json(out/'PRECOMPLETED_INDEX.json',result);return result
    finally:
        for v in views:v.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--index',type=Path,required=True);p.add_argument('--legacy-evidence',type=Path,required=True)
    p.add_argument('--legacy-dir',type=Path,required=True);a=p.parse_args()
    print(json.dumps(build(a.index,a.legacy_evidence,a.legacy_dir),indent=2))
