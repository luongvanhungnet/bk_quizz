"""Revalidate old raw responses without inference or modification of source files."""
import copy
import hashlib
import json
from pathlib import Path
import zipfile
from validation import parse_json_output, validate_prediction, semantic_warnings

ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'region_preprocessing'


def sha(data):return hashlib.sha256(data).hexdigest()


def migrate_vlm(record):
    result={'id':record['id'],'source_status':record['status'],
            'source_cache_key':record['cache_key'],'semantic_verified':False,
            'destination':'review_queue','repairs':[]}
    try:
        obj,recovered=parse_json_output(record['raw_content'])
    except (ValueError,KeyError) as exc:
        return {**result,'schema_status':'invalid_json','errors':[str(exc)]}
    if recovered:result['repairs'].append('removed_markdown_wrapper')
    obj=copy.deepcopy(obj)
    old_type=obj.get('image_type')
    if old_type in ['diagram|graph','diagram|graph|chart|illustration|unknown']:
        # Legacy output does not tell us which enum was intended. Do not guess.
        obj['image_type']='unknown'
        result['repairs'].append({'field':'image_type','before':old_type,'after':'unknown',
                                  'reason':'ambiguous_legacy_enum_no_semantic_inference'})
    errors=validate_prediction('vlm',obj)
    return {**result,'prediction':obj,'errors':errors,
            'schema_status':'invalid_structure' if errors else 'ok',
            'semantic_warnings':semantic_warnings(obj)}


def run():
    archive=OLD/'model/region_results_33f6b7b75d29.zip'
    raw=archive.read_bytes()
    out=ROOT/'revalidation';out.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as z:old=json.loads(z.read('results.json'))
    manifest_path=OLD/'runs/it3170_scored_v3/manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    assert old['manifest_sha256']==sha(manifest_path.read_bytes())
    requests={r['id']:r for r in manifest['requests']}
    assert len({r['id'] for r in old['records']})==len(old['records'])==len(requests)
    for r in old['records']:
        q=requests[r['id']]
        assert r['cache_key']==q['cache_key'] and r['raw_pixel_sha256']==q['raw_pixel_sha256']
    rows=[migrate_vlm(r) for r in old['records'] if r['engine']=='vlm']
    for row in rows:
        q=requests[row['id']]
        row['source']={k:q[k] for k in ['page','document_sha256','render_sha256','input_file_sha256']}
    from collections import Counter
    report={'source_archive_sha256':sha(raw),'source_manifest_sha256':old['manifest_sha256'],
            'inference_calls':0,'vlm_total':len(rows),'previous_parsed':55,
            'before_schema_ok':0,'after_schema_statuses':dict(Counter(r['schema_status'] for r in rows)),
            'new_semantically_verified':0,'new_CPT_samples':0,
            'formula_old_validator_ok':421,
            'formula_new_validator_ok':sum(not validate_prediction('formula',r.get('prediction')) for r in old['records'] if r['engine']=='formula'),
            'table_failures':[{**{k:r.get(k) for k in ['id','error_type','error_message']},
                              'historical_traceback_available':False} for r in old['records'] if r['engine']=='table']}
    (out/'vlm_schema_review.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    (out/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    assert archive.read_bytes()==raw
    print(json.dumps(report,ensure_ascii=True,indent=2))


if __name__=='__main__':run()
