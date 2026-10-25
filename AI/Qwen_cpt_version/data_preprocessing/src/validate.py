"""Check source coverage, leakage, audit links, training labels and token loss."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import EMAIL, digest, dump_json, read_jsonl


def validate(out: Path):
    document = json.loads((out/'document.json').read_text(encoding='utf-8'))
    native = read_jsonl(out/'native_pages.jsonl')
    normalized = read_jsonl(out/'normalized.jsonl')
    metadata = read_jsonl(out/'cpt/train.metadata.jsonl')
    train = read_jsonl(out/'cpt/train.jsonl')
    errors = []
    def check(condition, message):
        if not condition:
            errors.append(message)
    check(digest(Path(document['path']).read_bytes()) == document['sha256'], 'Source PDF SHA mismatch')
    expected_sources = {}
    for part in document.get('parts', []):
        path = Path(part['path'])
        check(path.exists() and digest(path.read_bytes()) == part['source_sha256'], f'Original PDF SHA mismatch {part["file_id"]}')
        for page,source_page in enumerate(part['pages_selected'],part['output_start']):
            expected_sources[page] = (part['file_id'],source_page)
    check(len(normalized) == len(native) == document['pages'], 'Page count mismatch')
    check({r['page'] for r in normalized} == set(range(1,document['pages']+1)), 'Missing/duplicated normalized page')
    for p in native:
        path = out/p['render_path']
        check(path.exists() and digest(path.read_bytes()) == p['render_sha256'], f'Invalid render {p["page"]}')
        check(p['document_sha256'] == document['sha256'], f'Wrong document source {p["page"]}')
        check(bool(p['original_source']), f'Upstream page mapping missing {p["page"]}')
        if p['page'] in expected_sources:
            check((p['original_source']['source_id'],p['original_source']['source_page']) == expected_sources[p['page']], f'Incorrect upstream page mapping {p["page"]}')
    native_by_page = {r['page']:r for r in native}
    for folder in ['components','ppstructure']:
        for path in (out/folder).glob('page_*.json'):
            result = json.loads(path.read_text(encoding='utf-8'))
            source = native_by_page.get(result.get('page'))
            check(bool(source) and result.get('document_sha256') == document['sha256'] and
                  result.get('render_sha256') == source['render_sha256'], f'Stale recognition result {path.name}')
            check(result.get('status') == 'ok', f'Recognition error remains in {folder}/{path.name}')
    check(len(metadata) == len(train), 'Training metadata count mismatch')
    check(len({r['exact_hash'] for r in metadata}) == len(metadata), 'Duplicate training text')
    check(all(a['text'] == b['text'] for a,b in zip(metadata,train)), 'Training text differs from audited metadata')
    check(all(r['quality']['status'] == 'accepted' and not r['quality']['flags'] for r in metadata), 'Unresolved data entered training')
    check(not any(EMAIL.search(r['text']) for r in train), 'Email PII remained in training text')
    for split in ['validation','test']:
        check(not read_jsonl(out/f'cpt/{split}.jsonl'), 'A single document must not be randomly split by page')
    config_path = out/'cpt/tokenization.json'
    token_stats = None
    if config_path.exists():
        from transformers import AutoTokenizer
        config = json.loads(config_path.read_text(encoding='utf-8'))
        tokenizer = AutoTokenizer.from_pretrained(out/'cpt/tokenizer', local_files_only=True, trust_remote_code=False)
        packs = read_jsonl(out/'cpt/train.packed.jsonl')
        mapping = read_jsonl(out/'cpt/train.packed.sources.jsonl')
        expected = []
        samples = {}
        for r in metadata:
            ids = tokenizer.encode(r['text'], add_special_tokens=False) + [tokenizer.eos_token_id]
            expected.extend(ids)
            samples[r['id']] = ids
        check(len(packs) == len(mapping), 'Packed source map count mismatch')
        observed = []
        for i,(p,m) in enumerate(zip(packs,mapping)):
            ids = p['input_ids']
            observed.extend(ids)
            check(0 < len(ids) <= config['sequence_length'], f'Invalid packed length {i}')
            check(p['labels'] == ids and p['attention_mask'] == [1]*len(ids), f'Invalid causal LM labels/mask {i}')
            covered = 0
            for s in m['source_spans']:
                a,b = s['token_start'],s['token_end']
                check(a == covered, f'Packed source map gap {i}')
                check(ids[a:b] == samples[s['sample_id']][s['source_token_start']:s['source_token_end']], f'Packed source token mismatch {i}')
                covered = b
            check(covered == len(ids), f'Incomplete packed source map {i}')
        check(observed == expected, 'Token loss, unexpected truncation or EOS insertion error')
        token_stats = {'tokens': len(observed), 'sequences': len(packs), 'source_samples':len(metadata)}
    report = {'passed': not errors, 'errors': errors, 'source_pages':len(native),
              'training_samples':len(train), 'tokenization':token_stats,
              'checks':['source SHA-256','all-page coverage','render SHA-256','upstream page traceability',
                        'recognition result source binding and completion',
                        'quality quarantine','exact duplicates','PII email scan','document-level split isolation',
                        'token-preserving packing and source spans','causal LM labels and attention masks']}
    dump_json(out/'validation.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out',type=Path,required=True)
    a = p.parse_args()
    validate(a.out)
