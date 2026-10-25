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
from common import VERSION, atomic_json, checked_extract, checkpoint, digest, load, restore_checkpoint, rows, safe, verify_release, write_archive

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
        manifests = []
        for archive in archives:
            m = checked_extract(archive, self.work / 'incoming', 'bundle.json')
            if m['schema'] != VERSION:
                raise ValueError('Unknown upload schema')
            manifests.append(m)
        if not manifests:
            raise ValueError('No upload ZIPs selected')
        count = manifests[0]['bundle_count']
        if len(manifests) != count or {m['bundle_index'] for m in manifests} != set(range(1, count + 1)):
            raise ValueError(f'Upload all {count} distinct input bundles before starting the queue')
        if len({m['plan_sha256'] for m in manifests}) != 1:
            raise ValueError('Mixed queue plans')
        first_runtime = {n: h for n,h in manifests[0]['files'].items() if n.startswith(('runtime/', 'engine/'))}
        if any({n: h for n,h in m['files'].items() if n.startswith(('runtime/', 'engine/'))} != first_runtime for m in manifests):
            raise ValueError('Mixed runtime versions across upload bundles')
        self.plan = load(self.work / 'incoming/plan.json')
        if digest(self.work / 'incoming/plan.json') != manifests[0]['plan_sha256']:
            raise ValueError('Plan identity mismatch')
        key = manifests[0]['plan_sha256']
        if self.state.get('plan_sha256', key) != key:
            raise ValueError('Drive queue contains a different plan; use a new BASE')
        self.state['plan_sha256'] = key
        self.bundle_manifests = sorted(manifests, key=lambda m: m['bundle_index'])
        self.engine = self.work / 'incoming/engine'
        if digest(self.engine / 'RELEASE.json') != self.plan['release_manifest_sha256']:
            raise ValueError('Release identity mismatch')
        verify_release(self.engine)
        sys.path.insert(0, str(self.engine))
        self.config = {**self.plan['config'], 'work_root': str(self.work)}
        self.jobs = []
        for original in self.plan['jobs']:
            job = {**original, 'source_path': str(self.work / 'incoming/sources' / (original['source_sha256'] + '.pdf')),
                   'run': str(self.work / 'runs' / original['document_id'])}
            if not Path(job['source_path']).exists() or digest(job['source_path']) != job['source_sha256']:
                raise ValueError('Missing or changed original source: ' + job['document_id'])
            self.jobs.append(job)
        documents = {j['document_id']: j for j in self.jobs}
        for did, job in documents.items():
            run = Path(job['run'])
            cp = self.base / 'checkpoints' / did
            if not (run / 'manifest.json').exists() and (cp / 'index.json').exists():
                restore_checkpoint(cp, run)
            seed = self.work / 'incoming/seeds' / did
            if not (run / 'manifest.json').exists() and seed.exists():
                shutil.copytree(seed, run, dirs_exist_ok=True)
                atomic_json(run / 'seed_provenance.json', {'manifest_sha256': digest(seed / 'manifest.json'),
                                                         'records_sha256': digest(seed / 'records.jsonl'), 'reviews_included': False})
            if (run / 'manifest.json').exists():
                m = load(run / 'manifest.json')
                if m['document']['sha256'] != job['source_sha256']:
                    raise ValueError('Restored run source mismatch')
                m['document']['path'] = job['source_path']
                m['asset_root'] = str(run)
                atomic_json(run / 'manifest.json', m)
        for m in self.bundle_manifests:
            for done in m['completed_jobs']:
                job = next(j for j in self.jobs if j['job_id'] == done['job_id'])
                evidence = self.work / 'incoming/completed_evidence' / done['job_id'] / 'results.zip'
                if job['source_sha256'] != done['source_sha256'] or digest(evidence) != done['archive_sha256']:
                    raise ValueError('Completed job evidence mismatch')
                self.state['completed_external'][done['job_id']] = done
        shared = Path('/content/drive/MyDrive/BKQuiz_region_v5')
        os.environ.update(HF_HOME=str(shared / 'hf_cache'), PADDLE_PDX_CACHE_HOME=str(shared / 'paddle_cache'),
                          V5_VLM_CACHE=str(shared / 'vlm_success_cache'), PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True', TOKENIZERS_PARALLELISM='false')
        for cache in (self.work / 'incoming/vlm_seed_cache').glob('*.json'):
            target = Path(os.environ['V5_VLM_CACHE']) / cache.name
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cache, target)
        self.save()

    def prepare(self):
        from corpus import prepare_documents
        seen = set()
        for job in self.jobs:
            if job['document_id'] in seen:
                continue
            seen.add(job['document_id'])
            if shutil.disk_usage(self.work).free < self.config.get('minimum_free_disk_bytes', 0):
                raise RuntimeError('Runtime disk free space is below the corpus plan threshold; retained checkpoints allow continuation')
            print('PREPARE', job['document_id'], flush=True)
            run = Path(job['run'])
            if run.exists() and not (run / 'manifest.json').exists():
                run.rename(run.with_name(run.name + '_incomplete_' + str(time.time_ns())))
            with heartbeat('native/checkpoint ' + job['document_id']):
                prepare_documents(self.config, [job])
                checkpoint(run, self.base / 'checkpoints' / job['document_id'])

    def packet(self, job, phase):
        from corpus import package_job
        key = job['job_id'] + ':' + phase
        previous = self.state['packets'].get(key)
        if previous:
            folder = self.work / 'restored_packets' / key.replace(':', '_')
            if not (folder / 'manifest.json').exists():
                if digest(previous['archive']) != previous['archive_sha256']:
                    raise ValueError('Saved packet changed')
                extract_packet(previous['archive'], folder)
            if digest(folder / 'manifest.json') != previous['manifest_sha256']:
                raise ValueError('Saved manifest changed')
            return folder
        archive = package_job(self.config, job, phase)
        folder = archive.parent
        target = self.base / 'packets' / f'{job["job_id"]}_{phase}.zip'
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archive, target)
        self.state['packets'][key] = {'archive': str(target), 'archive_sha256': digest(target),
                                      'manifest_sha256': digest(folder / 'manifest.json')}
        self.save()
        return folder

    def phase_out(self, job, phase):
        return self.base / 'raw_results' / job['job_id'] / phase

    def execute_stage(self, worker, job, phase, visual_only=False):
        key = job['job_id'] + ':' + phase + ':' + worker.role
        if key in self.state['stages']:
            return self.state['stages'][key]
        packet = self.packet(job, phase)
        out = self.phase_out(job, phase) / ('vlm' if worker.role == 'vlm' else worker.role if worker.role == 'docling' else 'paddle_' + worker.role)
        print('START', key, flush=True)
        response = worker.call(packet, out, self.work / 'ipc', visual_only)
        response.update(packet_manifest_sha256=digest(packet / 'manifest.json'))
        self.state['stages'][key] = response
        atomic_json(out / f'orchestrator_stage_{time.time_ns()}.json', response)
        self.save()
        print('END', key, json.dumps({k: v for k, v in response.items() if k not in {'traceback'}}, ensure_ascii=False)[:1600], flush=True)
        return response

    def group_stage(self, role, pairs):
        pending = [(j, phase) for j, phase in pairs if j['job_id'] + ':' + phase + ':' + role not in self.state['stages']]
        if not pending:
            return
        python = self.envs['docling' if role == 'docling' else 'vlm' if role == 'vlm' else 'paddle']
        worker = Worker(python, role, self.engine, self.base / 'logs', {'CUDA_VISIBLE_DEVICES': ''} if role == 'docling' else None)
        try:
            for job, phase in pending:
                self.execute_stage(worker, job, phase, visual_only=phase == 'inference' and job['layout_required'])
        finally:
            # Closing owned processes releases their GPU allocations before Qwen starts.
            worker.close()

    def result_archive(self, job, phase):
        out = self.phase_out(job, phase)
        out.mkdir(parents=True, exist_ok=True)
        packet = self.packet(job, phase)
        stages = {k: v for k, v in self.state['stages'].items() if k.startswith(job['job_id'] + ':' + phase + ':')}
        atomic_json(out / 'orchestrator_status.json', {'packet_manifest_sha256': digest(packet / 'manifest.json'),
                    'stages': stages, 'semantic_verified': False, 'human_verified': False})
        files = {p.relative_to(out).as_posix(): p for p in out.rglob('*') if p.is_file()}
        signature = __import__('hashlib').sha256(json.dumps({n: digest(p) for n, p in files.items()}, sort_keys=True).encode()).hexdigest()
        target = self.base / 'archives' / f'{job["job_id"]}_{phase}_{signature[:16]}.zip'
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
        summary = merge_job(self.config, job, self.packet(job, phase), archive)
        checkpoint(job['run'], self.base / 'checkpoints' / job['document_id'])
        self.state['merged'][key] = {'archive': str(archive), 'archive_sha256': digest(archive), 'summary': summary}
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
        bad = {k: v for k, v in self.state['stages'].items() if not v.get('completed') or v.get('result', {}).get('status') != 'ok'}
        summary = {'schema': VERSION, 'source_jobs': len(self.jobs), 'completed_jobs': len(completed),
                   'pending_jobs': [j['job_id'] for j in self.jobs if j['job_id'] not in completed], 'blocked_layout_jobs': blocked,
                   'stages_with_errors': len(bad), 'all_jobs_executed': len(completed) == len(self.jobs),
                   'all_stages_successful': not bad and len(completed) == len(self.jobs),
                   'quality_certified': False, 'human_decisions_auto_created': 0, 'training_exported': False}
        atomic_json(self.base / 'summary.json', summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
        return summary

    def export(self):
        outputs = []
        owners = {}
        for m in self.bundle_manifests:
            for jid in m['jobs']:
                owners[next(j['document_id'] for j in self.jobs if j['job_id'] == jid)] = m['bundle_id']
        stamp = str(time.time_ns())
        for m in self.bundle_manifests:
            files = {'summary.json': self.base / 'summary.json'} if (self.base / 'summary.json').exists() else {}
            files['queue_state.json'] = self.state_path
            if m['bundle_id'] == self.bundle_manifests[0]['bundle_id']:
                for directory in ['logs', 'environment_logs']:
                    for path in (self.base / directory).glob('*'):
                        if path.is_file():
                            files[f'{directory}/{path.name}'] = path
            phase_results = []
            for jid in m['jobs']:
                # Preserve partial stages and stack traces even if layout could not be merged.
                raw_root = self.base / 'raw_results' / jid
                for path in raw_root.rglob('*'):
                    if path.is_file():
                        files[f'raw_results/{jid}/{path.relative_to(raw_root).as_posix()}'] = path
                for phase in ['discovery', 'inference']:
                    key = jid + ':' + phase
                    if key not in self.state['merged']:
                        continue
                    result = self.state['merged'][key]
                    files[f'packets/{jid}_{phase}.zip'] = Path(self.state['packets'][key]['archive'])
                    files[f'results/{jid}_{phase}.zip'] = Path(result['archive'])
                    phase_results.append({'job_id': jid, 'phase': phase, 'packet': f'packets/{jid}_{phase}.zip',
                                          'results': f'results/{jid}_{phase}.zip'})
            included_runs = []
            for did, owner in owners.items():
                if owner != m['bundle_id']:
                    continue
                run = self.work / 'runs' / did
                if not (run / 'manifest.json').exists():
                    continue
                included_runs.append(did)
                for path in run.rglob('*'):
                    if path.is_file() and path.suffix != '.sqlite3' and not path.name.endswith(('-wal', '-shm')):
                        files[f'runs/{did}/{path.relative_to(run).as_posix()}'] = path
            output = self.base / 'downloads' / f'v5_results_{m["bundle_id"]}_{stamp}.zip'
            write_archive(output, files, {'schema': VERSION, 'bundle_id': m['bundle_id'], 'plan_sha256': self.state['plan_sha256'],
                          'original_jobs_sha256': self.plan['jobs_sha256'], 'bundle_count': m.get('bundle_count',len(self.bundle_manifests)),
                          'sequence_index': m.get('bundle_index',1),
                          'phase_results': phase_results, 'runs': included_runs,
                          'externally_completed_jobs': [jid for jid in m['jobs'] if jid in self.state['completed_external']],
                          'human_verified': False, 'semantic_verified': False}, 'return.json')
            outputs.append({'path': str(output), 'sha256': digest(output), 'bytes': output.stat().st_size})
            print('EXPORT', output, flush=True)
        atomic_json(self.base / 'downloads/latest_index.json', {'files': outputs, 'plan_sha256': self.state['plan_sha256']})
        return outputs


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--work', type=Path, default=Path('/content/bkquiz_v5_queue'))
    p.add_argument('--inputs', type=Path, required=True, help='JSON list of the 14 persistent uploaded paths')
    p.add_argument('--export-only', action='store_true')
    a = p.parse_args()
    c = Coordinator(a.base, a.work, load(a.base / 'environments.json'))
    c.register([Path(s) for s in load(a.inputs)])
    try:
        if not a.export_only:
            c.run()
    finally:
        if (c.work / 'runs').exists():
            c.export()


if __name__ == '__main__':
    main()
