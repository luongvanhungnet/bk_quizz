"""Local stages for the IT3170 CPU / Colab GPU pilot. Never changes old runs."""
import argparse
import collections
import hashlib
import json
import shutil
import sys
import time
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'data_preprocessing'
sys.path.insert(0,str(BASE/'src'))
from common import digest,dump_json,read_jsonl,write_jsonl
from build_dataset import build,shingles,simhash
from pack_qwen import pack_records
from datasketch import MinHash,MinHashLSH

TOKENIZER=ROOT.parent/'local_qwen3/models/merged_hf_fp16'
PILOT=[20,49,51,129,130,300,500,800,869,1000,1042,1060]


def dedup(rows):
    """Three independent checks; text-only collisions never delete visual slides."""
    exact={};text_groups=collections.defaultdict(list);edges={};bands=collections.defaultdict(list)
    lsh=MinHashLSH(threshold=.8,num_perm=128);features=[];hashes=[]
    for i,r in enumerate(rows):
        text=r['text'];r['exact_hash']=digest(text)
        text_groups[r['exact_hash']].append(r['page'])
        key=(r['exact_hash'],r['source']['render_sha256'])
        r['duplicate_of']=exact.get(key)
        exact.setdefault(key,r['id'])
        features.append(shingles(text) if text else set())
        h=simhash(text) if text else None;hashes.append(h)
        r['simhash64']=f'{h:016x}' if h is not None else None
        if len(text)<80:continue
        mh=MinHash(num_perm=128,seed=42)
        mh.update_batch([x.encode() for x in sorted(features[i])])
        candidates=set(lsh.query(mh))
        # If Hamming distance <=3, one of four 16-bit bands must match.
        for band in range(4):candidates.update(bands[(band,(h>>(16*band))&65535)])
        for j in sorted(candidates):
            jac=len(features[i]&features[j])/max(1,len(features[i]|features[j]))
            distance=(h^hashes[j]).bit_count()
            if jac>=.8 or distance<=3:
                edges[(j,i)]={'page_a':rows[j]['page'],'page_b':r['page'],
                              'jaccard':round(jac,6),'simhash_distance':distance,
                              'minhash_candidate':j in lsh.query(mh),'simhash_match':distance<=3,
                              'action':'retain_and_same_split'}
        lsh.insert(i,mh)
        for band in range(4):bands[(band,(h>>(16*band))&65535)].append(i)
    return {'algorithms':['SHA-256','MinHash-128-seed42','SimHash-64-four-band'],
            'exact_removal_rule':'identical clean text AND full-resolution page render SHA256',
            'text_duplicate_groups':[v for v in text_groups.values() if len(v)>1],
            'exact_duplicates':[{'page':r['page'],'duplicate_of':r['duplicate_of']} for r in rows if r['duplicate_of']],
            'near_pairs':list(edges.values()),'near_removal':False}


def export(rows,out,tokenizer_path,stage):
    from transformers import AutoTokenizer
    tok=AutoTokenizer.from_pretrained(str(tokenizer_path),local_files_only=True,trust_remote_code=False)
    if tok.eos_token_id is None:raise ValueError('Missing EOS')
    kept=[];seen=set()
    for r in rows:
        key=(digest(r['text']),r['source']['render_sha256'])
        if key not in seen:kept.append(r);seen.add(key)
    write_jsonl(out/'train.jsonl',({'text':r['text']} for r in kept))
    write_jsonl(out/'train.metadata.jsonl',kept)
    packed=list(pack_records(kept,lambda s:tok.encode(s,add_special_tokens=False),tok.eos_token_id,1024))
    write_jsonl(out/'train.packed.jsonl',({k:v for k,v in p.items() if k!='source_spans'} for p in packed))
    write_jsonl(out/'train.packed.sources.jsonl',({'index':i,'source_spans':p['source_spans']} for i,p in enumerate(packed)))
    actual=[x for p in packed for x in p['input_ids']]
    expected=[x for r in kept for x in tok.encode(r['text'],add_special_tokens=False)+[tok.eos_token_id]]
    assert actual==expected
    assert all(p['labels']==p['input_ids'] and len(p['input_ids'])<=1024 for p in packed)
    dump_json(out/'manifest.json',{'stage':stage,'training_ready':stage=='reviewed_cloud_return',
              'samples':len(kept),'sequences':len(packed),'tokens_including_eos':len(actual),
              'tokenizer_path':str(tokenizer_path.resolve()),
              'tokenizer_files_sha256':{p.name:digest(p.read_bytes()) for p in tokenizer_path.glob('*token*') if p.is_file()},
              'eos_token_id':tok.eos_token_id,'sequence_length':1024,'cross_sample_attention':True,
              'split_policy':'one_document_train_only_no_independent_test',
              'validation':{'all_tokens_preserved':True,'causal_labels_equal_input_ids':True},
              'notes':'Native preview is not a completed OCR/vision dataset. Pad labels with -100 in trainer.'})
    return load(out/'manifest.json')


