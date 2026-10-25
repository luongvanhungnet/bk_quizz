"""Build exactly 14 upload containers around the unchanged 148 source jobs."""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys
import zipfile
from common import VERSION, atomic_json, digest, load, rows, verify_release, write_archive

ROOT = Path(__file__).resolve().parent
AI = ROOT.parent.parent


def partition(jobs, count=14):
    if not 1 <= count <= len(jobs):
        raise ValueError('Invalid upload count')
    return [jobs[i * len(jobs) // count:(i + 1) * len(jobs) // count] for i in range(count)]


def build(plan, config_path, out, count=14):
    plan, out = Path(plan).resolve(), Path(out).resolve()
    config = load(config_path)
    if config != load(plan / 'config_snapshot.json'):
        raise ValueError('Plan/config mismatch')
    release = AI / 'Qwen_cpt_version/region_preprocessing_v5_official'
    current = load(ROOT.parent / 'CURRENT.json')
    if digest(release / 'RELEASE.json') != current['release_manifest_sha256']:
        raise ValueError('Unexpected release manifest')
    verify_release(release)
    jobs = rows(plan / 'jobs.jsonl')
    groups = partition(jobs, count)
    if out.exists():
        raise FileExistsError('Choose a fresh bundle output; previous inputs are immutable')
    out.mkdir(parents=True)
    staging = out / '_build_metadata'
    staging.mkdir()
    documents = {j['document_id']: j for j in jobs}
    for job in documents.values():
        if digest(job['source_path']) != job['source_sha256']:
            raise ValueError('Source PDF changed: ' + job['document_id'])
    metadata = {'schema': VERSION, 'jobs': jobs, 'config': config,
                'jobs_sha256': digest(plan / 'jobs.jsonl'), 'release_manifest_sha256': digest(release / 'RELEASE.json'),
                'bundle_count': count, 'documents': len(documents), 'pages': sum(j['source_pages'] for j in documents.values()),
                'human_verification_auto_created': False}
    atomic_json(staging / 'plan.json', metadata)
    runtime = {f'runtime/{p.name}': p for p in ROOT.glob('*.py') if not p.name.startswith('test_')}
    engine = {f'engine/{name}': release / name for name in [*load(release / 'RELEASE.json')['files'], 'RELEASE.json']}
    global_files = {**runtime, **engine, 'plan.json': staging / 'plan.json'}
    seen = set()
    outputs = []
    for i, group in enumerate(groups, 1):
        files = dict(global_files)
        seeds = []
        completed = []
        for job in group:
            did = job['document_id']
            if did in seen:
                continue
            seen.add(did)
            files[f'sources/{job["source_sha256"]}.pdf'] = Path(job['source_path'])
            if job['layout_required']:
                continue
            run = Path(job['run'])
            if load(run / 'manifest.json')['document']['sha256'] != job['source_sha256']:
                raise ValueError('Cached run/source mismatch')
            seed_names = ['manifest.json', 'records.jsonl', 'document_pages.jsonl', 'prepare_summary.json',
                          'classification.json', 'duplicate_candidates.json', 'benchmark_groups.json', 'benchmark_queue.jsonl']
            for name in seed_names:
                if (run / name).exists():
                    files[f'seeds/{did}/{name}'] = run / name
            for p in (run / 'assets').rglob('*'):
                if p.is_file():
                    files[f'seeds/{did}/{p.relative_to(run).as_posix()}'] = p
            seeds.append({'document_id': did, 'records_sha256': digest(run / 'records.jsonl'),
                          'manifest_sha256': digest(run / 'manifest.json'), 'reviews_included': False})
            # Preserve proven VLM successes without rerunning the seven pilot/batch images.
            caches = {}
            archives = list((run / 'external_raw').rglob('*.zip'))
            for archive in archives:
                with zipfile.ZipFile(archive) as z:
                    for name in z.namelist():
                        if 'vlm_results_' not in name or not name.endswith('.json'):
                            continue
                        for o in json.loads(z.read(name)).get('observations', []):
                            if o.get('status') == 'ok' and o.get('source_sha256') == job['source_sha256'] and o.get('cache_key'):
                                caches.setdefault(o['cache_key'], o)
            for key, observation in caches.items():
                cache_path = staging / ('vlm_' + key + '.json')
                atomic_json(cache_path, observation)
                files[f'vlm_seed_cache/{key}.json'] = cache_path
            # Completed shard receipts are source/packet/archive-bound, not guesses from page coverage.
            events = Path(config['work_root']) / 'events.jsonl'
            for event in rows(events) if events.exists() else []:
                if event.get('action') != 'merge' or event.get('phase') != 'inference':
                    continue
                matching = next((j for j in jobs if j['job_id'] == event['job_id'] and j['document_id'] == did), None)
                if not matching:
                    continue
                arc = next((p for p in archives if digest(p) == event['archive_sha256']), None)
                if arc is None:
                    continue
                receipt = next((load(p) for p in (run / 'import_receipts').glob('*.json')
                                if load(p).get('archive_sha256') == event['archive_sha256']), None)
                if receipt:
                    completed.append({'job_id': matching['job_id'], 'source_sha256': matching['source_sha256'],
                                      'archive_sha256': event['archive_sha256'], 'receipt': receipt})
                    files[f'completed_evidence/{matching["job_id"]}/results.zip'] = arc
        path = out / f'v5_upload_{i:02d}_of_{count:02d}.zip'
        m = write_archive(path, files, {'schema': VERSION, 'bundle_id': f'upload_{i:02d}', 'bundle_index': i,
                                      'bundle_count': count, 'jobs': [j['job_id'] for j in group],
                                      'plan_sha256': digest(staging / 'plan.json'), 'seeds': seeds,
                                      'completed_jobs': completed, 'semantic_verified': False}, 'bundle.json')
        info = {'bundle_id': m['bundle_id'], 'path': str(path), 'sha256': digest(path), 'bytes': path.stat().st_size,
                'job_count': len(group), 'pages': sum(j['last_page'] - j['first_page'] + 1 for j in group),
                'source_documents_added': len(seeds) + sum(n.startswith('sources/') for n in files) - len(seeds)}
        outputs.append(info)
        print(json.dumps(info, ensure_ascii=False), flush=True)
    summary = {'schema': VERSION, 'bundle_count': count, 'source_jobs': len(jobs), 'documents': len(documents),
               'pages': metadata['pages'], 'total_bytes': sum(o['bytes'] for o in outputs), 'bundles': outputs,
               'plan_sha256': digest(staging / 'plan.json'), 'upload_all_before_run': True}
    atomic_json(out / 'UPLOAD_INDEX.json', summary)
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--count', type=int, default=14)
    a = p.parse_args()
    build(a.plan, a.config, a.out, a.count)
