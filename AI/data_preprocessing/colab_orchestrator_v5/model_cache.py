"""Copy a complete verified cache archive once; models load from local disk."""
import json
from pathlib import Path
import time
import zipfile

from common import atomic_json,checked_extract,copy_verified,digest,load


def restore(base,root,family='docling_hf'):
    base,root=Path(base),Path(root)
    if family not in {'docling_hf','hf_cache','paddle_cache'}:raise ValueError('Invalid model cache family')
    receipt=base/'model_cache'/family/'latest.json';local=root/family
    local.mkdir(parents=True,exist_ok=True)
    if not receipt.exists():return {'restored':False,'reason':'No sealed cache; download into local cache during smoke/model initialization'}
    m=load(receipt);marker=local/'_RESTORED.json'
    if marker.exists() and load(marker).get('archive_sha256')==m['archive_sha256']:
        return {'restored':True,'already_local':True}
    archive=root/(family+'_restore.zip')
    copy_verified(m['archive'],archive,expected_sha256=m['archive_sha256'])
    checked_extract(archive,local,'model_cache.json',maximum_bytes=64*1024**3)
    atomic_json(marker,m);archive.unlink();return {'restored':True,'already_local':False}


def seal(base,root,family='docling_hf'):
    base,root=Path(base),Path(root);source=root/family
    if family not in {'docling_hf','hf_cache','paddle_cache'}:raise ValueError('Invalid model cache family')
    files={p.relative_to(source).as_posix():p for p in source.rglob('*') if p.is_file()
           and not any(x in {'.locks','__pycache__'} for x in p.relative_to(source).parts)
           and not p.name.endswith(('.incomplete','.lock')) and p.name not in {'_RESTORED.json','model_cache.json'}}
    if not files:return {'saved':False,'reason':'Cache empty'}
    if family=='docling_hf':
        from runtime_profile import audit_docling_cache
        audit=audit_docling_cache(source)
        if audit['invalid_files'] or not audit['files']:raise ValueError('Do not persist an invalid/uninspected Docling model cache')
    hashes={n:digest(p) for n,p in files.items()}
    previous=base/'model_cache'/family/'latest.json'
    if previous.exists() and load(previous).get('files')==hashes:return {'saved':True,'unchanged':True}
    archive=root/(family+'_cache.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_STORED,allowZip64=True) as z:
        for name,p in files.items():z.write(p,name)
        z.writestr('model_cache.json',json.dumps({'family':family,'files':hashes,'format':'v6-local-model-cache'}))
    target=base/'model_cache'/family/(str(time.time_ns())+'.zip');receipt=copy_verified(archive,target)
    atomic_json(previous,{'archive':receipt['path'],'archive_sha256':receipt['sha256'],'files':hashes})
    archive.unlink();return {'saved':True,'archive':receipt['path']}
