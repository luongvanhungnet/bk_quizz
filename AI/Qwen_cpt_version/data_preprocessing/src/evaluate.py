"""Reference-based CER/WER on a named, source-bound QA subset, never corpus-wide."""
import argparse
import json
import re
from pathlib import Path
from common import dump_json, normalize, read_jsonl


def edit_distance(a,b):
    prev = list(range(len(b)+1))
    for i,x in enumerate(a,1):
        row = [i]
        for j,y in enumerate(b,1):
            row.append(min(row[-1]+1, prev[j]+1, prev[j-1]+(x != y)))
        prev = row
    return prev[-1]


def canonical(text):
    return re.sub(r'\s+',' ', normalize(text)).strip()


def run(out, reference):
    native = {r['page']: r for r in read_jsonl(out/'native_pages.jsonl')}
    refs = read_jsonl(reference)
    scored = []
    for r in refs:
        p = native[r['page']]
        if r['document_sha256'] != p['document_sha256'] or r['render_sha256'] != p['render_sha256']:
            raise ValueError('Reference source hash mismatch')
        selected = [b['text'] for b in p['blocks'] if b['bbox'][1] < p['page_size_pt'][1]*.9 and not (re.fullmatch(r'\d+(?:\s*/\s*\d+)?', b['text']) and b['bbox'][1]>p['page_size_pt'][1]*.86)]
        ref,hyp = canonical(r['reference_text']),canonical('\n'.join(selected))
        ce,we = edit_distance(ref,hyp),edit_distance(ref.split(),hyp.split())
        scored.append({'page':r['page'],'char_errors':ce,'reference_chars':len(ref),
                       'word_errors':we,'reference_words':len(ref.split()),
                       'CER':ce/max(1,len(ref)),'WER':we/max(1,len(ref.split()))})
    report = {'scope':'agent_visual_transcription_QA_subset_not_independent_human_benchmark',
              'evaluated_layer':'native_pdf_after_geometry_repair_before_reviewed_text_overrides',
              'canonicalization':'NFC and collapsed whitespace; math scripts retained as ^{...}',
              'reference_file':str(reference), 'page_count':len(scored),'per_page':scored,
              'CER':sum(r['char_errors'] for r in scored)/max(1,sum(r['reference_chars'] for r in scored)),
              'WER':sum(r['word_errors'] for r in scored)/max(1,sum(r['reference_words'] for r in scored))}
    dump_json(out/'qa/reference_metrics.json', report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--reference',type=Path,required=True)
    a=p.parse_args()
    run(a.out,a.reference)
