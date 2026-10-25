import argparse
import importlib.metadata
from pathlib import Path
from data_utils import load, save, sha, verify_bundle, pack, write_jsonl


def prepare(root, out):
    from transformers import AutoTokenizer
    cfg = load(root/'config.json')
    rows, sources, manifest = verify_bundle(root)
    tokenizer = AutoTokenizer.from_pretrained(cfg['model_id'], revision=cfg['revision'],
                                             trust_remote_code=False)
    if tokenizer.eos_token_id is None:
        raise ValueError('Checkpoint must define its own EOS')
    packed = pack(rows, sources, lambda t: tokenizer.encode(t, add_special_tokens=False),
                  tokenizer.eos_token_id, cfg['sequence_length'])
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out/'train.packed.jsonl', [{k:v for k,v in r.items() if k!='source_spans'} for r in packed])
    write_jsonl(out/'train.sources.jsonl', [{'index':i,'spans':r['source_spans']} for i,r in enumerate(packed)])
    tokenizer.save_pretrained(out/'tokenizer')
    info = {'model_id': cfg['model_id'], 'revision': cfg['revision'],
            'transformers_version': importlib.metadata.version('transformers'),
            'dataset_manifest_sha256': sha(root/'data/manifest.json'),
            'input_samples': len(rows), 'sequence_length': cfg['sequence_length'],
            'packed_sequences': len(packed), 'tokens_including_eos': sum(len(r['input_ids']) for r in packed),
            'supervised_next_token_positions': sum(len(r['labels'])-1 for r in packed),
            'eos_token': tokenizer.eos_token, 'eos_token_id': tokenizer.eos_token_id,
            'files_sha256': {name:sha(out/name) for name in ['train.packed.jsonl','train.sources.jsonl']},
            'chat_template_applied': False, 'labels_shifted_in_data': False,
            'cross_sample_attention': True, 'last_fragment_kept': True,
            'validation': 'none: one document group, train-only; no random page split'}
    save(out/'manifest.json', info)
    print(info)


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    prepare(a.root,a.out)
