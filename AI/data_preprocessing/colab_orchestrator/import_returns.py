"""Validate and import multi-job Colab returns without modifying human decisions."""
import argparse
from pathlib import Path
import shutil
import sys
import time
from common import VERSION, atomic_json, checked_extract, digest, load, rows, safe, verify_release
from orchestrator import extract_packet

ROOT = Path(__file__).resolve().parent


def import_returns(plan, bundle_index, archives, *, check_only=False):
    plan = Path(plan).resolve()
    index = load(bundle_index)
    jobs = rows(plan / 'jobs.jsonl')
    by_id = {j['job_id']: j for j in jobs}
    documents = {j['document_id']: j for j in jobs}
    release = ROOT.parent.parent / 'Qwen_cpt_version/region_preprocessing_v5_official'
    verify_release(release)
    sys.path.insert(0, str(release))
    from models import validate_record
    from corpus import merge_job
    config = load(plan / 'config_snapshot.json')
    work = Path(config['work_root']) / 'orchestrator_returns'
    work.mkdir(parents=True, exist_ok=True)
    packets, manifests, offered_runs = [], [], {}
    for archive in archives:
        archive = Path(archive).resolve()
        dest = work / digest(archive)[:20]
        m = checked_extract(archive, dest, 'return.json')
        if m['schema'] != VERSION or m['plan_sha256'] != index['plan_sha256'] or m['original_jobs_sha256'] != digest(plan / 'jobs.jsonl'):
            raise ValueError('Returned corpus/plan identity mismatch')
        if any('human_reviews.sqlite' in name for name in m['files']):
            raise ValueError('A return must not carry human review databases')
        manifests.append((archive, dest, m))
        for did in m['runs']:
            if did not in documents:
                raise ValueError('Unknown returned document')
            source = dest / 'runs' / did
            metadata = load(source / 'manifest.json')
            job = documents[did]
            if metadata['document']['sha256'] != job['source_sha256'] or digest(job['source_path']) != job['source_sha256']:
                raise ValueError('Returned document/source mismatch')
            for r in rows(source / 'records.jsonl'):
                validate_record(r)
                if r['source_sha256'] != job['source_sha256'] or r.get('human_verified') or r.get('semantic_verified'):
                    raise ValueError('Untrusted record source or forged verification')
                for prefix in ['crop', 'context', 'render']:
                    if digest(safe(source, r[prefix + '_path'])) != r[prefix + '_sha256']:
                        raise ValueError('Returned record image mismatch')
            old = offered_runs.get(did)
            if old and digest(old / 'records.jsonl') != digest(source / 'records.jsonl'):
                raise ValueError('Multiple different final snapshots; import one export generation at a time')
            offered_runs[did] = source
        for item in m['phase_results']:
            if item['job_id'] not in by_id or item['phase'] not in {'discovery', 'inference'}:
                raise ValueError('Unknown returned job/phase')
            folder = dest / 'unpacked_packets' / (item['job_id'] + '_' + item['phase'])
            pm = extract_packet(safe(dest, item['packet']), folder)
            job = by_id[item['job_id']]
            if pm.get('corpus_job', {}).get('job_id') != job['job_id'] or pm['document']['sha256'] != job['source_sha256']:
                raise ValueError('Packet belongs to another source job')
            if sorted(pm['page_map'].values()) != list(range(job['first_page'], job['last_page'] + 1)):
                raise ValueError('Source page coverage mismatch')
            packets.append((job, item['phase'], folder, safe(dest, item['results'])))
    for job, phase, packet, result in packets:
        if not (Path(job['run']) / 'manifest.json').exists() and job['document_id'] not in offered_runs:
            raise ValueError('Missing final run snapshot; select all 14 returned archives')
    if check_only:
        return {'archives_validated': len(manifests), 'job_phases_validated': len(packets), 'final_runs_validated': len(offered_runs), 'mutated_runs': 0}
    for archive, dest, manifest in manifests:
        raw = work / 'raw_archives' / (digest(archive) + '.zip')
        raw.parent.mkdir(parents=True, exist_ok=True)
        if not raw.exists():
            shutil.copy2(archive, raw)
        if digest(raw) != digest(archive):
            raise ValueError('Preserved raw result archive mismatch')
    installed = set()
    for did, source in offered_runs.items():
        job = documents[did]
        target = Path(job['run'])
        if (target / 'manifest.json').exists():
            if load(target / 'manifest.json')['document']['sha256'] != job['source_sha256']:
                raise ValueError('Existing local run belongs to another source')
            continue
        if target.exists():
            raise ValueError('Incomplete local run retained; inspect before importing: ' + str(target))
        staging = target.with_name(target.name + '_importing_' + str(time.time_ns()))
        shutil.copytree(source, staging)
        metadata = load(staging / 'manifest.json')
        atomic_json(staging / 'cloud_import_source_manifest.json', metadata)
        metadata['document']['path'] = job['source_path']
        metadata['asset_root'] = str(target)
        atomic_json(staging / 'manifest.json', metadata)
        staging.rename(target)
        installed.add(did)
    merged, reused = 0, 0
    # Entire document discovery must finish before its inference is imported.
    packets.sort(key=lambda t: (t[1] == 'inference', t[0]['document_id'], t[0]['first_page']))
    for job, phase, packet, result in packets:
        run = Path(job['run'])
        already = {load(p).get('archive_sha256') for p in (run / 'import_receipts').glob('*.json')}
        if job['document_id'] in installed or digest(result) in already:
            reused += 1
            continue
        merge_job(config, job, packet, result)
        merged += 1
    summary = {'archives_imported': len(manifests), 'new_local_runs': len(installed), 'job_phases_merged': merged,
               'job_phases_already_in_snapshot': reused, 'human_decisions_auto_created': 0, 'training_exported': False}
    atomic_json(work / ('import_' + str(time.time_ns()) + '.json'), summary)
    print(summary)
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--bundle-index', type=Path, required=True)
    p.add_argument('--results', type=Path, nargs='+', required=True)
    p.add_argument('--check-only', action='store_true')
    a = p.parse_args()
    import_returns(a.plan, a.bundle_index, a.results, check_only=a.check_only)
