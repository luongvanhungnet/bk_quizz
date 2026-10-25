"""Drive input -> local batches -> verified Drive result -> next input."""
import json
import os
from pathlib import Path
import shutil
import sys
import time
from common import VERSION, INPUT_VERSION, atomic_json, checked_extract, checkpoint, copy_verified, digest, load, restore_checkpoint, restore_pending_path, rows, safe, verify_release, write_compact_archive
from orchestrator import Coordinator, Worker, heartbeat
from telemetry import event, span


def assert_next(state, manifest):
    expected = state.get('last_acknowledged_index', 0) + 1
    if manifest['bundle_index'] != expected:
        raise ValueError(f'Expected input {expected:02d}; publish and commit the previous Drive result first')
    if manifest.get('schema') != INPUT_VERSION or not manifest.get('sequence_required'):
        raise ValueError('Use the new sequential inputs, not the old 14-file set')


class SequentialCoordinator(Coordinator):
    def __init__(self, base, work, environments, keep_model=True, batch_pages=20):
        super().__init__(base, work, environments)
        self.batch_pages=batch_pages
        if self.state.get('schema')!=VERSION:raise ValueError('Use a separate v3 BASE; previous queues are preserved')
        self.state.setdefault('batch_pages',batch_pages)
        if self.state['batch_pages']!=batch_pages:raise ValueError('Keep batch_pages unchanged when resuming this queue')
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
            # The transport distributes cached assets across inputs. Copy only the
            # current fragment's referenced files, not every previously received PNG.
            for record in rows(src/'records.jsonl'):
                for prefix in ['crop','context','render']:
                    name=record[prefix+'_path'];source=safe(asset_source,name);target=safe(run,name)
                    if digest(source)!=record[prefix+'_sha256']:raise ValueError('Seed asset changed')
                    if not target.exists():target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
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
                local=self.work/'inputs'/(info['sha256']+'.zip')
                with span('stage_input',bundle_index=manifest['bundle_index']):
                    copy_verified(info['path'],local,expected_sha256=info['sha256'])
                if digest(local) != info['sha256']: raise ValueError('Drive input changed')
                with span('extract_input',archive=str(local)):checked_extract(local,self.work/'incoming','bundle.json')
                local.unlink()
                marker.parent.mkdir(parents=True,exist_ok=True); marker.write_text('verified')
        self.plan=load(self.work/'incoming/plan.json')
        if digest(self.work/'incoming/plan.json') != wanted_plan: raise ValueError('Plan hash mismatch')
        self.engine=self.work/'incoming/engine'
        if digest(self.engine/'RELEASE.json') != self.plan['release_manifest_sha256']: raise ValueError('Release mismatch')
        verify_release(self.engine); sys.path.insert(0,str(self.engine))
        # Runtime adapter only: avoid read_bytes() loading a multi-GB ZIP to hash it.
        import io_utils
        io_utils.file_sha=digest
        from layout_merge import install
        install()
        self.config={**self.plan['config'],'work_root':str(self.work)}
        self.all_jobs=[{**j,'source_path':str(self.work/'incoming/sources'/(j['source_sha256']+'.pdf')),
                        'run':str(self.work/'runs'/j['document_id'])} for j in self.plan['jobs']]
        active=set(manifest['jobs']); self.jobs=[j for j in self.all_jobs if j['job_id'] in active]
        if len(self.jobs)!=len(active): raise ValueError('Unknown active job')
        self.bundle_manifests=[manifest]
        for job in {j['document_id']:j for j in self.jobs}.values():
            if digest(job['source_path'])!=job['source_sha256']: raise ValueError('Missing original PDF for active input')
            run=Path(job['run']); cp=self.base/'checkpoints'/job['document_id']
            if (cp/'index.json').exists() and (not (run/'manifest.json').exists() or restore_pending_path(cp,run).exists()):
                restore_checkpoint(cp,run)
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
        local_cache=self.work/'vlm_success_cache';local_cache.mkdir(parents=True,exist_ok=True)
        if not getattr(self,'cache_restored',False):
            for cache in (shared/'vlm_success_cache').glob('*.json'):copy_verified(cache,local_cache/cache.name,quiet=True)
            if (self.base/'vlm_cache/index.json').exists():restore_checkpoint(self.base/'vlm_cache',local_cache)
            self.cache_restored=True
        os.environ.update(HF_HOME=str(shared/'hf_cache'),PADDLE_PDX_CACHE_HOME=str(shared/'paddle_cache'),V5_VLM_CACHE=str(local_cache),
                          PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True',TOKENIZERS_PARALLELISM='false')
        for cache in (self.work/'incoming/vlm_seed_cache').glob('*.json'):
            target=local_cache/cache.name
            if not target.exists(): target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(cache,target)
        self.state['received_inputs']=received;self.state['plan_sha256']=wanted_plan;self.save()
        return manifest

    def park(self):
        if self.vlm_worker is None:return
        response=self.vlm_worker.call(self.work,self.work,self.work/'ipc',action='park')
        if not response['completed']:
            raise RuntimeError('Unable to park VLM on CPU safely; see worker traceback: '+response.get('traceback',''))

    def prepare(self):
        from native_batches import prepare_native
        from corpus import audit_event
        for job in {j['document_id']:j for j in self.jobs}.values():
            if shutil.disk_usage(self.work).free < self.config.get('minimum_free_disk_bytes',0):
                raise RuntimeError('Local disk below plan threshold; checkpoints retained')
            print('PREPARE',job['document_id'],flush=True)
            with span('native_prepare',document=job['document_id']),heartbeat('native '+job['document_id']):
                prepare_native(job,self.base/'checkpoints'/job['document_id'],self.batch_pages)
            with span('native_final_checkpoint',document=job['document_id']):checkpoint(job['run'],self.base/'checkpoints'/job['document_id'])
            audit_event(self.work,{'action':'prepare_document_batched','document_id':job['document_id'],'batch_pages':self.batch_pages})

    def group_stage(self,role,pairs):
        if role!='vlm':
            self.park()
            return super().group_stage(role,pairs)
        pending=[(j,p) for j,p in pairs if self.needs_stage(j,p,'vlm')]
        if not pending:return
        if self.vlm_worker is None:
            self.vlm_worker=Worker(self.envs['vlm'],'vlm',self.engine,self.work/'logs')
        for job,phase in pending:self.execute_stage(self.vlm_worker,job,phase)
        if self.keep_model:self.park()
        else:self.vlm_worker.close();self.vlm_worker=None

    def process(self,archive):
        import zipfile
        self.diagnostic_export=False
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
                    'archive':outputs[0]['path'],'archive_sha256':outputs[0]['sha256'],'archive_bytes':outputs[0]['bytes'],'summary':summary,
                    'download_confirmed':False}
            self.state['finished_inputs'][str(m['bundle_index'])]=result;self.save()
            return result
        except Exception:
            import traceback
            self.state['errors'].append({'bundle_index':m['bundle_index'],'traceback':traceback.format_exc()});self.save()
            try:
                self.diagnostic_export=True
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
        result['drive_saved_verified']=True
        result['download_confirmed']=False
        result['advance_method']='hash_verified_Drive_result_no_browser_download_required'
        self.save()
        # Remove only owned, reproducible local work after durable commit.
        import gc
        def prune(path):
            path=Path(path).resolve();root=self.work.resolve()
            if path==root or not path.is_relative_to(root):raise ValueError('Refusing cleanup outside local WORK')
            if path.is_dir():shutil.rmtree(path)
            elif path.exists():path.unlink()
        jobs=getattr(self,'jobs',[])
        for job in jobs:
            for directory in [self.phase_out(job,'discovery').parent,self.work/'page_batches'/job['job_id']]:
                if directory.exists():prune(directory)
            for phase in ['discovery','inference']:
                for directory in [self.work/'restored_packets'/(job['job_id']+'_'+phase),self.work/'packets'/phase/job['job_id']]:
                    if directory.exists():prune(directory)
        for did in {j['document_id'] for j in jobs}:
            remaining=[j for j in self.all_jobs if j['document_id']==did and j['job_id'] not in self.state['completed_external']
                       and j['job_id']+':inference' not in self.state['merged']]
            if not remaining and (self.work/'runs'/did).exists():prune(self.work/'runs'/did)
        for name in ['export_sources','export_log_snapshots','exports','archives','batch_archives']:
            if (self.work/name).exists():prune(self.work/name)
        gc.collect();event('input_committed',index=index,drive_archive=result['archive'])
        return {'acknowledged':index,'next_index':index+1}

    def export(self):
        """Local compact archive -> verified Drive copy. Never browser-download."""
        files={}
        for name in ['summary.json','queue_state.json','environments.json','hardware_profile.json']:
            if (self.base/name).exists():files[name]=self.base/name
        for p in (self.base/'preflight_runs').rglob('*'):
            if p.is_file():files['preflight_runs/'+p.relative_to(self.base/'preflight_runs').as_posix()]=p
        for root,prefix in [(self.work/'logs','logs'),(self.work/'telemetry','telemetry'),(self.base/'environment_logs','environment_logs')]:
            for p in root.rglob('*'):
                if p.is_file() and p.suffix!='.snapshot':files[f'{prefix}/{p.relative_to(root).as_posix()}']=p
        manifest=self.bundle_manifests[0];phases=[];runs=[]
        for job in self.jobs:
            for phase in ['discovery','inference']:
                key=job['job_id']+':'+phase
                previous=self.state['merged'].get(key)
                if not previous:continue
                packet=self.packet(job,phase);prefix=f'packets/{job["job_id"]}_{phase}'
                for p in packet.rglob('*'):
                    if p.is_file() and p.name!='v5_colab_input.zip': files[prefix+'/'+p.relative_to(packet).as_posix()]=p
                source=Path(previous['archive']);local=self.work/'export_sources'/source.name
                copy_verified(source,local,expected_sha256=previous['archive_sha256'])
                result_name=f'results/{source.name}';files[result_name]=local
                phases.append({'job_id':job['job_id'],'phase':phase,'packet_dir':prefix,
                               'packet_manifest_sha256':digest(packet/'manifest.json'),'results':result_name})
            # Preserve child manifests, exact raw output and failures, including unmerged phases.
            for key,info in self.state.get('page_batches',{}).items():
                if not key.startswith(job['job_id']+':'):continue
                archive=Path(info['archive']);local=Path(info.get('local_archive','__not_available__'))
                if not local.is_file():
                    local=self.work/'export_sources'/archive.name
                    copy_verified(archive,local,expected_sha256=info['archive_sha256'])
                if digest(local)!=info['archive_sha256']:raise ValueError('Batch audit archive changed')
                files['batch_audit/'+archive.name]=local
        for did,job in {j['document_id']:j for j in self.jobs}.items():
            run=Path(job['run'])
            if not (run/'manifest.json').exists():continue
            runs.append(did)
            for p in run.rglob('*'):
                if p.is_file() and p.suffix not in {'.sqlite3','.next'} and not p.name.endswith(('-wal','-shm')):
                    files[f'runs/{did}/{p.relative_to(run).as_posix()}']=p
            # The original PDF is included once, rather than depending on future inputs.
            files[f'sources/{job["source_sha256"]}.pdf']=Path(job['source_path'])
        metadata={'schema':VERSION,'bundle_id':manifest['bundle_id'],'plan_sha256':self.state['plan_sha256'],
                  'original_jobs_sha256':self.plan['jobs_sha256'],'bundle_count':manifest['bundle_count'],
                  'sequence_index':manifest['bundle_index'],'phase_results':phases,'runs':runs,
                  'externally_completed_jobs':[j['job_id'] for j in self.jobs if j['job_id'] in self.state['completed_external']],
                  'human_verified':False,'semantic_verified':False,'training_exported':False}
        metadata['diagnostic_only']=getattr(self,'diagnostic_export',False)
        runtime=Path(__file__).resolve().parent
        for p in runtime.glob('*.py'):
            if not p.name.startswith(('test_','build_')):files['orchestrator_runtime/'+p.name]=p
        metadata['input_schema']=INPUT_VERSION
        kind='diagnostics' if metadata['diagnostic_only'] else 'results'
        local=self.work/'exports'/f'v5_drive_{kind}_{manifest["bundle_id"]}_{time.time_ns()}.zip'
        # Telemetry is append-only; snapshot it so content hashes cannot race ZIP writes.
        for name,p in list(files.items()):
            if name.startswith(('telemetry/','logs/')):
                snapshot=self.work/'export_log_snapshots'/name
                snapshot.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,snapshot);files[name]=snapshot
        with span('export_zip',logical_files=len(files)):
            stats=write_compact_archive(local,files,metadata)
        event('export_size',zip_bytes=local.stat().st_size,logical_bytes=stats['logical_bytes'],unique_bytes=stats['unique_bytes'],
              duplicate_bytes_avoided=stats['duplicate_bytes_avoided'])
        receipt=copy_verified(local,self.base/'downloads'/local.name)
        outputs=[receipt];atomic_json(self.base/'downloads/latest_index.json',{'files':outputs,'plan_sha256':self.state['plan_sha256']})
        print('DRIVE_SAVED',receipt['path'],'bytes',receipt['bytes'],'SHA256',receipt['sha256'],flush=True)
        return outputs

    def close(self):
        if self.vlm_worker:self.vlm_worker.close();self.vlm_worker=None
