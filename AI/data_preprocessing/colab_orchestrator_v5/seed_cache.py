"""Reuse unchanged successful VLM observations carried by machine seed records.

Only an exact match to the frozen worker's full request/config cache key is used.
No text is rewritten and no semantic/human verification is inferred.
"""
from pathlib import Path
from common import atomic_json,load,rows


def seed_vlm_cache(run,packet,cache):
    from io_utils import canonical,sha
    from vlm_worker import PROMPT
    run,packet,cache=Path(run),Path(packet),Path(cache)
    m=load(packet/'manifest.json');records={r['id']:r for r in rows(run/'records.jsonl')};count=0
    for q in m['requests']:
        if not q.get('use_vlm'):continue
        text=PROMPT+('\nNgữ cảnh nguồn tham khảo (có thể chưa đầy đủ): '+q['context_text'][:240] if q.get('context_text') else '')
        key=sha(canonical({'image':q['vlm_image_sha256'],'target_crop':q['crop_sha256'],'target_bbox':q['bbox'],
                           'kind':q['kind'],'prompt':text,'config':m['vlm_config'],'source':q['source_sha256']}))
        target=cache/(key+'.json')
        if target.exists():continue
        record=records[q['id']]
        for c in record['candidates']:
            ev=c.get('evidence') or {}
            if (c['engine']=='vlm' and c['status']=='ok' and c.get('text','').strip() and ev.get('cache_key')==key
                and ev.get('source_sha256')==q['source_sha256'] and ev.get('crop_sha256')==q['crop_sha256']
                and ev.get('input_image_sha256')==q['vlm_image_sha256']):
                atomic_json(target,{'id':q['id'],'page':q['page'],'engine':'vlm','cache_key':key,'status':'ok','text':c['text'],
                    'source_sha256':q['source_sha256'],'crop_sha256':q['crop_sha256'],'input_image_sha256':q['vlm_image_sha256'],
                    'model_config':m['vlm_config'],'context_supplied':q.get('context_text','')[:240],
                    'packet_manifest_sha256':None,'source_machine_revision':record.get('machine_revision'),
                    'source_candidate_sha256':sha(canonical(c)),'cache_migrated_from_machine_candidate':True,
                    'partial_observation':ev.get('partial_observation',False),'semantic_verified':False})
                count+=1;break
    return count