def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def bundle(run,pages):
    native=run/'native';document=load(native/'document.json')
    records={p['page']:p for p in read_jsonl(native/'native_pages.jsonl')}
    requests=[]
    for number in pages:
        p=records[number];image=native/p['render_path']
        assert digest(image.read_bytes())==p['render_sha256']
        requests.append({'page':number,'document_sha256':document['sha256'],
                         'render_sha256':p['render_sha256'],'image':f'images/page_{number:04d}.png',
                         'native_text':'\n'.join(b['text'] for b in p['blocks']),
                         'page_size_pt':p['page_size_pt'],'render_width':p['render_width'],
                         'code_boxes_pt':[b['bbox'] for b in p['blocks'] if b['type']=='code']})
    manifest={'schema_version':'it3170_hybrid_v1','document_sha256':document['sha256'],
              'source_pages':document['pages'],'pilot_pages':pages,'requests':requests,
              'worker_sha256':digest((ROOT/'colab_worker.py').read_bytes()),
              'vlm_prompt_sha256':digest((ROOT/'vlm_prompt.txt').read_bytes()),
              'notice':'Full page source images may contain original contact details; audit material, not public training text.'}
    dump_json(run/'request_manifest.json',manifest)
    target=run/'colab_input.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(run/'request_manifest.json','manifest.json')
        for r in requests:z.write(native/'assets'/f'page_{r["page"]:04d}.png',r['image'])
        for name in ['colab_worker.py','vlm_prompt.txt']:
            z.write(ROOT/name,name)
    return target


