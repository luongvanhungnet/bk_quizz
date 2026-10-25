"""Native-PDF hybrid path using the layout/formula components of PP-StructureV3.

Avoid OCR of every native text line. Full PP-StructureV3 remains available in
recognize.py for scanned pages and table structure recognition.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import time
from pathlib import Path

from PIL import Image

from common import area, digest, dump_json, overlap, read_jsonl


def run(out: Path, threads=4, mkldnn=True, limit=None):
    os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK', 'True')
    os.environ.setdefault('PADDLE_PDX_MODEL_SOURCE', 'BOS')
    from paddleocr import FormulaRecognition, LayoutDetection
    pages = read_jsonl(out/'native_pages.jsonl')
    pending = []
    for p in pages:
        path = out/'components'/f'page_{p["page"]:04d}.json'
        old = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        if not (old.get('status') == 'ok' and old.get('render_sha256') == p['render_sha256'] and old.get('document_sha256') == p['document_sha256']):
            pending.append(p)
    if limit:
        pending = pending[:limit]
    print(f'Hybrid component pages pending {len(pending)}', flush=True)
    if not pending:
        return
    options = dict(device='cpu', cpu_threads=threads, enable_mkldnn=mkldnn)
    layout = LayoutDetection(model_name='PP-DocLayout-M', **options)
    formula = FormulaRecognition(model_name='PP-FormulaNet-S', **options)
    for i,p in enumerate(pending, 1):
        start = time.time()
        image_path = out/p['render_path']
        if digest(image_path.read_bytes()) != p['render_sha256']:
            raise ValueError(f'Stale or damaged page render {p["page"]}')
        raw = next(iter(layout.predict(str(image_path), batch_size=1)))
        det = raw.json.get('res', raw.json)
        formulas, ignored = [], []
        scale = p['render_width']/p['page_size_pt'][0]
        code_boxes = [[v*scale for v in b['bbox']] for b in p['blocks'] if b['type'] == 'code']
        for box in det.get('boxes', []):
            if box['label'] != 'formula':
                continue
            coords = box['coordinate']
            if any(overlap(coords,c)/max(1,area(coords)) > .65 for c in code_boxes):
                ignored.append({'bbox_pixels':coords,'reason':'overlaps_native_code'})
                continue
            with Image.open(image_path) as im:
                clip = (max(0,int(coords[0])-3), max(0,int(coords[1])-3),
                        min(im.width,int(coords[2])+4), min(im.height,int(coords[3])+4))
                if clip[2] <= clip[0] or clip[3] <= clip[1]:
                    continue
                crop_path = out/'assets/formulas'/f'p{p["page"]:04d}_f{len(formulas):03d}.png'
                crop_path.parent.mkdir(parents=True, exist_ok=True)
                im.crop(clip).save(crop_path)
            result = next(iter(formula.predict(str(crop_path), batch_size=1)))
            rec = result.json.get('res', result.json)
            formulas.append({'rec_formula': rec.get('rec_formula'), 'rec_score': rec.get('rec_score'),
                             'dt_polys': list(clip), 'layout_score': box['score'],
                             'source_crop': crop_path.relative_to(out).as_posix()})
        record = {'page':p['page'], 'status':'ok', 'engine':'PP-StructureV3_components',
                  'layout_model':'PP-DocLayout-M', 'formula_model':'PP-FormulaNet-S',
                  'runtime_versions': {m:importlib.metadata.version(m) for m in ['paddleocr','paddlex','paddlepaddle']},
                  'render_sha256':p['render_sha256'], 'document_sha256':p['document_sha256'],
                  'result':{'layout_det_res': det, 'formula_res_list': formulas, 'ignored_formula_candidates': ignored},
                  'elapsed_seconds':round(time.time()-start,3)}
        dump_json(out/'components'/f'page_{p["page"]:04d}.json', record)
        if i%10 == 0 or i == len(pending):
            print(f'Hybrid {i}/{len(pending)} page={p["page"]} time={record["elapsed_seconds"]}s formulas={len(formulas)}', flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--threads', type=int, default=4)
    p.add_argument('--no-mkldnn', action='store_true')
    p.add_argument('--limit', type=int)
    a = p.parse_args()
    run(a.out, a.threads, not a.no_mkldnn, a.limit)
