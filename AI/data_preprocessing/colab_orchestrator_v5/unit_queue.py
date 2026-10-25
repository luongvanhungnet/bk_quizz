"""Independent unit transactions: local compute, final Drive ZIP, then receipt."""
import gc
import json
import os
from pathlib import Path
import shutil
import sys
import time
import traceback
import zipfile

from common import atomic_json,checked_extract,copy_verified,digest,load,rows,safe,verify_release,write_compact_archive
from orchestrator import Coordinator,Worker
from telemetry import event,span
from unit_store import INPUT_SCHEMA,RESULT_SCHEMA,UnitStore


class ModelPool:
    """Keep Qwen parked in host RAM and Docling on CPU across completed units."""
    def __init__(self):self.vlm=None;self.docling=None
    def park(self,work):
        if self.vlm is not None:
            response=self.vlm.call(work,work,Path(work)/'ipc',action='park')
            if not response['completed']:raise RuntimeError('Unable to park Qwen: '+response.get('traceback',''))
    def close(self):
        for name in ['vlm','docling']:
            worker=getattr(self,name)
            if worker is not None:worker.close();setattr(self,name,None)


class UnitCoordinator(Coordinator):
    def __init__(self,attempt,entry,header,envs,pool):
        attempt=Path(attempt)
        super().__init__(attempt/'state',attempt,envs)
        self.entry,self.header,self.pool=entry,header,pool;self.batch_pages=20
        self.runtime_work=attempt.parent.parent
        supplied=attempt/'incoming/engine';verify_release(supplied)
        self.engine=self.runtime_work/'engine'
        if not self.engine.exists():shutil.copytree(supplied,self.engine)
        verify_release(self.engine)
        if digest(self.engine/'RELEASE.json')!=digest(supplied/'RELEASE.json'):raise ValueError('Core changed inside unit queue')
        sys.path.insert(0,str(self.engine))
        import io_utils
        io_utils.file_sha=digest
        from jsonl_adapter import install as install_jsonl
        install_jsonl()
        from layout_merge import install
        install()
        self.plan=load(attempt/'incoming/plan.json')
        if digest(attempt/'incoming/plan.json')!=header['plan_sha256']:raise ValueError('Unit plan changed')
        active=set(header['jobs']);self.jobs=[]
        for j in self.plan['jobs']:
            if j['job_id'] in active:
                self.jobs.append({**j,'source_path':str(attempt/'incoming/sources'/(j['source_sha256']+'.pdf')),
                                  'run':str(attempt/'runs'/j['document_id'])})
        if len(self.jobs)!=len(active) or {j['unit_id'] for j in self.jobs}!={entry['unit_id']}:raise ValueError('Invalid unit jobs')
        actual=sorted((j['document_id'],j['source_sha256'],j['first_page'],j['last_page']) for j in self.jobs)
        from unit_store import ranges
        if actual!=ranges(entry) or sum(j['last_page']-j['first_page']+1 for j in self.jobs)!=entry['pages']:
            raise ValueError('Unit page scope changed')
        for j in self.jobs:
            if digest(j['source_path'])!=j['source_sha256']:raise ValueError('Original source changed')
        self.config={**self.plan['config'],'work_root':str(attempt)}
        shared=Path(os.environ.get('BKQUIZ_MODEL_ROOT','/content/bkquiz_v6_models'))
        local_cache=attempt.parent.parent/'vlm_success_cache';local_cache.mkdir(parents=True,exist_ok=True)
        os.environ.update(HF_HOME=str(shared/'hf_cache'),PADDLE_PDX_CACHE_HOME=str(shared/'paddle_cache'),
                          V5_VLM_CACHE=str(local_cache),PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True',TOKENIZERS_PARALLELISM='false')

    def prepare(self):
        from native_batches import prepare_native
        from layout_merge import route_scope
        from workflow import publish
        fragments={f['job_id']:f for f in self.header['seed_fragments']}
        for job in self.jobs:
            run=Path(job['run']);scope={'first_page':job['first_page'],'last_page':job['last_page'],
                'pages':job['last_page']-job['first_page']+1,'vlm_page_budget':job['vlm_page_budget']}
            if job['job_id'] in fragments:
                f=fragments[job['job_id']];source=safe(self.work/'incoming',f['prefix'])
                if digest(source/'records.jsonl')!=f['records_sha256']:raise ValueError('Seed records changed')
                run.mkdir(parents=True,exist_ok=True)
                for p in source.iterdir():
                    if p.is_file():shutil.copyfile(p,run/p.name)
                source_metadata=run/'seed_source_metadata';source_metadata.mkdir()
                for name in ['manifest.json','prepare_summary.json','classification.json','duplicate_candidates.json']:
                    if (run/name).exists():shutil.copyfile(run/name,source_metadata/name)
                rs=rows(run/'records.jsonl')
                for r in rs:
                    if r['source_sha256']!=job['source_sha256'] or not job['first_page']<=r['page']<=job['last_page']:
                        raise ValueError('Seed escaped unit scope')
                    if r.get('semantic_verified') or r.get('human_verified'):raise ValueError('Cloud seed must not convey human verification')
                    for k in ['crop','context','render']:
                        name=r[k+'_path'];target=safe(run,name)
                        origin=safe(self.work/'incoming/seed_assets'/job['document_id'],name)
                        if digest(origin)!=r[k+'_sha256']:raise ValueError('Seed asset changed')
                        if not target.exists():target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(origin,target)
                m=load(run/'manifest.json');m['document']['path']=job['source_path'];m['asset_root']=str(run)
                (run/'machine_snapshots').mkdir(exist_ok=True)
                shutil.copyfile(run/'records.jsonl',run/'machine_snapshots/initial.jsonl')
                m['seed_original_initial_records_sha256']=m.get('initial_records_sha256')
                m['initial_records_sha256']=digest(run/'machine_snapshots/initial.jsonl')
                m.update(processing_scope=scope,pilot_pages=[job['first_page'],job['last_page']],
                         layout_inventory_status='cached_inventory',document_layout_complete=scope['pages']==job['source_pages'],
                         cache_inventory_complete=scope['pages']==job['source_pages'])
                atomic_json(run/'manifest.json',m)
                from collections import Counter
                page_metadata=rows(run/'document_pages.jsonl')
                atomic_json(run/'classification.json',{'pages':scope['pages'],'scope':'unit_pages_only',
                    'page_classes':dict(Counter(p.get('document_class','unknown') for p in page_metadata)),
                    'source_classification_preserved':'seed_source_metadata/classification.json'})
                atomic_json(run/'prepare_summary.json',{'records':len(rs),'full_source_renders':scope['pages'],
                    'reused_layout_and_specialist_cache':True,'scope':'unit_pages_only','training_ready':False,
                    'source_summary_preserved':'seed_source_metadata/prepare_summary.json'})
                routing=route_scope(rs,scope)
                publish(run,rs,{'type':'unit_machine_seed','unit_id':self.entry['unit_id'],'human_verification_transferred':False})
                atomic_json(run/'routing_summary.json',routing)
            else:
                print('NATIVE UNIT',self.entry['unit_id'],job['document_id'],scope,flush=True)
                self.cpu_stage('native',job)
            actual={p['page'] for p in rows(run/'document_pages.jsonl')}
            expected=set(range(job['first_page'],job['last_page']+1))
            if actual!=expected:raise ValueError('Native processing exceeded or missed unit pages')

    def packet(self,job,phase):
        key=job['job_id']+':'+phase
        previous=self.state['packets'].get(key)
        if previous:return Path(previous['local_folder'])
        from corpus import package_job
        with span('package_unit_job',job=job['job_id'],phase=phase):archive=package_job(self.config,job,phase)
        folder=archive.parent;m=load(folder/'manifest.json')
        if phase=='inference':
            pages={q['page'] for q in m['requests'] if q.get('use_vlm')}
            if len(pages)>job['vlm_page_budget']:raise ValueError('Unit VLM budget exceeded')
            from seed_cache import seed_vlm_cache
            reused=seed_vlm_cache(job['run'],folder,Path(os.environ['V5_VLM_CACHE']))
            if reused:event('seed_vlm_observations_reused',unit_id=self.entry['unit_id'],count=reused,semantic_verified=False)
        self.state['packets'][key]={'archive':str(archive),'archive_sha256':digest(archive),
            'manifest_sha256':digest(folder/'manifest.json'),'local_folder':str(folder)}
        self.save();return folder

    def cpu_stage(self,stage,job,**fields):
        from stage_guard import run_guarded
        folder=self.work/'guarded_stages'/(job['job_id']+'_'+stage)
        folder.mkdir(parents=True,exist_ok=True)
        output=folder/'result.json';request=folder/'request.json'
        atomic_json(request,{'stage':stage,'engine':str(self.engine),'job':job,'config':self.config,
                             'output':str(output),**fields})
        run_guarded([self.envs['controller'],str(Path(__file__).with_name('stage_worker.py')),str(request)],
                    folder,stage,timeout=float(os.environ.get('BKQUIZ_CPU_TIMEOUT_SECONDS','900')))
        return load(output)

    def group_stage(self,role,pairs):
        pending=[(j,p) for j,p in pairs if self.needs_stage(j,p,role)]
        if not pending:return
        if role=='vlm':
            if self.pool.vlm is None:self.pool.vlm=Worker(self.envs['vlm'],'vlm',self.engine,self.runtime_work/'model_logs')
            for job,phase in pending:self.execute_stage(self.pool.vlm,job,phase)
            self.pool.park(self.work)
        else:
            self.pool.park(self.work)
            if role=='docling':
                if self.pool.docling is None:
                    extra={'CUDA_VISIBLE_DEVICES':''}
                    if os.environ.get('BKQUIZ_DOCLING_HF_HOME'):
                        extra.update(HF_HOME=os.environ['BKQUIZ_DOCLING_HF_HOME'],
                                     HF_HUB_CACHE=str(Path(os.environ['BKQUIZ_DOCLING_HF_HOME'])/'hub'))
                    self.pool.docling=Worker(self.envs['docling'],'docling',self.engine,self.runtime_work/'model_logs',extra)
                for job,phase in pending:self.execute_stage(self.pool.docling,job,phase)
            else:super().group_stage(role,pending)

    def merge(self,job,phase):
        from corpus import merge_job
        key=job['job_id']+':'+phase
        if key in self.state['merged']:return
        archive=self.result_archive(job,phase)
        with span('merge_unit',job=job['job_id'],phase=phase):
            summary=self.cpu_stage('merge',job,packet=str(self.packet(job,phase)),archive=str(archive))
        # All intermediate results stay local; there is no cross-unit checkpoint replay.
        self.state['merged'][key]={'archive':str(archive),'archive_sha256':digest(archive),'summary':summary}
        self.save()

    def run(self):
        summary=super().run()
        if not summary['all_jobs_executed']:
            raise RuntimeError('Unit incomplete; no final result committed: '+json.dumps(
                {'summary':summary,'last_errors':self.state.get('errors',[])[-3:]},ensure_ascii=False))
        review=[];suppressed=0
        for job in self.jobs:
            for path in (Path(job['run'])/'region_audit').glob('*.json'):
                item=load(path);suppressed+=item.get('suppressed_background_occurrences',0)
                if item.get('review_required'):review.append({'document_id':job['document_id'],'page':item['page'],'audit':path.name})
        summary.update(preprocessing_version='6.0.0',suppressed_background_occurrences=suppressed,
                       region_review_pages=review,region_review_required=bool(review))
        atomic_json(self.base/'summary.json',summary)
        return summary

    def export(self,summary,input_sha):
        if not summary['all_jobs_executed']:raise ValueError('Incomplete units cannot be exported as complete')
        files={};phases=[]
        for job in self.jobs:
            run=Path(job['run'])
            for r in rows(run/'records.jsonl'):
                if not job['first_page']<=r['page']<=job['last_page'] or r['source_sha256']!=job['source_sha256']:
                    raise ValueError('Output escaped unit scope')
                if r.get('human_verified') or r.get('semantic_verified'):raise ValueError('Machine results cannot self-verify')
            for p in run.rglob('*'):
                if p.is_file() and p.suffix not in {'.next','.sqlite3'} and not p.name.endswith(('-wal','-shm')):
                    files[f'runs/{job["document_id"]}/{p.relative_to(run).as_posix()}']=p
            for phase in ['discovery','inference']:
                key=job['job_id']+':'+phase
                if key not in self.state['merged']:continue
                packet=self.packet(job,phase);prefix=f'packets/{job["job_id"]}_{phase}'
                for p in packet.rglob('*'):
                    if p.is_file() and p.name!='v5_colab_input.zip':files[prefix+'/'+p.relative_to(packet).as_posix()]=p
                result=self.state['merged'][key]['archive'];name=f'results/{Path(result).name}';files[name]=Path(result)
                phases.append({'job_id':job['job_id'],'phase':phase,'packet_dir':prefix,'results':name})
        for root,prefix in [(self.work/'raw_results','raw_results'),(self.work/'page_batches','page_batches'),
                            (self.work/'logs','logs'),(self.work/'guarded_stages','guarded_stages'),(self.base,'state')]:
            for p in root.rglob('*'):
                if p.is_file() and p.suffix not in {'.next','.sqlite3'}:
                    files[prefix+'/'+p.relative_to(root).as_posix()]=p
        # Resident workers log into their first unit; include a stable snapshot for later units.
        for role in ['vlm','docling']:
            worker=getattr(self.pool,role)
            if worker is not None and worker.log_path.is_file():
                target=self.work/'log_snapshots'/(role+'.log');target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(worker.log_path,target);files['resident_logs/'+role+'.log']=target
        for p in Path(__file__).parent.glob('*.py'):
            if not p.name.startswith(('build_','test_')):files['orchestrator_runtime/'+p.name]=p
        files['engine/RELEASE.json']=self.engine/'RELEASE.json';files['plan.json']=self.work/'incoming/plan.json'
        marker=getattr(self,'telemetry_marker',None)
        if marker is not None:
            import telemetry
            source,offset=marker;target_log=self.work/'unit_events.jsonl'
            with telemetry._lock,Path(source).open('rb') as src,target_log.open('wb') as dst:
                src.seek(offset);shutil.copyfileobj(src,dst,1024*1024)
            files['telemetry/unit_events.jsonl']=target_log
        atomic_json(self.work/'source_provenance.json',{'original_pdfs_preserved_in_input_zip':True,
            'input_sha256':input_sha,'source_ranges':self.entry['source_ranges']})
        files['source_provenance.json']=self.work/'source_provenance.json'
        target=self.work/'export'/f'{self.entry["unit_id"]}_result.zip'
        write_compact_archive(target,files,{'schema':RESULT_SCHEMA,'unit_id':self.entry['unit_id'],
            'bundle_index':self.entry['bundle_index'],'pages':self.entry['pages'],'source_ranges':self.entry['source_ranges'],
            'plan_sha256':self.header['plan_sha256'],'input_sha256':input_sha,'processing_complete':True,
            'diagnostic_only':False,'quality_certified':False,'training_exported':False,'human_verified':False,'semantic_verified':False,
            'runs':[j['document_id'] for j in self.jobs],'phase_results':phases,'summary':summary,
            'original_jobs_sha256':self.plan['jobs_sha256'],'core_release':'5.0.0',
            'preprocessing_version':'6.0.0','region_policy':'source_bound_verified_tiles_only',
            'old_results_automatically_upgraded':False})
        return target


class UnitRunner:
    def __init__(self,base,work,index,envs,precompleted_dir=None,previous_base=None):
        self.base,self.work=Path(base),Path(work);self.index=index;self.envs=envs
        self.store=UnitStore(base,index);self.pool=ModelPool();self.scanned=False
        self.precompleted_dir=Path(precompleted_dir) if precompleted_dir is not None else None
        self.previous_base=Path(previous_base) if previous_base is not None else None

    def scan(self):
        summary=self.store.scan();self.scanned=True
        if self.previous_base is not None:
            from reuse_previous import adopt
            adopt(self.store,self.previous_base,self.work)
            summary=self.store.summary()
        if self.precompleted_dir is not None and (self.precompleted_dir/'PRECOMPLETED_INDEX.json').exists():
            seeds=load(self.precompleted_dir/'PRECOMPLETED_INDEX.json')
            if seeds.get('schema')!='v5-unit-precompleted-v1' or seeds['plan_sha256']!=self.index['plan_sha256']:
                raise ValueError('Precompleted results belong to another unit plan')
            for seed in seeds['units']:
                if seed['unit_id'] in self.store.completed:continue
                entry=self.store.entries[seed['unit_id']]
                source=safe(self.precompleted_dir,seed['filename'])
                local=self.work/'precompleted'/(seed['unit_id']+'.zip')
                print('REUSE OLD RESULT',seed['unit_id'],'no model inference',flush=True)
                copy_verified(source,local,expected_sha256=seed['sha256'])
                self.store.publish(local,entry);local.unlink()
            summary=self.store.summary()
        # Restart semantics deliberately discard incomplete LOCAL attempts.
        for path in (self.work/'attempts').glob('*'):
            if path.is_dir() and (path/'ATTEMPT.json').exists():self.cleanup(path)
        atomic_json(self.base/'queue_state.json',summary);return summary

    def cleanup(self,path):
        path=Path(path).resolve();root=(self.work/'attempts').resolve()
        if path==root or not path.is_relative_to(root):raise ValueError('Refusing cleanup outside owned local attempts')
        marker=load(path/'ATTEMPT.json')
        if marker['plan_sha256']!=self.index['plan_sha256'] or marker['unit_id'] not in self.store.entries:
            raise ValueError('Retaining an attempt from a different plan')
        shutil.rmtree(path)

    def process(self,unit_id):
        if not self.scanned:self.scan()
        if unit_id in self.store.completed:return {**self.store.completed[unit_id],'reused':True}
        entry=self.store.entries[unit_id]
        if not Path(entry['path']).is_file():raise FileNotFoundError('Input not yet on Drive: '+entry['path'])
        attempt=self.work/'attempts'/(unit_id+'_'+str(time.time_ns()));attempt.mkdir(parents=True)
        atomic_json(attempt/'ATTEMPT.json',{'unit_id':unit_id,'plan_sha256':self.index['plan_sha256']})
        atomic_json(self.base/'current_attempt.json',{'unit_id':unit_id,'started_unix':time.time(),'status':'running',
            'policy':'On restart this unfinished unit is retried from its input; other complete receipts are preserved'})
        try:
            import telemetry
            telemetry_marker=(telemetry._path,telemetry._path.stat().st_size) if telemetry._path and telemetry._path.exists() else None
            local=attempt/'input.zip'
            with span('unit_stage_input',unit_id=unit_id):copy_verified(entry['path'],local,expected_sha256=entry['sha256'])
            with span('unit_extract',unit_id=unit_id):header=checked_extract(local,attempt/'incoming','bundle.json')
            if (header.get('schema')!=INPUT_SCHEMA or header.get('unit_id')!=unit_id
                or header.get('plan_sha256')!=self.index['plan_sha256'] or header.get('pages')!=entry['pages']):
                raise ValueError('Wrong unit input')
            local.unlink()
            c=UnitCoordinator(attempt,entry,header,self.envs,self.pool)
            c.telemetry_marker=telemetry_marker
            with span('unit_compute',unit_id=unit_id):summary=c.run()
            archive=c.export(summary,entry['sha256'])
            receipt=self.store.publish(archive,entry)
            atomic_json(self.base/'current_attempt.json',{'unit_id':unit_id,'status':'complete','saved_unix':time.time()})
            try:self.cleanup(attempt)
            except OSError as exc:event('local_cleanup_error_after_durable_save',unit_id=unit_id,error=repr(exc))
            gc.collect();return receipt
        except Exception:
            error={'unit_id':unit_id,'status':'incomplete','traceback':traceback.format_exc(),'unix':time.time()}
            atomic_json(self.base/'failures'/unit_id/(str(time.time_ns())+'.json'),error)
            for p in (attempt/'logs').glob('*.log'):
                copy_verified(p,self.base/'failures'/unit_id/(attempt.name+'_'+p.name),quiet=True)
            for p in (attempt/'guarded_stages').rglob('*'):
                if p.is_file() and (p.suffix=='.log' or p.name.endswith('_progress.json')):
                    copy_verified(p,self.base/'failures'/unit_id/attempt.name/p.relative_to(attempt/'guarded_stages'),quiet=True)
            self.pool.close()
            atomic_json(self.base/'current_attempt.json',error)
            raise

    def close(self):self.pool.close()
