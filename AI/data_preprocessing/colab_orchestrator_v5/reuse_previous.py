"""Read-only adoption of complete v4 unit ZIPs; preserve their old quality/version."""
from pathlib import Path
import time

from common import atomic_json,copy_verified,digest,load
from unit_store import inspect_result


def adopt(store,previous_base,work):
    previous=Path(previous_base)
    if not previous.exists():return
    if previous.resolve()==store.base.resolve():raise ValueError('Previous BASE must be separate')
    issues=[]
    for uid,entry in store.entries.items():
        if uid in store.completed:continue
        candidates=sorted((previous/'results'/uid).glob('*.zip'),reverse=True)
        receipt=previous/'receipts'/(uid+'.json')
        if receipt.exists():
            try:
                r=load(receipt);path=Path(r['archive']).resolve()
                if not path.is_relative_to((previous/'results'/uid).resolve()):raise ValueError('Old receipt outside its result directory')
                if digest(path)!=r['archive_sha256']:raise ValueError('Old result hash mismatch')
                candidates=[path]+[p for p in candidates if p.resolve()!=path]
            except Exception as exc:issues.append({'unit_id':uid,'error':repr(exc)})
        for source in candidates:
            local=Path(work)/'previous_results'/source.name
            try:
                print('VERIFY PREVIOUS RESULT',uid,flush=True)
                receipt=copy_verified(source,local,quiet=True)
                m=inspect_result(local,entry,store.index['plan_sha256'])
                result=store.publish(local,entry)
                atomic_json(store.base/'previous_provenance'/(uid+'.json'),
                    {'source_archive':str(source),'source_sha256':receipt['sha256'],'adopted_archive':result['archive'],
                     'source_preprocessing_version':m.get('preprocessing_version','legacy_v5'),
                     'new_policy_rerun':False,'quality_certified':False,'semantic_verified':False,'unix':time.time()})
                local.unlink();break
            except Exception as exc:issues.append({'unit_id':uid,'archive':str(source),'error':repr(exc)})
    atomic_json(store.base/'previous_adoption_issues.json',issues)
