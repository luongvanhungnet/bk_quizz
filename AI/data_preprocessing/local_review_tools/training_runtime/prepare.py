import argparse
import importlib.metadata
from pathlib import Path
from data_utils import load, save, sha, iter_verified_samples, stream_packs
import json


def prepare(root, out, tokenizer_path=None):
    from transformers import AutoTokenizer
    cfg = load(root/'config.json')
    manifest=load(root/'data/manifest.json')
    tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_path or cfg['model_id']), revision=cfg['revision'],
                                             trust_remote_code=False,local_files_only=bool(tokenizer_path))
    if tokenizer.eos_token_id is None:
        raise ValueError('Checkpoint must define its own EOS')
    out.mkdir(parents=True, exist_ok=True)
    token_count=0;sequence_count=0;targets=0
    packed=stream_packs(iter_verified_samples(root),lambda t:tokenizer.encode(t,add_special_tokens=False),
                        tokenizer.eos_token_id,cfg['sequence_length'])
    with (out/'train.packed.jsonl').open('w',encoding='utf-8') as texts,(out/'train.sources.jsonl').open('w',encoding='utf-8') as sources:
        for index,row in enumerate(packed):
            token_count+=len(row['input_ids']);sequence_count+=1;targets+=len(row['input_ids'])-1
            sources.write(json.dumps({'index':index,'spans':row.pop('source_spans')},ensure_ascii=False)+'\n')
            texts.write(json.dumps(row,separators=(',',':'))+'\n')
            if sequence_count%1000==0:print('Packed',sequence_count,'sequences;',token_count,'tokens',flush=True)
    tokenizer.save_pretrained(out/'tokenizer')
    info = {'model_id': cfg['model_id'], 'revision': cfg['revision'],
            'transformers_version': importlib.metadata.version('transformers'),
            'dataset_manifest_sha256': sha(root/'data/manifest.json'),
            'input_samples': manifest['samples'], 'sequence_length': cfg['sequence_length'],
            'packed_sequences': sequence_count, 'tokens_including_eos':token_count,
            'supervised_next_token_positions':targets,
            'eos_token': tokenizer.eos_token, 'eos_token_id': tokenizer.eos_token_id,
            'files_sha256': {name:sha(out/name) for name in ['train.packed.jsonl','train.sources.jsonl']},
            'chat_template_applied': False, 'labels_shifted_in_data': False,
            'cross_sample_attention': True, 'last_fragment_kept': True,
            'validation': 'none: existing development/holdout excluded; no independent generalization test'}
    save(out/'manifest.json', info)
    print(info)


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--tokenizer',type=Path);a=p.parse_args()
    prepare(a.root,a.out,a.tokenizer)
