"""Tokenize CPT text using the actual target Qwen tokenizer, append its EOS.

No chat template, role tokens or instruction/answer pairs. Carry a source map
for every packed token span. Do not truncate text or discard final fragments.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import digest, dump_json, read_jsonl, write_jsonl


def pack_records(rows, encode, eos, length):
    if length < 2:
        raise ValueError('Sequence length must be >= 2')
    buffer, spans = [], []
    for row in rows:
        ids = encode(row['text']) + [eos]
        offset = 0
        while offset < len(ids):
            count = min(length-len(buffer), len(ids)-offset)
            spans.append({'sample_id': row['id'], 'page': row['page'],
                          'token_start': len(buffer), 'token_end': len(buffer)+count,
                          'source_token_start': offset, 'source_token_end': offset+count})
            buffer.extend(ids[offset:offset+count])
            offset += count
            if len(buffer) == length:
                yield {'input_ids': buffer, 'attention_mask': [1]*len(buffer), 'labels': buffer.copy(), 'source_spans': spans}
                buffer, spans = [], []
    if buffer:
        yield {'input_ids': buffer, 'attention_mask': [1]*len(buffer), 'labels': buffer.copy(), 'source_spans': spans}


def run(out: Path, tokenizer_name: str, revision: str, length: int):
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_name, revision=revision, trust_remote_code=False)
    if tokenizer.eos_token_id is None:
        raise ValueError('Tokenizer must define an EOS token; do not invent one')
    rows = read_jsonl(out/'cpt/train.metadata.jsonl')
    packs = list(pack_records(rows, lambda t: tokenizer.encode(t, add_special_tokens=False), tokenizer.eos_token_id, length))
    write_jsonl(out/'cpt/train.packed.jsonl', ({k:v for k,v in r.items() if k != 'source_spans'} for r in packs))
    write_jsonl(out/'cpt/train.packed.sources.jsonl', ({'index': i, 'source_spans': r['source_spans']} for i,r in enumerate(packs)))
    tok_dir = out/'cpt/tokenizer'
    tokenizer.save_pretrained(tok_dir)
    from huggingface_hub import try_to_load_from_cache
    cached = try_to_load_from_cache(tokenizer_name, 'tokenizer_config.json', revision=revision)
    resolved_revision = Path(cached).parent.name if isinstance(cached,str) and 'snapshots' in Path(cached).parts else None
    dump_json(out/'cpt/tokenization.json', {'tokenizer': tokenizer_name, 'revision_requested': revision,
              'revision_resolved': resolved_revision,
              'local_files_sha256': {p.name: digest(p.read_bytes()) for p in tok_dir.iterdir() if p.is_file()},
              'eos_token': tokenizer.eos_token, 'eos_token_id': tokenizer.eos_token_id,
              'sequence_length': length, 'packing': 'continuous_causal_with_sample_EOS',
              'cross_sample_attention': True, 'labels_shift': 'trainer_model_shifts_labels_once',
              'last_fragment_kept': True, 'padding': False,
              'total_tokens': sum(len(r['input_ids']) for r in packs), 'sequences': len(packs),
              'source_samples': len(rows), 'chat_template_applied': False})
    print(f'Packed {len(rows)} samples -> {len(packs)} sequences; {sum(len(r["input_ids"]) for r in packs)} tokens')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--tokenizer', default='Qwen/Qwen2.5-7B')
    p.add_argument('--revision', default='main')
    p.add_argument('--seq-length', type=int, default=2048)
    a = p.parse_args()
    run(a.out, a.tokenizer, a.revision, a.seq_length)
