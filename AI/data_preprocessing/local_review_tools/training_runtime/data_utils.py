"""Auditable text-only CPT preparation. No chat templates or generated QA."""
import hashlib
import json
import math
from collections import deque
from itertools import zip_longest
from pathlib import Path


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def read_jsonl(path):
    return list(iter_jsonl(path))


def iter_jsonl(path):
    with Path(path).open(encoding='utf-8-sig') as source:
        for line in source:
            if line.strip():yield json.loads(line)


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')


def iter_verified_samples(root):
    root = Path(root)
    manifest = load(root / 'data/manifest.json')
    for name, digest in manifest['files_sha256'].items():
        if sha(root / name) != digest:
            raise ValueError('Bundle file changed: ' + name)
    count=0
    for text, source in zip_longest(iter_jsonl(root/'data/train.jsonl'),iter_jsonl(root/'data/sources.jsonl')):
        if text is None or source is None:raise ValueError('Text/provenance count mismatch')
        if set(text) != {'text'} or not isinstance(text['text'], str) or not text['text'].strip():
            raise ValueError('Expected nonempty text-only training record')
        if hashlib.sha256(text['text'].encode()).hexdigest() != source['text_sha256']:
            raise ValueError('Text/provenance checksum mismatch')
        count+=1
        yield text,source
    if count!=manifest['samples']:raise ValueError('Text/provenance count mismatch')


def verify_bundle(root):
    pairs=list(iter_verified_samples(root))
    return [p[0] for p in pairs],[p[1] for p in pairs],load(Path(root)/'data/manifest.json')


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


def stream_packs(pairs,encode,eos,size):
    """Pack with bounded memory, preserving source spans and a trainable tail."""
    if size<2:raise ValueError('Sequence length must be >=2')
    tokens=[];segments=deque();offset=0;total=0
    def take(n):
        nonlocal offset
        ids=tokens[:n];del tokens[:n];end=offset+n;spans=[]
        for a,b,source in segments:
            if a>=end:break
            left=max(a,offset);right=min(b,end)
            if left<right:spans.append({'sample_id':source['id'],'page':source['page'],
                'token_start':left-offset,'token_end':right-offset,
                'source_token_start':left-a,'source_token_end':right-a})
        while segments and segments[0][1]<=end:segments.popleft()
        offset=end
        if len(ids)<2:raise ValueError('Insufficient tokens for causal LM training')
        return {'input_ids':ids,'attention_mask':[1]*len(ids),'labels':ids.copy(),'source_spans':spans}
    for row,source in pairs:
        ids=encode(row['text'])+[eos];segments.append((total,total+len(ids),source));total+=len(ids);tokens.extend(ids)
        # Retain lookahead so a final one-token fragment is never discarded.
        while len(tokens)>size+1:yield take(size)
    if len(tokens)==size+1:yield take(size-1)
    if tokens:yield take(len(tokens))


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
