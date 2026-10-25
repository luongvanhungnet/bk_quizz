"""Local-only preparation of verified unit ZIPs for the frozen review application."""
from pathlib import Path, PurePosixPath, PureWindowsPath
import argparse
from collections import Counter
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import time
import zipfile

_COPY_FILE = shutil.copyfile


def link_copy(source, target, *, follow_symlinks=True):
    source, target = Path(source), Path(target)
    if target.exists():
        raise FileExistsError(target)
    try:
        os.link(source, target, follow_symlinks=follow_symlinks)
    except FileExistsError:
        raise
    except OSError:
        _COPY_FILE(source, target, follow_symlinks=follow_symlinks)
    return str(target)


def download_member(name):
    match = re.fullmatch(r'results/(unit_(\d{4}))/[^/\\:]+\.zip', name)
    if not match or not 1 <= int(match[2]) <= 134:
        raise ValueError('Unexpected Drive ZIP member: ' + name)
    return match[1]


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024**2),b''):h.update(block)
    return h.hexdigest()


def cached_cross_validation(validate):
    """Memoize exact immutable input/output contents for the current source only."""
    cache={};source=None
    def key(record):
        return hashlib.sha256(json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()
    def cached(record):
        nonlocal source
        if record.get('source_sha256')!=source:
            cache.clear();source=record.get('source_sha256')
        before=key(record)
        if before not in cache:
            result=validate(record);cache[before]=result;cache[key(result)]=result
        return cache[before]
    return cached


def publish_preserved(run,records,receipt):
    """Publish original machine outputs without rerunning preprocessing policies.

    The importer already validates every archive/source/asset and record schema.
    This local organisation step must retain proposal text, flags and revisions.
    """
    core=Path(__file__).resolve().parent.parent.parent/'Qwen_cpt_version/region_preprocessing_v5_official'
    if str(core) not in sys.path:sys.path.insert(0,str(core))
    from models import validate_record
    from io_utils import canonical,sha,write_once
    run=Path(run)
    for record in records:
        validate_record(record)
        if record.get('human_verified') or record.get('semantic_verified'):raise ValueError('Machine import cannot create human verification')
        if not record.get('machine_revision'):raise ValueError('Missing original machine revision')
    key=sha(canonical(receipt))[:16]
    snapshot=run/'machine_snapshots'/('revision_'+key+'.jsonl');snapshot.parent.mkdir(parents=True,exist_ok=True)
    data=''.join(canonical(r)+'\n' for r in records).encode('utf-8');wanted=hashlib.sha256(data).hexdigest()
    if snapshot.exists():
        if digest(snapshot)!=wanted:raise ValueError('Import snapshot conflict')
    else:
        temp=snapshot.with_suffix('.next');temp.write_bytes(data);os.replace(temp,snapshot)
    temporary=run/('records_'+key+'.next')
    if temporary.exists():
        if digest(temporary)!=wanted:temporary.write_bytes(data)
    else:link_copy(snapshot,temporary)
    os.replace(temporary,run/'records.jsonl')
    write_once(run/'import_receipts'/(key+'.json'),receipt)
    summary={'records':len(records),'buckets':dict(Counter(r['machine_bucket'] for r in records)),
        'snapshot':snapshot.relative_to(run).as_posix(),'human_decisions_auto_created':0}
    write_json(run/'machine_summary.json',summary)
    return summary


def write_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.next')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(temp,path)


def safe(root,name):
    p=PurePosixPath(name)
    if not name or '\\' in name or p.is_absolute() or '..' in p.parts or PureWindowsPath(name).drive:
        raise ValueError('Unsafe logical path: '+name)
    dest=(Path(root)/name).resolve()
    if not dest.is_relative_to(Path(root).resolve()):raise ValueError('Path escapes root')
    return dest


def materialize_review(archive,destination,manifest_name,**kwargs):
    """Expand run metadata/assets after the official importer verifies ALL objects.

    Full logs, packets and caches stay in the preserved raw ZIP. Mutable run JSON
    is always independent; immutable image aliases share verified object storage.
    """
    destination=Path(destination)
    with zipfile.ZipFile(archive) as z:
        m=json.loads(z.read(manifest_name));logical=m['logical_files']
        selected=set()
        for doc in m['runs']:
            prefix='runs/'+doc+'/'
            selected.update(n for n in logical if n.startswith(prefix) and '/' not in n[len(prefix):] and n.endswith(('.json','.jsonl')))
            records=[json.loads(l) for l in z.read('objects/'+logical[prefix+'records.jsonl']).decode('utf-8-sig').split('\n') if l.strip()]
            for r in records:
                for field in ['render','crop','context']:
                    selected.add(prefix+r[field+'_path'])
        for name in sorted(selected):
            target=safe(destination,name);sha=logical[name];obj=safe(destination,'objects/'+sha)
            if not obj.exists():
                data=z.read('objects/'+sha)
                if hashlib.sha256(data).hexdigest()!=sha:raise ValueError('Changed review object: '+name)
                obj.parent.mkdir(parents=True,exist_ok=True);temp=obj.with_name(obj.name+'.extracting')
                temp.write_bytes(data);os.replace(temp,obj)
            elif digest(obj)!=sha:raise ValueError('Existing review object changed: '+str(obj))
            if target.exists():
                if digest(target)!=sha:raise ValueError('Existing review file changed: '+name)
                continue
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.suffix.lower() in {'.png','.jpg','.jpeg','.webp','.gif','.pdf'}:link_copy(obj,target)
            else:_COPY_FILE(obj,target)
        write_json(destination/'REVIEW_MATERIALIZATION.json',{'raw_archive':str(archive),
            'expanded_logical_files':len(selected),'all_raw_files_retained_in_zip':True,
            'full_object_validation':'performed_by_official_inspect_result_before_this_adapter',
            'machine_records_changed':False})
    return m


def extract_downloads(downloads,output):
    archives=sorted(Path(downloads).glob('results-*.zip'))
    if not archives:raise FileNotFoundError('No Drive result ZIPs')
    entries=[];seen=set()
    for archive in archives:
        with zipfile.ZipFile(archive) as z:
            names=[i.filename for i in z.infolist() if not i.is_dir()]
            if len(names)!=len(set(names)):raise ValueError('Duplicate Drive ZIP member')
            for info in z.infolist():
                if info.is_dir():continue
                uid=download_member(info.filename)
                if uid in seen:raise ValueError('Multiple results for '+uid)
                if stat.S_ISLNK(info.external_attr>>16) or info.flag_bits&1:raise ValueError('Unsupported ZIP member')
                seen.add(uid);entries.append((archive,info.filename,info.file_size,uid))
    if seen!={f'unit_{i:04}' for i in range(1,135)}:raise ValueError('Missing/extra unit results')
    print(f'EXTRACT: {len(entries)} units from {len(archives)} Drive ZIPs',flush=True)
    state_path=output/'unit_returns/download_inventory.json'
    old=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {'units':[]}
    old_entries={e['unit_id']:e for e in old['units']};results=[]
    for number,(archive,name,size,uid) in enumerate(entries,1):
        target=safe(output/'unit_returns/downloaded',name)
        before=old_entries.get(uid)
        if target.exists() and before and before['member']==name and target.stat().st_size==size and digest(target)==before['sha256']:
            result=before
        else:
            if target.exists():raise FileExistsError('Untracked or changed existing ZIP: '+str(target))
            if shutil.disk_usage(output).free < size+2*1024**3:raise OSError('Insufficient free space')
            target.parent.mkdir(parents=True,exist_ok=True);temp=target.with_name(target.name+'.extracting');h=hashlib.sha256()
            with zipfile.ZipFile(archive) as z,z.open(name) as source,temp.open('wb') as sink:
                for block in iter(lambda:source.read(4*1024**2),b''):h.update(block);sink.write(block)
            os.replace(temp,target)
            with zipfile.ZipFile(target) as z:m=json.loads(z.read('return.json'))
            if m['unit_id']!=uid:raise ValueError('Folder/result identity mismatch')
            result={'unit_id':uid,'archive':str(target),'sha256':h.hexdigest(),'bytes':size,
                'outer_archive':str(archive),'member':name,'pages':m['pages'],
                'unique_bytes':m.get('unique_bytes'),'logical_bytes':m.get('logical_bytes'),
                'preprocessing_version':m.get('preprocessing_version'),'summary':m['summary']}
        results.append(result)
        write_json(state_path,{'source':str(downloads),'units':results,'complete':len(results)==134})
        print(f'EXTRACT {number}/134 {uid}: {size/1024**2:.1f} MiB; CRC/SHA recorded',flush=True)
    return results


def import_downloads(output,index):
    runtime=Path(__file__).resolve().parent.parent/'colab_orchestrator_v5'
    sys.path.insert(0,str(runtime))
    import import_units
    from common import verify_release
    verify_release(import_units.ENGINE)
    sys.path.insert(0,str(import_units.ENGINE))
    import workflow
    workflow.publish=publish_preserved
    # Preserve the frozen import gates and ReviewStore semantics. Only replace
    # duplicate physical copies and expansion of non-review model caches.
    import_units.checked_extract=materialize_review
    def immutable_copy(src,dst,*,follow_symlinks=True):
        if Path(src).suffix.lower() in {'.zip','.png','.jpg','.jpeg','.webp','.gif','.pdf'}:
            return link_copy(src,dst,follow_symlinks=follow_symlinks)
        return _COPY_FILE(src,dst,follow_symlinks=follow_symlinks)
    shutil.copyfile=immutable_copy
    inventory=json.loads((output/'unit_returns/download_inventory.json').read_text(encoding='utf-8'))
    if not inventory.get('complete'):raise ValueError('Drive extraction is incomplete')
    progress=output/'unit_returns/import_progress.json'
    previous=json.loads(progress.read_text(encoding='utf-8')) if progress.exists() else {'units':[]}
    previous_by_id={e['unit_id']:e for e in previous['units']}
    completed=[]
    for number,entry in enumerate(sorted(inventory['units'],key=lambda e:e['unit_id']),1):
        started=time.monotonic()
        print(f'IMPORT START {number}/134 {entry["unit_id"]}',flush=True)
        old=previous_by_id.get(entry['unit_id'])
        if old and old['archive_sha256']==entry['sha256']:
            with zipfile.ZipFile(entry['archive']) as z:header=json.loads(z.read('return.json'))
            for did in header['runs']:
                receipts=output/'runs'/did/'import_receipts'
                if not any(json.loads(p.read_text(encoding='utf-8')).get('archive_sha256')==entry['sha256'] for p in receipts.glob('*.json')):
                    raise ValueError('Checkpoint is missing its source-bound receipt')
            completed.append(old)
        else:
            result=import_units.import_units(index,[Path(entry['archive'])],output_dir=output)
            completed.append({'unit_id':entry['unit_id'],'archive_sha256':entry['sha256'],
                              'seconds':round(time.monotonic()-started,2),'result':result})
        write_json(progress,{'units':completed,'complete':len(completed)==134,'human_decisions_auto_created':0,'training_exported':False})
        print(f'IMPORT DONE {number}/134 {entry["unit_id"]}: {completed[-1]["seconds"]}s',flush=True)
    shutil.copyfile=_COPY_FILE


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--downloads',type=Path,default=Path(r'D:\Download'))
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parent.parent/'workspaces/unit100_v6_20261022')
    parser.add_argument('--extract',action='store_true');parser.add_argument('--import-results',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    if args.extract:extract_downloads(args.downloads,args.output)
    if args.import_results:import_downloads(args.output,Path(__file__).resolve().parent.parent/'uploads_134_unit100_20261022/UPLOAD_INDEX.json')


if __name__=='__main__':main()
