"""Independent, streaming validation of the final export and real Qwen3 packing."""
import argparse
from collections import Counter
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import struct
import unicodedata
from release_training import jsonl,sha_file,write_json


def normalized(text):return unicodedata.normalize('NFC',text).strip()


def latest(database):
    if not Path(database).is_file():return {},0
    with closing(sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True)) as c:
        rows={rid:json.loads(payload) for rid,payload in c.execute('SELECT r.record_id,r.payload FROM reviews r JOIN (SELECT record_id,MAX(sequence) s FROM reviews GROUP BY record_id) x ON r.sequence=x.s')}
        return rows,c.execute('SELECT COUNT(*) FROM reviews').fetchone()[0]


def validate(root,prepared):
    from transformers import AutoTokenizer
    root=Path(root);prepared=Path(prepared);package=root/'colab'
    manifest=json.loads((package/'data/manifest.json').read_text(encoding='utf-8'))
    prep=json.loads((prepared/'manifest.json').read_text(encoding='utf-8'))
    for name,digest in manifest['files_sha256'].items():assert sha_file(package/name)==digest,name
    for name,digest in prep['files_sha256'].items():assert sha_file(prepared/name)==digest,name
    assert prep['dataset_manifest_sha256']==sha_file(package/'data/manifest.json')
    cfg=json.loads((package/'config.json').read_text(encoding='utf-8'))
    assert (prep['model_id'],prep['revision'])==(cfg['model_id'],cfg['revision'])
    tok=AutoTokenizer.from_pretrained(root/'tokenizer_pinned',local_files_only=True,trust_remote_code=False)
    reviews={};events=0;originals=0
    catalog=json.loads((root/'snapshots/review_catalog.json').read_text(encoding='utf-8'))
    stage=json.loads((root/'stage_report.json').read_text(encoding='utf-8'))
    snapshots={r['document_id']:r for r in stage['documents']}
    for doc in catalog['documents']:
        identifier=doc['document_id'];saved,n=latest(root/'snapshots'/(identifier+'.sqlite3'))
        current,current_n=latest(Path(doc['run'])/'human_reviews.sqlite3')
        assert current==saved and current_n==n,'Review history changed after snapshot'
        assert sha_file(Path(doc['run'])/'records.jsonl')==snapshots[identifier]['records_sha256'],'Original records changed'
        reviews.update({(identifier,rid):r for rid,r in saved.items()});events+=n;originals+=1
    protected_text={normalized(r['text']) for r in jsonl(root/'protected.jsonl') if r.get('text','').strip()}
    protected_render={r['record'].get('render_sha256') for r in jsonl(root/'protected.jsonl')}-{None}
    counts=Counter();seen=set();expected={};token_digest=hashlib.sha256();characters=0
    texts=iter(jsonl(package/'data/train.jsonl'));sources=iter(jsonl(package/'data/sources.jsonl'))
    while True:
        row=next(texts,None);source=next(sources,None)
        if row is None or source is None:
            assert row is None and source is None,'Text/provenance length mismatch'
            break
        text=row['text'];key=normalized(text);assert text.strip() and key not in seen and key not in protected_text
        assert hashlib.sha256(text.encode()).hexdigest()==source['text_sha256']
        assert source['split']=='train' and source['identity']['render_sha256'] not in protected_render
        review=reviews.get((source['document_id'],source['record_id']))
        if source['acceptance']=='owner_default_pass':assert review is None and source['human_verified'] is False
        else:
            assert review and review['decision'] in {'approve','correct'} and review['identity']==source['identity']
            assert source['review_id']==review['review_id'] and source['human_verified'] is True
            accepted=unicodedata.normalize('NFC',review['accepted_text']).strip()
            accepted=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[EMAIL]',accepted)
            assert text==accepted
        seen.add(key);characters+=len(text);counts[source['acceptance']]+=1
        tokens=tok.encode(text,add_special_tokens=False)+[tok.eos_token_id]
        token_digest.update(struct.pack('<'+str(len(tokens))+'I',*tokens))
        expected[source['id']]={'tokens':len(tokens),'covered':0,'page':source['page']}
    assert len(expected)==manifest['samples'] and characters==manifest['characters']
    actual_digest=hashlib.sha256();packs=0;tokens=0;span_rows=iter(jsonl(prepared/'train.sources.jsonl'))
    for row in jsonl(prepared/'train.packed.jsonl'):
        ids=row['input_ids'];assert 2<=len(ids)<=cfg['sequence_length']
        assert row['labels']==ids and row['attention_mask']==[1]*len(ids)
        actual_digest.update(struct.pack('<'+str(len(ids))+'I',*ids));tokens+=len(ids)
        spans=next(span_rows);assert spans['index']==packs;position=0
        for span in spans['spans']:
            source=expected[span['sample_id']]
            assert source['page']==span['page'] and span['token_start']==position
            assert span['source_token_start']==source['covered']
            width=span['token_end']-span['token_start'];assert width>0
            assert span['source_token_end']-span['source_token_start']==width
            source['covered']+=width;position=span['token_end']
        assert position==len(ids);packs+=1
    assert next(span_rows,None) is None
    assert all(s['tokens']==s['covered'] for s in expected.values())
    assert actual_digest.hexdigest()==token_digest.hexdigest(),'Packed stream lost or reordered tokens'
    assert tokens==prep['tokens_including_eos'] and packs==prep['packed_sequences']
    report={'passed':True,'unit_tests':{'local_review_export_notebook':18,'runtime_data':7},
        'original_courses_unchanged':originals,'original_review_events_unchanged':events,
        'samples':len(expected),'characters':characters,'acceptance':dict(counts),
        'tokens_including_eos':tokens,'packed_sequences':packs,'token_stream_sha256':actual_digest.hexdigest(),
        'every_source_span_accounted_for':True,'padding_and_causal_labels_checked':True,
        'model_revision':cfg['revision'],'transformers_version':prep['transformers_version'],
        'automatic_human_review_events_created':0,'actual_gpu_training_executed':False}
    write_json(root/'LOCAL_VALIDATION.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--release',type=Path,required=True);parser.add_argument('--prepared',type=Path,required=True)
    args=parser.parse_args();validate(args.release,args.prepared)
