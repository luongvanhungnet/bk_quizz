"""Resumable PP-StructureV3 inference on explicitly selected source pages.

Every saved result is bound to the source document AND rendered image SHA.
Failure is recorded, not silently represented as successful OCR.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import importlib.metadata
from pathlib import Path

from common import digest, dump_json, read_jsonl, write_jsonl


def select_pages(spec, pages):
    if spec == 'all':
        return {p['page'] for p in pages}
    if spec == 'needed':
        return {p['page'] for p in pages if p['native_text_chars'] < 60 or
                any(b['math_candidate'] for b in p['blocks']) or p['vector_regions'] or
                any(not im['decorative_candidate'] for im in p['images'])}
    result = set()
    for part in spec.split(','):
        ends = list(map(int, part.split('-')))
        result.update(range(ends[0], ends[-1]+1))
    return result


def run(out: Path, spec: str, device='cpu', threads=2, tables=True, mkldnn=True):
    os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK', 'True')
    os.environ.setdefault('PADDLE_PDX_MODEL_SOURCE', 'BOS')
    from paddleocr import PPStructureV3
    pages = read_jsonl(out/'native_pages.jsonl')
    selected = select_pages(spec, pages)
    pending = []
    for p in pages:
        path = out/'ppstructure'/f'page_{p["page"]:04d}.json'
        old = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        if p['page'] in selected and not (old.get('status') == 'ok' and
                old.get('render_sha256') == p['render_sha256'] and
                old.get('document_sha256') == p['document_sha256'] and old.get('tables_enabled') == tables):
            pending.append(p)
    print(f'PP-StructureV3 pending: {len(pending)}/{len(selected)}', flush=True)
    if not pending:
        return
    pipe = PPStructureV3(device=device, cpu_threads=threads, enable_mkldnn=mkldnn,
                         use_doc_orientation_classify=False, use_doc_unwarping=False,
                         use_textline_orientation=False, use_region_detection=False,
                         use_seal_recognition=False, use_chart_recognition=False,
                         use_table_recognition=tables, use_formula_recognition=True,
                         layout_detection_model_name='PP-DocLayout-M',
                         text_detection_model_name='PP-OCRv5_mobile_det',
                         text_recognition_model_name='latin_PP-OCRv5_mobile_rec',
                         formula_recognition_model_name='PP-FormulaNet-S', formula_recognition_batch_size=1)
    for i, p in enumerate(pending, 1):
        started = time.time()
        path = out/'ppstructure'/f'page_{p["page"]:04d}.json'
        record = {'page': p['page'], 'document_sha256': p['document_sha256'],
                  'render_sha256': p['render_sha256'], 'engine': 'PP-StructureV3',
                  'tables_enabled': tables, 'formula_model': 'PP-FormulaNet-S',
                  'ocr_model': 'latin_PP-OCRv5_mobile_rec', 'device': device,
                  'enable_mkldnn': mkldnn, 'cpu_threads': threads,
                  'runtime_versions': {m: importlib.metadata.version(m) for m in ['paddleocr','paddlex','paddlepaddle']}}
        try:
            try:
                result = next(iter(pipe.predict(str(out/p['render_path']), use_table_orientation_classify=False)))
            except AttributeError as exc:
                # PaddleX can attempt a cell-split OCR pass while the table
                # child OCR is disabled by PP-StructureV3. Retry with its public
                # cell-OCR matching switch off; keep the result unverified.
                if tables and "text_rec_model" in str(exc) and 'NoneType' in str(exc):
                    record['fallback'] = {'reason':'table_child_ocr_unavailable', 'use_ocr_results_with_table_cells':False}
                    result = next(iter(pipe.predict(str(out/p['render_path']), use_table_orientation_classify=False,
                                                    use_ocr_results_with_table_cells=False)))
                else:
                    raise
            raw = result.json
            record.update(status='ok', result=raw.get('res', raw))
        except Exception as exc:
            record.update(status='error', error=f'{type(exc).__name__}: {exc}')
        record['elapsed_seconds'] = round(time.time()-started, 3)
        dump_json(path, record)
        print(f'PP {i}/{len(pending)} page={p["page"]} {record["status"]} {record["elapsed_seconds"]}s', flush=True)
    errors = [p['page'] for p in pending if json.loads((out/'ppstructure'/f'page_{p["page"]:04d}.json').read_text(encoding='utf-8'))['status'] != 'ok']
    if errors:
        raise RuntimeError(f'PP-StructureV3 failed on pages {errors}; see per-page error records')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--pages', default='needed', help='all, needed, or 1,20,755-769 (1-based)')
    p.add_argument('--device', default='cpu')
    p.add_argument('--threads', type=int, default=2)
    p.add_argument('--no-tables', action='store_true')
    p.add_argument('--no-mkldnn', action='store_true')
    a = p.parse_args()
    run(a.out, a.pages, a.device, a.threads, not a.no_tables, not a.no_mkldnn)
