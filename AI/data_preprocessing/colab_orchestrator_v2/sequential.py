"""One input -> one completed result -> explicit download acknowledgement -> next input."""
import json
import os
from pathlib import Path
import shutil
import sys
import time
from common import VERSION, atomic_json, checked_extract, checkpoint, digest, load, restore_checkpoint, rows, safe, verify_release
from orchestrator import Coordinator, Worker, heartbeat


def assert_next(state, manifest):
    expected = state.get('last_acknowledged_index', 0) + 1
    if manifest['bundle_index'] != expected:
        raise ValueError(f'Expected input {expected:02d}; download and acknowledge the previous result before uploading another file')
    if manifest.get('schema') != VERSION or not manifest.get('sequence_required'):
        raise ValueError('Use the new sequential inputs, not the old 14-file set')


class SequentialCoordinator(Coordinator):
    def __init__(self, base, work, environments, keep_model=True):
        super().__init__(base, work, environments)
        self.vlm_worker = None
        self.keep_model = keep_model
        self.state.setdefault('received_inputs', {})
        self.state.setdefault('last_acknowledged_index', 0)
        self.state.setdefault('finished_inputs', {})
        self.state.setdefault('inventory_seed_receipts', [])

    def _fragment(self, fragment):
        from workflow import publish
        did = fragment['document_id']; incoming = self.work/'incoming'
        src = incoming/fragment['prefix']; run = self.work/'runs'/did
        if digest(src/'records.jsonl') != fragment['records_sha256']:
            raise ValueError('Seed fragment changed')
        identity = digest(src/'records.jsonl')
        asset_source = incoming/'seed_assets'/did
        if asset_source.exists():
            shutil.copytree(asset_source,run,dirs_exist_ok=True)
        if not (run/'manifest.json').exists():
            run.mkdir(parents=True,exist_ok=True)
            for name in ['manifest.json','prepare_summary.json','classification.json','duplicate_candidates.json','benchmark_groups.json','benchmark_queue.jsonl']:
                if (src/name).exists(): shutil.copy2(src/name,run/name)
        existing = {r['id']: r for r in rows(run/'records.jsonl')} if (run/'records.jsonl').exists() else {}
        for r in rows(src/'records.jsonl'):
            if r['source_sha256'] != fragment['source_sha256']:
                raise ValueError('Seed source mismatch')
            for prefix in ['crop','context','render']:
                if digest(safe(run,r[prefix+'_path'])) != r[prefix+'_sha256']:
                    raise ValueError('An asset needed by the current input has not arrived')
            if r['id'] in existing:
                if any(existing[r['id']][k] != r[k] for k in ['source_sha256','bbox','crop_sha256','render_sha256','context_sha256']):
                    raise ValueError('Seed would overwrite processed source identity')
                continue
            existing[r['id']] = r
        pages = {p['page']:p for p in rows(run/'document_pages.jsonl')} if (run/'document_pages.jsonl').exists() else {}
        for p in rows(src/'document_pages.jsonl'):
            if p['page'] in pages and pages[p['page']]['render_sha256'] != p['render_sha256']:
                raise ValueError('Seed page identity changed')
            pages[p['page']] = p
        (run/'document_pages.jsonl').write_text(''.join(json.dumps(p,ensure_ascii=False)+'\n' for _,p in sorted(pages.items())),encoding='utf-8')
        m=load(run/'manifest.json'); m['document']['path']=str(incoming/'sources'/(fragment['source_sha256']+'.pdf'))
        m['asset_root']=str(run); m['seed_pages_present']=sorted(pages)
        m['cache_inventory_complete']=len(pages)==m['document']['pages']
        atomic_json(run/'manifest.json',m)
        if identity not in self.state['inventory_seed_receipts']:
            persisted=any(load(p).get('type')=='sequential_seed_fragment' and load(p).get('records_sha256')==identity
                          for p in (run/'import_receipts').glob('*.json'))
            if not persisted:
                publish(run,sorted(existing.values(),key=lambda r:(r['page'],r['id'])),
                        {'type':'sequential_seed_fragment','records_sha256':identity,'pages':fragment['pages'],'source_sha256':fragment['source_sha256']})
            self.state['inventory_seed_receipts'].append(identity)
            checkpoint(run,self.base/'checkpoints'/did)

    def register_one(self, archive):
        import zipfile
        archive=Path(archive)
        with zipfile.ZipFile(archive) as z: manifest=json.loads(z.read('bundle.json'))
        assert_next(self.state,manifest)
        wanted_plan=manifest['plan_sha256']
        if self.state.get('plan_sha256',wanted_plan) != wanted_plan:
            raise ValueError('A different plan is already registered in this BASE')
        # Restore only previously received files, never require future inputs.
        received={**self.state['received_inputs'],str(manifest['bundle_index']):{'path':str(archive),'sha256':digest(archive)}}
        for _,info in sorted(received.items(),key=lambda x:int(x[0])):
            marker=self.work/'received_markers'/info['sha256']
            if not marker.exists():
                if digest(info['path']) != info['sha256']: raise ValueError('Uploaded input changed')
                checked_extract(info['path'],self.work/'incoming','bundle.json')
                marker.parent.mkdir(parents=True,exist_ok=True); marker.write_text('verified')
        self.plan=load(self.work/'incoming/plan.json')
        if digest(self.work/'incoming/plan.json') != wanted_plan: raise ValueError('Plan hash mismatch')
        self.engine=self.work/'incoming/engine'
        if digest(self.engine/'RELEASE.json') != self.plan['release_manifest_sha256']: raise ValueError('Release mismatch')
        verify_release(self.engine); sys.path.insert(0,str(self.engine))
        self.config={**self.plan['config'],'work_root':str(self.work)}
        self.all_jobs=[{**j,'source_path':str(self.work/'incoming/sources'/(j['source_sha256']+'.pdf')),
                        'run':str(self.work/'runs'/j['document_id'])} for j in self.plan['jobs']]
        active=set(manifest['jobs']); self.jobs=[j for j in self.all_jobs if j['job_id'] in active]
        if len(self.jobs)!=len(active): raise ValueError('Unknown active job')
        self.bundle_manifests=[manifest]
        for job in {j['document_id']:j for j in self.jobs}.values():
            if digest(job['source_path'])!=job['source_sha256']: raise ValueError('Missing original PDF for active input')
            run=Path(job['run']); cp=self.base/'checkpoints'/job['document_id']
            if not (run/'manifest.json').exists() and (cp/'index.json').exists(): restore_checkpoint(cp,run)
            if (run/'manifest.json').exists():
                m=load(run/'manifest.json');m['document']['path']=job['source_path'];m['asset_root']=str(run);atomic_json(run/'manifest.json',m)
        for fragment in manifest['seed_fragments']: self._fragment(fragment)
        for done in manifest['completed_jobs']:
            evidence=self.work/'incoming/completed_evidence'/done['job_id']/'results.zip'
            job=next((j for j in self.jobs if j['job_id']==done['job_id']),None)
            if not job or job['source_sha256']!=done['source_sha256'] or digest(evidence)!=done['archive_sha256']:
                raise ValueError('Completed evidence mismatch')
            self.state['completed_external'][done['job_id']]=done
        shared=Path(os.environ.get('BKQUIZ_SHARED_CACHE','/content/drive/MyDrive/BKQuiz_region_v5'))
        os.environ.update(HF_HOME=str(shared/'hf_cache'),PADDLE_PDX_CACHE_HOME=str(shared/'paddle_cache'),V5_VLM_CACHE=str(shared/'vlm_success_cache'),
                          PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True',TOKENIZERS_PARALLELISM='false')
        for cache in (self.work/'incoming/vlm_seed_cache').glob('*.json'):
            target=shared/'vlm_success_cache'/cache.name
            if not target.exists(): target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(cache,target)
        self.state['received_inputs']=received;self.state['plan_sha256']=wanted_plan;self.save()
        return manifest

    def park(self):
        if self.vlm_worker is None:return
        response=self.vlm_worker.call(self.work,self.work,self.work/'ipc',action='park')
        if not response['completed']:
            raise RuntimeError('Unable to park VLM on CPU safely; see worker traceback: '+response.get('traceback',''))

    def group_stage(self,role,pairs):
        if role!='vlm':
            self.park()
            return super().group_stage(role,pairs)
        pending=[(j,p) for j,p in pairs if j['job_id']+':'+p+':vlm' not in self.state['stages']]
        if not pending:return
        if self.vlm_worker is None:
            self.vlm_worker=Worker(self.envs['vlm'],'vlm',self.engine,self.base/'logs')
        for job,phase in pending:self.execute_stage(self.vlm_worker,job,phase)
        if self.keep_model:self.park()
        else:self.vlm_worker.close();self.vlm_worker=None

    def process(self,archive):
        import zipfile
        with zipfile.ZipFile(archive) as z:m=json.loads(z.read('bundle.json'))
        assert_next(self.state,m)
        cached=self.state['finished_inputs'].get(str(m['bundle_index']))
        if cached:
            if cached['input_sha256']!=digest(archive) or digest(cached['archive'])!=cached['archive_sha256']:
                raise ValueError('Previously finished input/result changed')
            return cached
        self.register_one(archive)
        try:
            summary=self.run()
            if not summary['all_jobs_executed']:
                raise RuntimeError('Input has blocked jobs; see summary and diagnostics before advancing')
            for job in {j['document_id']:j for j in self.jobs}.values():
                atomic_json(Path(job['run'])/'sequential_export.json',{'sequence_index':m['bundle_index'],'bundle_id':m['bundle_id']})
            outputs=self.export()
            result={'bundle_index':m['bundle_index'],'bundle_count':m['bundle_count'],'input_sha256':digest(archive),
                    'archive':outputs[0]['path'],'archive_sha256':outputs[0]['sha256'],'summary':summary,
                    'download_confirmed':False}
            self.state['finished_inputs'][str(m['bundle_index'])]=result;self.save()
            return result
        except Exception:
            import traceback
            self.state['errors'].append({'bundle_index':m['bundle_index'],'traceback':traceback.format_exc()});self.save()
            try:
                diagnostics=self.export()
                self.state.setdefault('diagnostic_exports',[]).extend(diagnostics);self.save()
            except Exception:
                self.state['errors'].append({'bundle_index':m['bundle_index'],'export_traceback':traceback.format_exc()});self.save()
            raise

    def acknowledge(self,index,archive_sha256):
        result=self.state['finished_inputs'].get(str(index))
        if index!=self.state['last_acknowledged_index']+1 or not result or result['archive_sha256']!=archive_sha256:
            raise ValueError('Cannot acknowledge an unfinished or out-of-order result')
        if digest(result['archive'])!=archive_sha256: raise ValueError('Result archive changed')
        self.state['last_acknowledged_index']=index
        result['download_confirmed']=True
        result['download_confirmation_method']='user_typed_DA_TAI_after_download_request'
        self.save()
        return {'acknowledged':index,'next_index':index+1}

    def close(self):
        if self.vlm_worker:self.vlm_worker.close();self.vlm_worker=None
