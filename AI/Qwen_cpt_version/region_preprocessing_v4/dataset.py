"""Only carried or explicitly source-reviewed transcripts; protect benchmark groups."""
from pathlib import Path
import sys
from contracts import write_once,load,file_hash


def pack_dataset(rows,out,tokenizer,protected_pages):
    from transformers import AutoTokenizer
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'data_preprocessing/src'))
    from pack_qwen import pack_records
    from common import redact,normalize
    out=Path(out)
    if out.exists():raise ValueError('Choose a fresh dataset version')
    out.mkdir(parents=True)
    held=[r for r in rows if r['page'] in protected_pages]
    accepted=[r for r in rows if r['page'] not in protected_pages]
    for r in accepted:
        r['text']=redact(normalize(r['text'],code=True))[0]
    tok=AutoTokenizer.from_pretrained(str(tokenizer),local_files_only=True,trust_remote_code=False)
    if tok.eos_token_id is None:raise ValueError('Missing target tokenizer EOS')
    packs=list(pack_records(accepted,lambda s:tok.encode(s,add_special_tokens=False),tok.eos_token_id,1024))
    expected=[i for r in accepted for i in tok.encode(r['text'],add_special_tokens=False)+[tok.eos_token_id]]
    if [i for p in packs for i in p['input_ids']]!=expected:raise ValueError('Token preservation failure')
    import json
    def jsonl(name,data):(out/name).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in data),encoding='utf-8')
    jsonl('train.jsonl',({'text':r['text']} for r in accepted));jsonl('train.metadata.jsonl',accepted)
    jsonl('train.packed.jsonl',({k:v for k,v in p.items() if k!='source_spans'} for p in packs))
    jsonl('train.packed.sources.jsonl',({'index':i,'source_spans':p['source_spans']} for i,p in enumerate(packs)))
    jsonl('withheld_for_benchmark.metadata.jsonl',held)
    write_once(out/'manifest.json',{'samples':len(accepted),'tokens':len(expected),'sequences':len(packs),'eos_token_id':tok.eos_token_id,
        'withheld_samples':len(held),'all_protected_group_pages':sorted(protected_pages),'sequence_length':1024,
        'tokenizer_source':str(tokenizer),'tokenizer_sha256':{p.name:file_hash(p) for p in Path(tokenizer).glob('*token*') if p.is_file()},
        'chat_template_applied':False,'labels_shift':'causal_model_shifts_once','last_fragment_kept':True,
        'split_policy':'holdout_source_segments_near_text_and_exact_visual_components_excluded_from_training',
        'new_unverified_predictions_in_train':0,'all_pdf_content_complete':False})
    return load(out/'manifest.json')
