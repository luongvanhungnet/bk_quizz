"""RAG prototype: query train-only fact index, plan4concepts, generate and validate."""
import argparse
from pathlib import Path
from common import canonical, load, save, verify_files
from retrieval import retrieve
from quality import compact_schema, compact_score, hydrate


def plan(root, query, course=None):
    from planning import choose_related, make_sample
    facts = retrieve(root/'data/retrieval.sqlite3', query, split='train', course=course, limit=20)
    if not facts: raise ValueError('No completed native theory found in training retrieval partition')
    for target in facts:
        related = choose_related(target, facts)
        if related: return make_sample(target, related, 0)
    from common import read_rows
    target = facts[0]
    pool = [f for f in read_rows(root/'data/facts.jsonl') if f['split'] == 'train' and f['course'] == target['course']]
    related = choose_related(target, pool)
    if related: return make_sample(target, related, 0)
    raise ValueError('Not enough distinct source-supported concepts; choose a more specific course/topic')


def main(args):
    verify_files(args.root)
    sample = plan(args.root, args.query, args.course)
    if args.plan_only:
        print(canonical({'query': args.query, 'messages': sample['messages'][:-1], 'sources': sample['evidence']}).decode()); return
    from engine import Generator, load_model
    if args.sft_run:
        from evaluate_v2 import validate_adapter
        adapter = validate_adapter(args.sft_run, __import__('common').sha(args.root/'manifest.json'))
    else: adapter = None
    model, tok = load_model(args.root/'tokenizer', adapter); gen = Generator(model, tok)
    raw = gen.one(sample['messages'][:-1], compact_schema([e['id'] for e in sample['evidence']]))
    score = compact_score(raw['text'], sample)
    result = {'query': args.query, 'sources': sample['evidence'], 'raw': raw, 'score': score, 'production_approved': False}
    if score['usable_proxy']:
        result['quiz'] = hydrate(__import__('json').loads(raw['text']), sample['evidence'])
    if args.output: save(args.output, result)
    print(canonical(result).decode(), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--root', type=Path, required=True); p.add_argument('--query', required=True)
    p.add_argument('--course'); p.add_argument('--sft-run', type=Path); p.add_argument('--plan-only', action='store_true'); p.add_argument('--output', type=Path)
    main(p.parse_args())
