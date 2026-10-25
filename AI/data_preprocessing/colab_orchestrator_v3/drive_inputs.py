"""Read input headers from Drive; never send file contents through notebook UI."""
import json
from pathlib import Path
import zipfile

from common import INPUT_VERSION, digest


def discover(folder):
    folder=Path(folder)
    if not folder.is_dir(): raise FileNotFoundError('Input folder missing: '+str(folder))
    found={};plan=None;count=None
    for path in sorted(folder.rglob('*.zip')):
        try:
            with zipfile.ZipFile(path) as z:
                if 'bundle.json' not in z.namelist():continue
                m=json.loads(z.read('bundle.json'))
        except zipfile.BadZipFile as exc:raise ValueError('Invalid ZIP on Drive: '+str(path)) from exc
        if m.get('schema')!=INPUT_VERSION or not m.get('sequence_required'):
            continue
        index=m['bundle_index']
        if plan is None:plan=m['plan_sha256'];count=m['bundle_count']
        if m['plan_sha256']!=plan or m['bundle_count']!=count:raise ValueError('Mixed plans in Drive input folder')
        if index in found:
            raise ValueError(f'Duplicate input index {index}; keep one copy in INPUT_DIR')
        found[index]={'path':str(path),'manifest':m,'bytes':path.stat().st_size}
    if not found:raise ValueError('No v2 sequential bundles found in '+str(folder))
    if set(found)!=set(range(1,count+1)):raise ValueError('Missing input indices: '+str(sorted(set(range(1,count+1))-set(found))))
    return [found[i] for i in sorted(found)]
