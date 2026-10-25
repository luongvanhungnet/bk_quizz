"""Standard-library persistence shared by the Colab coordinator and local importer."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import stat
import time
import zipfile

VERSION = 'v5-orchestrator-1'


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
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').splitlines() if line.strip()]


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
    return m


def write_archive(target, files, metadata, manifest_name):
    """Publish a content-hashed ZIP atomically; do not overwrite a previous archive."""
    target = Path(target)
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = {name: digest(path) for name, path in sorted(files.items())}
    payload = {**metadata, 'files': expected}
    temporary = target.with_name(target.name + '.next')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=3, allowZip64=True) as z:
        for name, path in sorted(files.items()):
            safe(target.parent, name)
            z.write(path, name)
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
        write_archive(remote / name, changed, {'schema': VERSION, 'run': run.name}, 'checkpoint.json')
        index['archives'].append({'name': name, 'sha256': digest(remote / name)})
        index['files'] = current
        atomic_json(index_path, index)
    return index


def restore_checkpoint(remote, run):
    remote, run = Path(remote), Path(run)
    index = load(remote / 'index.json')
    for archive in index['archives']:
        path = safe(remote, archive['name'])
        if digest(path) != archive['sha256']:
            raise ValueError('Checkpoint archive changed')
        checked_extract(path, run, 'checkpoint.json')
    for name, info in index['files'].items():
        if digest(safe(run, name)) != info['sha256']:
            raise ValueError('Checkpoint restore mismatch: ' + name)
    return index
