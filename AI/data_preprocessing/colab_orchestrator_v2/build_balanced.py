"""Balance transport bytes while making every input executable in sequence."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics
import zipfile
from common import VERSION, atomic_json, digest, load, rows, verify_release, write_archive

ROOT = Path(__file__).resolve().parent
AI = ROOT.parent.parent


def balance(units, count):
    """LPT by compressed bytes. The shared-source bin is always first."""
    bins = [{'units': [], 'weight': 0} for _ in range(count)]
    for unit in sorted(units, key=lambda u: (-u['weight'], u['id'])):
        b = min(bins, key=lambda b: (b['weight'], len(b['units'])))
        b['units'].append(unit); b['weight'] += unit['weight']
    shared = next(b for b in bins if any(u.get('shared_source') for u in b['units']))
    return [shared] + [b for b in bins if b is not shared]


def size_stats(sizes):
    return {'total_bytes': sum(sizes), 'mean_bytes': statistics.mean(sizes), 'min_bytes': min(sizes),
            'max_bytes': max(sizes), 'population_variance_bytes2': statistics.pvariance(sizes),
            'population_std_bytes': statistics.pstdev(sizes), 'coefficient_of_variation': statistics.pstdev(sizes) / statistics.mean(sizes)}


def build(plan, config_path, old_index, out, count=14):
    plan, out = Path(plan).resolve(), Path(out).resolve()
    cfg = load(config_path); jobs = rows(plan / 'jobs.jsonl')
    if cfg != load(plan / 'config_snapshot.json'):
        raise ValueError('Plan/config mismatch')
    release = AI / 'Qwen_cpt_version/region_preprocessing_v5_official'
    verify_release(release)
    if digest(release / 'RELEASE.json') != load(ROOT.parent / 'CURRENT.json')['release_manifest_sha256']:
        raise ValueError('Official release mismatch')
    if out.exists():
        raise FileExistsError('Inputs are immutable; use a fresh output directory')
    out.mkdir(parents=True); staging = out / '_build_metadata'; staging.mkdir()
    previous = load(old_index); weights = {}; old_manifests = []
    for row in previous['bundles']:
        if digest(row['path']) != row['sha256']:
            raise ValueError('Old transport archive changed')
        with zipfile.ZipFile(row['path']) as z:
            weights.update({i.filename: i.compress_size for i in z.infolist()})
            old_manifests.append(json.loads(z.read('bundle.json')))
    completed = {d['job_id']: d for m in old_manifests for d in m['completed_jobs']}
    by_doc = defaultdict(list)
    for job in jobs: by_doc[job['document_id']].append(job)
    units = []
    for did, doc_jobs in by_doc.items():
        j = doc_jobs[0]
        if digest(j['source_path']) != j['source_sha256']:
            raise ValueError('Source PDF changed')
        source_name = f'sources/{j["source_sha256"]}.pdf'
        source = {source_name: Path(j['source_path'])}
        if j['layout_required']:
            units.append({'id': did, 'jobs': [x['job_id'] for x in doc_jobs], 'files': source,
                          'weight': weights[source_name], 'seed_fragments': [], 'completed_jobs': []})
            continue
        units.append({'id': did + ':shared_pdf', 'jobs': [], 'files': source, 'shared_source': True,
                      'weight': weights[source_name], 'seed_fragments': [], 'completed_jobs': []})
        run = Path(j['run']); records = rows(run / 'records.jsonl'); pages = rows(run / 'document_pages.jsonl')
        all_job_assets = set()
        caches = {}
        archives = list((run / 'external_raw').rglob('*.zip'))
        for archive in archives:
            with zipfile.ZipFile(archive) as z:
                for name in z.namelist():
                    if 'vlm_results_' in name and name.endswith('.json'):
                        for o in json.loads(z.read(name)).get('observations', []):
                            if o.get('status') == 'ok' and o.get('source_sha256') == j['source_sha256'] and o.get('cache_key'):
                                caches.setdefault(o['cache_key'], o)
        for job in doc_jobs:
            selected = [r for r in records if job['first_page'] <= r['page'] <= job['last_page']]
            selected_pages = [p for p in pages if job['first_page'] <= p['page'] <= job['last_page']]
            frag = staging / job['job_id']; frag.mkdir()
            def put_jsonl(name, values):
                p = frag / name; p.write_text(''.join(json.dumps(v, ensure_ascii=False) + '\n' for v in values), encoding='utf-8'); return p
            record_path = put_jsonl('records.jsonl', selected)
            page_path = put_jsonl('document_pages.jsonl', selected_pages)
            prefix = f'seed_fragments/{did}/{job["job_id"]}'
            files = {f'{prefix}/records.jsonl': record_path, f'{prefix}/document_pages.jsonl': page_path}
            for name in ['manifest.json', 'prepare_summary.json', 'classification.json', 'duplicate_candidates.json', 'benchmark_groups.json', 'benchmark_queue.jsonl']:
                if (run / name).exists(): files[f'{prefix}/{name}'] = run / name
            asset_paths = {r[k] for r in selected for k in ['render_path', 'crop_path', 'context_path']}
            for name in asset_paths:
                files[f'seed_assets/{did}/{name}'] = run / name
                all_job_assets.add(name)
            for key, observation in caches.items():
                if job['first_page'] <= observation['page'] <= job['last_page']:
                    path = staging / ('vlm_' + key + '.json'); atomic_json(path, observation)
                    files[f'vlm_seed_cache/{key}.json'] = path
            done = []
            if job['job_id'] in completed:
                d = completed[job['job_id']]; arc = next(p for p in archives if digest(p) == d['archive_sha256'])
                files[f'completed_evidence/{job["job_id"]}/results.zip'] = arc; done.append(d)
            weight = sum(weights.get('seeds/'+did+'/'+name, (run/name).stat().st_size) for name in asset_paths)
            weight += record_path.stat().st_size * .15 + page_path.stat().st_size * .2
            units.append({'id': job['job_id'], 'jobs': [job['job_id']], 'files': files, 'weight': weight,
                          'seed_fragments': [{'document_id': did, 'job_id': job['job_id'], 'prefix': prefix,
                                              'source_sha256': job['source_sha256'], 'records_sha256': digest(record_path),
                                              'pages': list(range(job['first_page'], job['last_page']+1))}], 'completed_jobs': done})
        all_assets = {p.relative_to(run).as_posix() for p in (run / 'assets').rglob('*') if p.is_file()}
        if all_assets != all_job_assets:
            raise ValueError('An unassigned cached asset would be lost')
    bins = balance(units, count)
    metadata = {'schema': VERSION, 'jobs': jobs, 'config': cfg, 'jobs_sha256': digest(plan/'jobs.jsonl'),
                'release_manifest_sha256': digest(release/'RELEASE.json'), 'bundle_count': count,
                'documents': len(by_doc), 'pages': sum(v[0]['source_pages'] for v in by_doc.values()),
                'sequence_required': True, 'human_verification_auto_created': False}
    atomic_json(staging/'plan.json', metadata)
    common = {f'runtime/{p.name}': p for p in ROOT.glob('*.py') if not p.name.startswith('test_')}
    common.update({f'engine/{n}': release/n for n in [*load(release/'RELEASE.json')['files'], 'RELEASE.json']})
    common['plan.json'] = staging/'plan.json'
    written = set(); outputs = []; assignments = []
    for i, b in enumerate(bins, 1):
        files = dict(common); child_jobs = []; fragments = []; done = []
        for unit in b['units']:
            child_jobs += unit['jobs']; fragments += unit['seed_fragments']; done += unit['completed_jobs']
            for name, path in unit['files'].items():
                if name not in written: files[name] = path
        written.update(files)
        assert child_jobs, 'A transport bundle must have executable jobs'
        path = out/f'v5_sequential_{i:02d}_of_{count:02d}.zip'
        payload = {'schema': VERSION, 'bundle_id': f'upload_{i:02d}', 'bundle_index': i, 'bundle_count': count,
                   'jobs': child_jobs, 'plan_sha256': digest(staging/'plan.json'), 'seed_fragments': fragments,
                   'completed_jobs': done, 'sequence_required': True, 'requires_acknowledged_previous': i-1,
                   'semantic_verified': False}
        write_archive(path, files, payload, 'bundle.json')
        row = {'bundle_id': payload['bundle_id'], 'path': str(path), 'sha256': digest(path), 'bytes': path.stat().st_size,
               'job_count': len(child_jobs), 'pages': sum(j['last_page']-j['first_page']+1 for j in jobs if j['job_id'] in child_jobs)}
        outputs.append(row); assignments.append(child_jobs)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    assert sorted(j for group in assignments for j in group) == sorted(j['job_id'] for j in jobs)
    before = size_stats([b['bytes'] for b in previous['bundles']]); after = size_stats([b['bytes'] for b in outputs])
    result = {'schema': VERSION, 'bundle_count': count, 'source_jobs': len(jobs), 'documents': len(by_doc),
              'pages': metadata['pages'], 'plan_sha256': digest(staging/'plan.json'), 'bundles': outputs,
              'total_bytes': after['total_bytes'], 'upload_all_before_run': False, 'sequential_ack_required': True,
              'size_before': before, 'size_after': after,
              'variance_reduction_percent': 100*(1-after['population_variance_bytes2']/before['population_variance_bytes2'])}
    atomic_json(out/'UPLOAD_INDEX.json', result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for name in ['plan','config','old-index','out']: p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--count', type=int, default=14)
    a=p.parse_args(); build(a.plan,a.config,a.old_index,a.out,a.count)
