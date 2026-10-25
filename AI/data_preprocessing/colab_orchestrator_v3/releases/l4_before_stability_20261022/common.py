"""Standard-library persistence shared by the Colab coordinator and local importer."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import stat
import time
import zipfile

VERSION = 'v5-orchestrator-3-drive'
INPUT_VERSION = 'v5-orchestrator-2-sequential'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.next')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    os.replace(temporary, path)


def rows(path):
    with Path(path).open(encoding='utf-8-sig') as f:
        return [json.loads(line) for line in f if line.strip()]


def safe(root, name):
    if not isinstance(name, str) or not name or '\\' in name:
        raise ValueError('Invalid archive path: ' + repr(name))
    p = PurePosixPath(name)
    if p.is_absolute() or PureWindowsPath(name).drive or '..' in p.parts:
        raise ValueError('Path traversal: ' + name)
    target = (Path(root) / name).resolve()
    if not target.is_relative_to(Path(root).resolve()):
        raise ValueError('Path escapes destination')
    return target


def checked_extract(archive, destination, manifest_name, *, maximum_bytes=32 * 1024**3):
    """Verify every member before extraction; a failed file never replaces a good one."""
    destination = Path(destination)
    with zipfile.ZipFile(archive) as z:
        names = [i.filename for i in z.infolist()]
        if len(set(names)) != len(names):
            raise ValueError('Duplicate ZIP member')
        for info in z.infolist():
            safe(destination, info.filename)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('ZIP symlinks are not accepted')
        if sum(i.file_size for i in z.infolist()) > maximum_bytes:
            raise ValueError('Uncompressed archive exceeds configured limit')
        m = json.loads(z.read(manifest_name))
        expected = m['files']
        if set(names) != set(expected) | {manifest_name}:
            raise ValueError('Archive inventory mismatch')
        for name, wanted in expected.items():
            h = hashlib.sha256()
            with z.open(name) as source:
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    h.update(block)
            if h.hexdigest() != wanted:
                raise ValueError('Archive content hash mismatch: ' + name)
        for name in expected:
            target = safe(destination, name)
            if target.exists() and digest(target) == expected[name]:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(target.name + '.extracting')
            with z.open(name) as source, temp.open('wb') as sink:
                shutil.copyfileobj(source, sink, 1024 * 1024)
            os.replace(temp, target)
        # Content-addressed returns keep one physical object for each byte hash.
        logical = m.get('logical_files')
        if logical is not None:
            if set(expected) != {'objects/' + h for h in logical.values()}:
                raise ValueError('Compact archive object inventory mismatch')
            expanded=sum(z.getinfo('objects/'+h).file_size for h in logical.values())
            if expanded > maximum_bytes:raise ValueError('Logical expansion exceeds configured limit')
            for name, sha in logical.items():
                if name.startswith('objects/') or name == manifest_name:
                    raise ValueError('Reserved logical path')
                target = safe(destination, name)
                source = safe(destination, 'objects/' + sha)
                if expected['objects/'+sha] != sha:
                    raise ValueError('Object path/hash mismatch')
                if target.exists() and digest(target) == sha: continue
                target.parent.mkdir(parents=True, exist_ok=True)
                temp = target.with_name(target.name + '.extracting')
                shutil.copyfile(source, temp)
                os.replace(temp, target)
    return m


def copy_verified(source, target, *, replace=False, quiet=False):
    """Bounded-memory copy, progress, destination SHA check, then final rename."""
    from telemetry import event, span
    source, target = Path(source), Path(target)
    with span('transfer_hash_source',source=str(source)):wanted = digest(source)
    if target.exists():
        if digest(target) == wanted: return {'path': str(target), 'sha256': wanted, 'bytes': target.stat().st_size}
        if not replace: raise ValueError('Existing destination has different bytes: '+str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name+'.partial')
    total = source.stat().st_size; copied = 0; last = time.monotonic(); mark = 0
    with span('transfer', source=str(source), target=str(target), bytes=total):
        with source.open('rb') as src, partial.open('wb') as dst:
            while block := src.read(4*1024*1024):
                dst.write(block); copied += len(block)
                if time.monotonic()-last >= 5 or copied-mark >= 64*1024*1024:
                    row = event('transfer_progress', target=str(target), bytes_copied=copied, bytes_total=total,
                                percent=100*copied/total if total else 100)
                    if not quiet: print('TRANSFER', json.dumps(row), flush=True)
                    last=time.monotonic(); mark=copied
            dst.flush()
            # Mounted Drive may not implement fsync; destination hash is required.
            try: os.fsync(dst.fileno())
            except OSError: pass
        with span('transfer_hash_destination',target=str(partial)):
            actual=digest(partial)
        if actual != wanted: raise ValueError('Destination copy hash mismatch; partial retained')
        os.replace(partial, target)
    row=event('transfer_complete', target=str(target), bytes=total, sha256=wanted, percent=100)
    if not quiet: print('TRANSFER_COMPLETE', json.dumps(row), flush=True)
    return {'path': str(target), 'sha256': wanted, 'bytes': total}


def write_compact_archive(target, files, metadata):
    """Keep all logical audit files but store identical bytes only once."""
    objects, logical = {}, {}
    for name, path in sorted(files.items()):
        safe(Path(target).parent, name)
        sha = digest(path); logical[name] = sha; objects.setdefault('objects/'+sha, path)
    original = sum(Path(p).stat().st_size for p in files.values())
    unique = sum(Path(p).stat().st_size for p in objects.values())
    return write_archive(target, objects, {**metadata, 'logical_files': logical,
        'storage': 'sha256-objects-v1', 'logical_bytes': original, 'unique_bytes': unique,
        'duplicate_bytes_avoided': original-unique}, 'return.json')


def write_archive(target, files, metadata, manifest_name):
    """Publish a content-hashed ZIP atomically; do not overwrite a previous archive."""
    from telemetry import event,span
    target = Path(target)
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with span('archive_hash',target=str(target),files=len(files)):
        expected = {name: digest(path) for name, path in sorted(files.items())}
    payload = {**metadata, 'files': expected}
    temporary = target.with_name(target.name + '.next')
    with span('archive_write',target=str(target),files=len(files)):
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=3, allowZip64=True) as z:
            total=sum(Path(p).stat().st_size for p in files.values());done=0;last=time.monotonic()
            for index,(name, path) in enumerate(sorted(files.items()),1):
                safe(target.parent, name)
                # PNG/JPEG/PDF/ZIP payloads are already compressed; avoid spending
                # CPU recompressing nested audit ZIPs and source slide images.
                stored=Path(path).suffix.lower() in {'.zip','.png','.jpg','.jpeg','.pdf','.gz'}
                z.write(path, name,compress_type=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED)
                done+=Path(path).stat().st_size
                if time.monotonic()-last>=5:
                    event('archive_progress',target=str(target),files_done=index,files_total=len(files),input_bytes_done=done,
                          input_bytes_total=total,zip_bytes_so_far=z.fp.tell());last=time.monotonic()
            z.writestr(manifest_name, json.dumps(payload, ensure_ascii=False, indent=2))
    os.replace(temporary, target)
    return payload


def verify_release(root):
    root = Path(root)
    release = load(root / 'RELEASE.json')
    for name, wanted in release['files'].items():
        if digest(safe(root, name)) != wanted:
            raise ValueError('Frozen v5 release changed: ' + name)
    return release


def checkpoint(run, remote):
    """Append a delta checkpoint; large immutable images are copied only once."""
    run, remote = Path(run), Path(remote)
    remote.mkdir(parents=True, exist_ok=True)
    index_path = remote / 'index.json'
    index = load(index_path) if index_path.exists() else {'files': {}, 'archives': []}
    current = {}
    changed = {}
    for path in sorted(run.rglob('*')):
        if not path.is_file() or path.suffix in {'.next', '.sqlite3'} or path.name.endswith(('-wal', '-shm')):
            continue
        name = path.relative_to(run).as_posix()
        info = path.stat()
        old = index['files'].get(name)
        # Assets are immutable in v5; changed metadata always gets rehashed.
        same_asset = name.startswith('assets/') and old and old.get('size') == info.st_size and old.get('mtime_ns') == info.st_mtime_ns
        sha = old['sha256'] if same_asset else digest(path)
        current[name] = {'sha256': sha, 'size': info.st_size, 'mtime_ns': info.st_mtime_ns}
        if not old or old['sha256'] != sha:
            changed[name] = path
    if changed:
        name = f'delta_{len(index["archives"]):05d}_{time.time_ns()}.zip'
        local = run.parent / '_checkpoint_archives' / run.name / name
        write_archive(local, changed, {'schema': VERSION, 'run': run.name}, 'checkpoint.json')
        receipt = copy_verified(local, remote/name)
        index['archives'].append({'name': name, 'sha256': receipt['sha256']})
        index['files'] = current
        atomic_json(index_path, index)
        local.unlink()  # Durable, hash-verified copy has been published.
    return index


def restore_checkpoint(remote, run):
    remote, run = Path(remote), Path(run)
    index = load(remote / 'index.json')
    for archive in index['archives']:
        path = safe(remote, archive['name'])
        if archive.get('origin'):
            path=Path(archive['origin']).resolve()
            if not index.get('legacy_root') or not path.is_relative_to(Path(index['legacy_root']).resolve()):
                raise ValueError('Legacy checkpoint outside read-only migration root')
        local = run.parent/'_checkpoint_restore'/archive['sha256']
        copy_verified(path, local)
        if digest(local) != archive['sha256']:
            raise ValueError('Checkpoint archive changed')
        checked_extract(local, run, 'checkpoint.json')
        local.unlink()
    for name, info in index['files'].items():
        if digest(safe(run, name)) != info['sha256']:
            raise ValueError('Checkpoint restore mismatch: ' + name)
    return index
