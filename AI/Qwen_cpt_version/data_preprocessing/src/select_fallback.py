"""Select scan/table pages for full PP-StructureV3 after cheap layout analysis."""
import argparse
import json
from pathlib import Path
from common import read_jsonl, dump_json
from build_dataset import component_result


def select(out):
    reviewed = {r['page']:r for r in read_jsonl(out/'reviewed_annotations.jsonl') if r.get('verified')}
    selected = []
    for page in read_jsonl(out/'native_pages.jsonl'):
        note = reviewed.get(page['page'], {})
        if note.get('document_sha256') == page['document_sha256'] and note.get('render_sha256') == page['render_sha256']:
            continue
        comp = component_result(out, page)
        table = bool(comp and any(b['label'] == 'table' for b in comp['result']['layout_det_res'].get('boxes', [])))
        if table or page['native_text_chars'] < 60:
            selected.append({'page': page['page'], 'reason': 'table_layout' if table else 'sparse_or_image_page'})
    dump_json(out/'fallback_pages.json', selected)
    return selected


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out',type=Path,required=True)
    a = p.parse_args()
    print(','.join(str(r['page']) for r in select(a.out)))
