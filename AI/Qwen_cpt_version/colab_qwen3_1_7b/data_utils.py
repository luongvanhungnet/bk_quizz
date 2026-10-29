"""Auditable text-only CPT preparation. No chat templates or generated QA."""
import hashlib
import json
import math
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')


def verify_bundle(root):
    root = Path(root)
    manifest = load(root / 'data/manifest.json')
    for name, digest in manifest['files_sha256'].items():
        if sha(root / name) != digest:
            raise ValueError('Bundle file changed: ' + name)
    rows = read_jsonl(root / 'data/train.jsonl')
    sources = read_jsonl(root / 'data/sources.jsonl')
    if len(rows) != len(sources) or len(rows) != manifest['samples']:
        raise ValueError('Text/provenance count mismatch')
    for text, source in zip(rows, sources):
        if set(text) != {'text'} or not isinstance(text['text'], str) or not text['text'].strip():
            raise ValueError('Expected nonempty text-only training record')
        if hashlib.sha256(text['text'].encode()).hexdigest() != source['text_sha256']:
            raise ValueError('Text/provenance checksum mismatch')
    return rows, sources, manifest


def pack(rows, sources, encode, eos, size):
    if size < 2:
        raise ValueError('Sequence length must be >= 2')
    tokens, ranges = [], []
    for row, source in zip(rows, sources):
        start = len(tokens)
        tokens.extend(encode(row['text']) + [eos])
        ranges.append((start, len(tokens), source))
    ends = list(range(size, len(tokens), size)) + [len(tokens)]
    # A 1-token sequence has zero next-token targets and can produce NaN loss.
    if len(ends) > 1 and ends[-1] - ends[-2] == 1:
        ends[-2] -= 1
    result, start = [], 0
    for end in ends:
        ids = tokens[start:end]
        if len(ids) < 2:
            raise ValueError('Insufficient tokens for causal LM training')
        spans = []
        for a, b, source in ranges:
            left, right = max(a, start), min(b, end)
            if left < right:
                spans.append({'sample_id': source['id'], 'page': source['page'],
                              'token_start': left-start, 'token_end': right-start,
                              'source_token_start': left-a, 'source_token_end': right-a})
        result.append({'input_ids': ids, 'attention_mask': [1]*len(ids),
                       'labels': ids.copy(), 'source_spans': spans})
        start = end
    assert [t for row in result for t in row['input_ids']] == tokens
    return result


def padded_batch(rows, pad_id):
    """Mask padding by position, never by token identity (EOS can equal PAD)."""
    width = math.ceil(max(len(r['input_ids']) for r in rows)/8)*8
    result = {key: [] for key in ['input_ids', 'attention_mask', 'labels']}
    for row in rows:
        ids = row['input_ids']; n = width-len(ids)
        result['input_ids'].append(ids + [pad_id]*n)
        result['attention_mask'].append([1]*len(ids) + [0]*n)
        result['labels'].append(ids.copy() + [-100]*n)
    return result


def complete_checkpoint(folder):
    folder = Path(folder)
    required = ['trainer_state.json', 'adapter_config.json', 'adapter_model.safetensors',
                'optimizer.pt', 'scheduler.pt', 'rng_state.pth']
    if not all((folder/name).is_file() and (folder/name).stat().st_size > 0 for name in required):
        return False
    try:
        state=load(folder/'trainer_state.json');adapter=load(folder/'adapter_config.json')
        return isinstance(adapter,dict) and state.get('global_step')==int(folder.name.split('-')[-1])
    except (ValueError,TypeError,AttributeError):
        return False


def latest_checkpoint(folder):
    candidates = []
    for p in Path(folder).glob('checkpoint-*'):
        if p.name.split('-')[-1].isdigit() and complete_checkpoint(p):
            candidates.append(p)
    if not candidates:
        raise ValueError('No complete checkpoint: cannot resume optimizer state.')
    return max(candidates, key=lambda p: int(p.name.split('-')[-1]))
