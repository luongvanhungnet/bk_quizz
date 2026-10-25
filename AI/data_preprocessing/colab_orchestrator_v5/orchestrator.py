"""Resume a corpus queue: native -> discovery -> specialists -> one resident VLM."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
import zipfile
import stat
import threading
from contextlib import contextmanager
from common import VERSION, atomic_json, checked_extract, checkpoint, copy_verified, digest, load, restore_checkpoint, rows, safe, verify_release, write_archive
from telemetry import event, span

ROOT = Path(__file__).resolve().parent


@contextmanager
def heartbeat(label):
    stop = threading.Event()
    def report():
        started = time.monotonic()
        while not stop.wait(30):
            print(f'Heartbeat {label}: {time.monotonic()-started:.0f}s', flush=True)
    thread = threading.Thread(target=report, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1)


def extract_packet(archive, target):
    target = Path(target)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError('Corrupt packet ZIP')
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate packet members')
        for name in names:
            safe(target, name)
        if any(stat.S_ISLNK(info.external_attr >> 16) for info in z.infolist()):
            raise ValueError('Packet symlinks are not accepted')
        for name in names:
            if name.endswith('/'):
                continue
            p = safe(target, name)
            p.parent.mkdir(parents=True, exist_ok=True)
            with z.open(name) as source, p.open('wb') as sink:
                shutil.copyfileobj(source, sink, 1024 * 1024)
    return verify_packet(target)


def verify_packet(target):
    target=Path(target)
    m = load(target / 'manifest.json')
    expected = {**m['code_sha256'], m['parser_input']: m['parser_input_sha256']}
    for q in m['requests']:
        expected[q['image']] = q['crop_sha256']
        expected[q['vlm_image']] = q['vlm_image_sha256']
    for name, wanted in expected.items():
        if digest(safe(target, name)) != wanted:
            raise ValueError('Packet identity mismatch: ' + name)
    return m


class Worker:
    def __init__(self, python, role, engine, logs, env=None):
        self.role = role
        self.log_path = Path(logs) / f'{role}_{time.time_ns()}.log'
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log = self.log_path.open('w', encoding='utf-8')
        child_env = {**os.environ, **(env or {}), 'PYTHONUNBUFFERED': '1'}
        if role=='docling' and (env or {}).get('HF_HOME'):child_env.pop('TRANSFORMERS_CACHE',None)
        child_env['PATH'] = str(Path(python).parent) + os.pathsep + child_env.get('PATH', '')
        self.process = subprocess.Popen([str(python), str(ROOT / 'warm_worker.py'), '--engine', str(engine), '--role', role],
                                        stdin=subprocess.PIPE, stdout=self.log, stderr=subprocess.STDOUT, text=True, encoding='utf-8', env=child_env)

    def call(self, packet, out, control, visual_only=False, action='process'):
        response = Path(control) / f'{self.role}_{time.time_ns()}.json'
        response.parent.mkdir(parents=True, exist_ok=True)
        command = {'action': action, 'packet': str(packet), 'out': str(out), 'response': str(response), 'visual_only': visual_only}
        self.process.stdin.write(json.dumps(command) + '\n')
        self.process.stdin.flush()
        started = last = time.monotonic()
        while not response.exists():
            if self.process.poll() is not None:
                raise RuntimeError(f'{self.role} worker exited {self.process.returncode}; log={self.log_path}')
            timeout=float(os.environ.get('BKQUIZ_MODEL_TIMEOUT_SECONDS','900'))
            if time.monotonic()-started>timeout:
                from stage_guard import terminate_tree,StageTimeout
                terminate_tree(self.process)
                raise StageTimeout(f'{self.role} exceeded {timeout}s; unfinished unit not committed; log={self.log_path}')
            if time.monotonic() - last > 30:
                print(f'Heartbeat {self.role}: {Path(packet).parent.name}, elapsed {time.monotonic() - started:.0f}s', flush=True)
                last = time.monotonic()
            time.sleep(.25)
        return {**load(response), 'worker_log': str(self.log_path)}

    def close(self):
        if self.process.poll() is None:
            try:
                self.process.stdin.write('{"action":"close"}\n')
                self.process.stdin.flush()
                self.process.wait(timeout=30)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
        self.log.close()
        if self.process.stdin:
            self.process.stdin.close()


class Coordinator:
    def __init__(self, base, work, environments):
        self.base, self.work = Path(base), Path(work)
        self.envs = environments
        self.base.mkdir(parents=True, exist_ok=True)
        self.work.mkdir(parents=True, exist_ok=True)
        self.state_path = self.base / 'queue_state.json'
        self.state = load(self.state_path) if self.state_path.exists() else {'schema': VERSION, 'packets': {}, 'stages': {}, 'merged': {}, 'completed_external': {}, 'errors': []}

    def save(self):
        self.state['updated_at_unix'] = time.time()
        atomic_json(self.state_path, self.state)

    def register(self, archives):
        raise NotImplementedError('Use SequentialCoordinator via daemon.py for the Drive queue')

    def prepare(self):
        raise NotImplementedError('Use SequentialCoordinator via daemon.py for the Drive queue')

    def packet(self, job, phase):
        from corpus import package_job
        key = job['job_id'] + ':' + phase
        previous = self.state['packets'].get(key)
        if previous:
            existing=Path(previous.get('local_folder','__not_available__'))
            if (existing/'manifest.json').exists() and digest(existing/'manifest.json')==previous['manifest_sha256']:
                return existing
            folder = self.work / 'restored_packets' / key.replace(':', '_')
            if not (folder / 'manifest.json').exists():
                local=self.work/'restored_zips'/(previous['archive_sha256']+'.zip')
                copy_verified(previous['archive'],local,expected_sha256=previous['archive_sha256'])
                if digest(local) != previous['archive_sha256']:
                    raise ValueError('Saved packet changed')
                with span('restore_packet',job=job['job_id'],phase=phase):extract_packet(local, folder)
                local.unlink()
            if digest(folder / 'manifest.json') != previous['manifest_sha256']:
                raise ValueError('Saved manifest changed')
            return folder
        with span('package_job',job=job['job_id'],phase=phase):archive = package_job(self.config, job, phase)
        folder = archive.parent
        target = self.base / 'packets' / f'{job["job_id"]}_{phase}.zip'
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_verified(archive, target)
        self.state['packets'][key] = {'archive': str(target), 'archive_sha256': digest(target),
                                      'manifest_sha256': digest(folder / 'manifest.json'),'local_folder':str(folder)}
        self.save()
        return folder

    def phase_out(self, job, phase):
        return self.work / 'raw_results' / job['job_id'] / phase

    def execute_stage(self, worker, job, phase, visual_only=False):
        from page_batches import split_packet, normalized_files
        import gc
        key = job['job_id'] + ':' + phase + ':' + worker.role
        existing_out=self.phase_out(job,phase)/('vlm' if worker.role=='vlm' else worker.role if worker.role=='docling' else 'paddle_'+worker.role)
        if key in self.state['stages'] and (existing_out/'machine_files.json').exists():
            return self.state['stages'][key]
        packet = self.packet(job, phase)
        out = self.phase_out(job, phase) / ('vlm' if worker.role == 'vlm' else worker.role if worker.role == 'docling' else 'paddle_' + worker.role)
        legacy=self.state.get('legacy_stage_outputs',{}).get(key)
        if legacy:
            if legacy['response'].get('packet_manifest_sha256')!=digest(packet/'manifest.json'):
                raise ValueError('Legacy stage packet identity mismatch')
            files={}
            with span('reuse_v2_stage',stage_key=key):
                for p in Path(legacy['folder']).rglob('*'):
                    if not p.is_file():continue
                    relative=p.relative_to(legacy['folder']).as_posix();target=out/relative
                    copy_verified(p,target,quiet=True)
                    files[f'{out.name}/{relative}']=str(target)
            atomic_json(out/'machine_files.json',files)
            self.state['stages'][key]=legacy['response'];self.save()
            return legacy['response']
        print('START', key, flush=True)
        batch_states=self.state.setdefault('page_batches',{})
        responses=[];machine_files={}
        for child in split_packet(packet,self.work/'page_batches'/job['job_id']/phase,self.batch_pages):
            batch_key=key+':'+child.name;batch_out=out/'chunks'/child.name
            from warm_worker import select_tasks
            cm=load(child/'manifest.json')
            if worker.role=='vlm' and not any(q.get('use_vlm') for q in cm['requests']):
                event('batch_skipped',stage_key=key,batch=child.name,reason='no_vlm_requests');continue
            if worker.role not in {'vlm','docling'} and not select_tasks(cm,worker.role,visual_only):
                event('batch_skipped',stage_key=key,batch=child.name,reason='no_specialist_requests');continue
            old=batch_states.get(batch_key)
            with span('model_batch',stage_key=key,batch=child.name):
                if old:
                    restore=self.work/'batch_restore'/__import__('hashlib').sha256(batch_key.encode()).hexdigest()[:20]
                    marker=batch_out/'_restored.json'
                    if not marker.exists() or load(marker).get('checkpoint_sha256')!=old['archive_sha256']:
                        local=restore.with_suffix('.zip'); copy_verified(old['archive'],local,expected_sha256=old['archive_sha256'])
                        if digest(local)!=old['archive_sha256']:raise ValueError('Batch checkpoint changed')
                        checkpoint_manifest=checked_extract(local,restore,'batch.json')
                        if checkpoint_manifest.get('stage_key')!=key or checkpoint_manifest.get('response')!=old['response']:
                            raise ValueError('Batch checkpoint stage/response mismatch')
                        from batch_restore import restore_output
                        restore_output(restore,batch_out,checkpoint_manifest)
                        shutil.copyfile(restore/'child_manifest.json',child/'manifest.json')
                        shutil.copyfile(restore/'child_parser_input.pdf',child/load(child/'manifest.json')['parser_input'])
                        atomic_json(batch_out/'_restored.json',{'checkpoint_sha256':old['archive_sha256']})
                        restore_root=(self.work/'batch_restore').resolve()
                        if restore.resolve()==restore_root or not restore.resolve().is_relative_to(restore_root):
                            raise ValueError('Refusing cleanup outside owned batch restore directory')
                        local.unlink();shutil.rmtree(restore)
                    response=old['response']
                    event('batch_reused',stage_key=key,batch=child.name)
                else:
                    print('BATCH',batch_key,flush=True)
                    response=worker.call(child,batch_out,self.work/'ipc',visual_only)
                    if worker.role=='docling' and (not response.get('completed') or response.get('result',{}).get('status')!='ok'):
                        atomic_json(batch_out/'docling_fatal.json',response)
                        raise RuntimeError('Docling failed; stop this unit after the first failed batch. Fix model/preflight before retry: '+str(response))
                    response['child_packet_manifest_sha256']=digest(child/'manifest.json')
                    if worker.role=='vlm':
                        with span('vlm_cache_checkpoint',batch=child.name):checkpoint(self.work/'vlm_success_cache',self.base/'vlm_cache')
                responses.append(response)
                machine_files.update(normalized_files(packet,child,batch_out,worker.role))
                if not old:
                    files={'output/'+p.relative_to(batch_out).as_posix():p for p in batch_out.rglob('*') if p.is_file()}
                    files.update({'child_manifest.json':child/'manifest.json','child_parser_input.pdf':child/load(child/'manifest.json')['parser_input']})
                    local=self.work/'batch_archives'/f'{__import__("hashlib").sha256(batch_key.encode()).hexdigest()[:20]}_{time.time_ns()}.zip'
                    with span('batch_checkpoint',stage_key=key,batch=child.name):
                        write_archive(local,files,{'schema':VERSION,'stage_key':key,'response':response},'batch.json')
                        receipt=copy_verified(local,self.base/'batch_checkpoints'/local.name)
                    batch_states[batch_key]={'archive':receipt['path'],'archive_sha256':receipt['sha256'],'response':response,'local_archive':str(local)}
                    self.save()
                # All large task/parser objects live in the worker for <= batch_pages pages.
                gc.collect()
        response={'completed':all(r.get('completed') for r in responses),
                  'result':{'status':'ok' if all(r.get('completed') and r.get('result',{}).get('status')=='ok' for r in responses) else 'error',
                            'batches':len(responses)},
                  'seconds':sum(r.get('seconds',0) for r in responses),'role':worker.role,
                  'batch_responses':responses,'worker_log':str(worker.log_path)}
        atomic_json(out/'machine_files.json',{n:str(p) for n,p in machine_files.items()})
        response.update(packet_manifest_sha256=digest(packet / 'manifest.json'))
        self.state['stages'][key] = response
        atomic_json(out / f'orchestrator_stage_{time.time_ns()}.json', response)
        self.save()
        print('END', key, json.dumps({k: v for k, v in response.items() if k not in {'traceback'}}, ensure_ascii=False)[:1600], flush=True)
        return response

    def group_stage(self, role, pairs):
        pending = [(j, phase) for j, phase in pairs if self.needs_stage(j,phase,role)]
        if not pending:
            return
        python = self.envs['docling' if role == 'docling' else 'vlm' if role == 'vlm' else 'paddle']
        extra={'CUDA_VISIBLE_DEVICES':''} if role=='docling' else {}
        if role=='docling' and os.environ.get('BKQUIZ_DOCLING_HF_HOME'):
            extra['HF_HOME']=os.environ['BKQUIZ_DOCLING_HF_HOME']
            extra['HF_HUB_CACHE']=str(Path(extra['HF_HOME'])/'hub')
        worker = Worker(python, role, self.engine, self.work / 'logs', extra)
        try:
            for job, phase in pending:
                self.execute_stage(worker, job, phase, visual_only=phase == 'inference' and job['layout_required'])
        finally:
            # Closing owned processes releases their GPU allocations before Qwen starts.
            worker.close()

    def needs_stage(self,job,phase,role):
        prefix=job['job_id']+':'+phase
        if prefix in self.state['merged']:return False
        out=self.phase_out(job,phase)/('vlm' if role=='vlm' else role if role=='docling' else 'paddle_'+role)
        return prefix+':'+role not in self.state['stages'] or not (out/'machine_files.json').exists()

    def result_archive(self, job, phase):
        out = self.phase_out(job, phase)
        out.mkdir(parents=True, exist_ok=True)
        packet = self.packet(job, phase)
        stages = {k: v for k, v in self.state['stages'].items() if k.startswith(job['job_id'] + ':' + phase + ':')}
        atomic_json(out / 'orchestrator_status.json', {'packet_manifest_sha256': digest(packet / 'manifest.json'),
                    'stages': stages, 'semantic_verified': False, 'human_verified': False})
        files={'orchestrator_status.json':out/'orchestrator_status.json'}
        for manifest in out.glob('*/machine_files.json'):
            for n,p in load(manifest).items(): files[n]=Path(p)
        signature = __import__('hashlib').sha256(json.dumps({n: digest(p) for n, p in files.items()}, sort_keys=True).encode()).hexdigest()
        target = self.work / 'archives' / f'{job["job_id"]}_{phase}_{signature[:16]}.zip'
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_suffix('.next')
            with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as z:
                for n, p in files.items():
                    z.write(p, n)
            os.replace(temp, target)
        return target

    def merge(self, job, phase):
        from corpus import merge_job
        key = job['job_id'] + ':' + phase
        if key in self.state['merged']:
            return
        archive = self.result_archive(job, phase)
        with span('merge',job=job['job_id'],phase=phase):
            summary = merge_job(self.config, job, self.packet(job, phase), archive)
        with span('merge_checkpoint',job=job['job_id'],phase=phase):
            checkpoint(job['run'], self.base / 'checkpoints' / job['document_id'])
        receipt=copy_verified(archive,self.base/'archives'/archive.name)
        self.state['merged'][key] = {'archive': receipt['path'], 'archive_sha256': receipt['sha256'], 'summary': summary}
        self.save()

    def run(self):
        self.prepare()
        fresh = [j for j in self.jobs if j['job_id'] not in self.state['completed_external']]
        discovery = [(j, 'discovery') for j in fresh if j['layout_required']]
        cached = [(j, 'inference') for j in fresh if not j['layout_required']]
        self.group_stage('ocr', discovery + cached)
        self.group_stage('structure', discovery)
        self.group_stage('docling', discovery)
        for job, phase in discovery:
            try:
                self.merge(job, phase)
            except Exception:
                self.state['errors'].append({'job_id': job['job_id'], 'phase': phase, 'traceback': traceback.format_exc()})
                self.save()
        inference = []
        blocked = []
        for job in fresh:
            m = load(Path(job['run']) / 'manifest.json')
            if job['layout_required'] and m.get('layout_inventory_status') != 'ready':
                blocked.append(job['job_id'])
            else:
                inference.append((job, 'inference'))
        self.state['blocked_layout_jobs'] = blocked
        self.save()
        self.group_stage('ocr', inference)
        self.group_stage('formula', inference)
        self.group_stage('table', inference)
        vlm = [(j, phase) for j, phase in inference if any(q.get('use_vlm') for q in load(self.packet(j, phase) / 'manifest.json')['requests'])]
        self.group_stage('vlm', vlm)
        for job, phase in inference:
            self.merge(job, phase)
        completed = [j['job_id'] for j in self.jobs if j['job_id'] in self.state['completed_external'] or j['job_id'] + ':inference' in self.state['merged']]
        bad_all = {k: v for k, v in self.state['stages'].items() if not v.get('completed') or v.get('result', {}).get('status') != 'ok'}
        current_jobs={j['job_id'] for j in self.jobs}
        bad={k:v for k,v in bad_all.items() if k.split(':')[0] in current_jobs}
        historical={k:v for k,v in bad_all.items() if k.split(':')[0] not in current_jobs}
        summary = {'schema': VERSION, 'source_jobs': len(self.jobs), 'completed_jobs': len(completed),
                   'pending_jobs': [j['job_id'] for j in self.jobs if j['job_id'] not in completed], 'blocked_layout_jobs': blocked,
                   'stages_with_errors': len(bad),'historical_stages_with_errors':len(historical),
                   'cumulative_stages_with_errors':len(bad_all),'all_jobs_executed': len(completed) == len(self.jobs),
                   'all_stages_successful': not bad and len(completed) == len(self.jobs),
                   'quality_certified': False, 'human_decisions_auto_created': 0, 'training_exported': False}
        atomic_json(self.base / 'summary.json', summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
        return summary

    def export(self):
        raise NotImplementedError('Use SequentialCoordinator via daemon.py for the Drive queue')


def main():
    raise SystemExit('Use the Drive notebook/client.py or daemon.py; the all-input CLI is not supported in v3')


if __name__ == '__main__':
    main()