def prepare(a):
    start=time.perf_counter();run=a.run.resolve();native=run/'native'
    if (run/'local_result.json').exists():raise ValueError('Completed run exists; use a new --run')
    if not (native/'native_pages.jsonl').exists():
        from extract import extract
        extract(a.pdf,native,a.manifest,1400)
    document=load(native/'document.json')
    assert digest(a.pdf.read_bytes())==document['sha256']
    start_clean=time.perf_counter();build(native,None)
    rows=read_jsonl(native/'normalized.jsonl')
    start_dedup=time.perf_counter();duplicates=dedup(rows)
    dump_json(run/'deduplication.json',duplicates)
    write_jsonl(run/'normalized.native.jsonl',rows)
    dedup_seconds=time.perf_counter()-start_dedup
    start_pack=time.perf_counter()
    accepted=[r for r in rows if r['quality']['status']=='accepted']
    packed=export(accepted,run/'local_preview',a.tokenizer,'native_only_provisional')
    with zipfile.ZipFile(run/'local_preview.zip','w',zipfile.ZIP_DEFLATED) as z:
        for path in sorted((run/'local_preview').glob('*')):
            if path.is_file():z.write(path,path.name)
    pack_seconds=time.perf_counter()-start_pack
    pages=[int(x) for x in a.pages.split(',')]
    zip_path=bundle(run,pages)
    result={'document_sha256':document['sha256'],'pages':len(rows),
            'local_native_status_counts':dict(collections.Counter(r['quality']['status'] for r in rows)),
            'dedup':{'text_duplicate_groups':len(duplicates['text_duplicate_groups']),
                     'exact_render_and_text_duplicates':len(duplicates['exact_duplicates']),
                     'near_pairs':len(duplicates['near_pairs']),'seconds':dedup_seconds},
            'pack':packed,'pack_seconds':pack_seconds,
            'clean_dedup_pack_bundle_seconds':time.perf_counter()-start_clean,
            'command_elapsed_seconds':time.perf_counter()-start,
            'colab_input_bytes':zip_path.stat().st_size,'pilot_pages':pages,
            'gpu_stage':'not_run_here','quality_metrics_need_independent_gold':True,
            'old_cpu_paddle_cache_used':False}
    dump_json(run/'local_result.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))


def merge(a):
    run=a.run.resolve();manifest=load(run/'request_manifest.json')
    with zipfile.ZipFile(a.results) as z:
        result=json.loads(z.read('results.json'))
    if result['manifest_sha256']!=digest((run/'request_manifest.json').read_bytes()):
        raise ValueError('Cloud result belongs to a different input manifest')
    requests={p['page']:p for p in manifest['requests']};by_page={}
    for r in result['pages']:
        p=requests[r['page']]
        if r['page'] in by_page:raise ValueError('Duplicate returned page')
        if any(r[k]!=p[k] for k in ['document_sha256','render_sha256']):raise ValueError('Cloud source mismatch')
        for stage in ['paddle','vlm']:
            nested=r.get(stage,{})
            if nested.get('status')!='not_run' and any(nested.get(k)!=p[k] for k in ['document_sha256','render_sha256','page']):
                raise ValueError('Nested prediction source mismatch')
            if nested.get('status')!='not_run' and nested.get('manifest_sha256')!=result['manifest_sha256']:
                raise ValueError('Stale nested prediction')
        by_page[r['page']]=r
    if set(by_page)!=set(requests):raise ValueError('Incomplete cloud return')
    dump_json(run/'cloud_return.json',result)
    write_jsonl(run/'cloud_review_queue.jsonl',({'page':p,'source':requests[p],
                'prediction':r,'verified':False,'action':'compare OCR/formulas/visual relations against source image'} for p,r in by_page.items()))
    if not a.reviews:
        print('Cloud predictions imported for review. No unverified content exported for training.');return
    native={r['page']:r for r in read_jsonl(run/'normalized.native.jsonl')};approved=[]
    seen_pages=set()
    for review in read_jsonl(a.reviews):
        if review['page'] in seen_pages:raise ValueError('Conflicting duplicate review page')
        seen_pages.add(review['page'])
        p=requests[review['page']]
        if not (review.get('verified') is True and review.get('reviewer') and review.get('evidence') and
                isinstance(review.get('text'),str) and review['text'].strip()):raise ValueError('Incomplete review')
        if any(review.get(k)!=p[k] for k in ['document_sha256','render_sha256']):raise ValueError('Stale review')
        from common import normalize,redact
        row=dict(native[review['page']]);row['text']=redact(normalize(review['text'],code=True))[0]
        row['review']=review;approved.append(row)
    if not approved:raise ValueError('No source-verified transcripts to export')
    report=dedup(approved);dump_json(run/'final_deduplication.json',report)
    export(approved,run/'reviewed_cpt',a.tokenizer,'reviewed_cloud_return')
    print('Exported source-verified transcripts only:',run/'reviewed_cpt')


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('--pdf',type=Path,required=True)
    prep.add_argument('--manifest',type=Path);prep.add_argument('--pages',default=','.join(map(str,PILOT)))
    ret=sub.add_parser('merge');ret.add_argument('--results',type=Path,required=True);ret.add_argument('--reviews',type=Path)
    for s in [prep,ret]:
        s.add_argument('--run',type=Path,default=ROOT/'runs/it3170_test');s.add_argument('--tokenizer',type=Path,default=TOKENIZER)
    args=p.parse_args();prepare(args) if args.command=='prepare' else merge(args)
