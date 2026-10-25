"""Assemble only files to upload; no build staging, raw PDFs or duplicate folders."""
from pathlib import Path
import os
import shutil

from common import digest,load,atomic_json

ROOT=Path(__file__).resolve().parent


def link(source,target):
    source,target=Path(source),Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if digest(source)==digest(target):return
        target.unlink()  # Only explicitly generated delivery files are replaced.
    try:os.link(source,target)
    except OSError:shutil.copyfile(source,target)


def build():
    inputs=ROOT.parent/'uploads_134_unit100_20261022';out=ROOT/'drive_upload'
    index=load(inputs/'UPLOAD_INDEX.json');release=load(ROOT/'RUNTIME_RELEASE.json')
    for e in index['bundles']:link(inputs/e['filename'],out/'inputs_134'/e['filename'])
    link(inputs/'UPLOAD_INDEX.json',out/'inputs_134/UPLOAD_INDEX.json')
    pre=load(inputs/'precompleted_results/PRECOMPLETED_INDEX.json')
    for e in pre['units']:link(inputs/'precompleted_results'/e['filename'],out/'inputs_134/precompleted_results'/e['filename'])
    link(inputs/'precompleted_results/PRECOMPLETED_INDEX.json',out/'inputs_134/precompleted_results/PRECOMPLETED_INDEX.json')
    link(ROOT/release['runtime_zip'],out/release['runtime_zip'])
    atomic_json(ROOT/'DELIVERY.json',{'folder':str(out),'input_folder':str(out/'inputs_134'),
        'input_archives':len(index['bundles']),'precompleted_result_archives':len(pre['units']),
        'runtime_zip':release['runtime_zip'],'runtime_sha256':release['runtime_zip_sha256'],
        'upload_bytes':index['total_bytes']+sum(e['bytes'] for e in pre['units'])+(ROOT/release['runtime_zip']).stat().st_size})
    return out


if __name__=='__main__':print(build())
