"""Normalize, gate, deduplicate and export traceable CPT samples.

Native text is retained as the authoritative text layer. OCR predictions and
unverified mathematical/visual content stay in the review set, never silently
substitute lecture text. A single document is train-only by design.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import re
import unicodedata
from pathlib import Path

from datasketch import MinHash, MinHashLSH

from common import EMAIL, area, digest, dump_json, latex_check, normalize, overlap, read_jsonl, redact, write_jsonl


def shingles(text):
    # Preserve case, digits, operators and punctuation: a changed inequality matters.
    words = re.findall(r'\w+|[^\w\s]', text, re.UNICODE)
    return {' '.join(words[i:i+5]) for i in range(max(1, len(words)-4))}


def simhash(text):
    weights = [0]*64
    for token in shingles(text):
        h = int(digest(token)[:16], 16)
        for bit in range(64):
            weights[bit] += 1 if h & (1 << bit) else -1
    return sum(1 << i for i, weight in enumerate(weights) if weight >= 0)


def find_duplicates(rows):
    index = MinHashLSH(threshold=.80, num_perm=128)
    hashes, exact, edges = {}, {}, []
    for i, row in enumerate(rows):
        text = row['text']
        key = digest(text)
        row['exact_hash'] = key
        row['duplicate_of'] = exact.get(key)
        exact.setdefault(key, row['id'])
        row['simhash64'] = f'{simhash(text):016x}' if text else None
        tokens = shingles(text)
        if len(text) < 80:
            continue
        mh = MinHash(num_perm=128, seed=42)
        mh.update_batch([s.encode('utf-8') for s in sorted(tokens)])
        for other in index.query(mh):
            j = int(other)
            a = hashes[j]
            similarity = len(tokens & a)/max(1, len(tokens | a))
            distance = (int(row['simhash64'], 16) ^ int(rows[j]['simhash64'], 16)).bit_count()
            if similarity >= .9 or (similarity >= .8 and distance <= 3):
                edges.append({'page_a': rows[j]['page'], 'page_b': row['page'],
                              'jaccard': round(similarity, 6), 'simhash_distance': distance,
                              'action': 'same_split_only_preserve_content'})
        hashes[i] = tokens
        index.insert(str(i), mh)
    return edges


def pp_result(out, page):
    path = out/'ppstructure'/f'page_{page["page"]:04d}.json'
    if not path.exists():
        return None
    obj = json.loads(path.read_text(encoding='utf-8'))
    if obj.get('status') != 'ok' or obj.get('render_sha256') != page['render_sha256'] or obj.get('document_sha256') != page['document_sha256']:
        return None
    return obj


def component_result(out, page):
    path = out/'components'/f'page_{page["page"]:04d}.json'
    if not path.exists():
        return None
    obj = json.loads(path.read_text(encoding='utf-8'))
    if obj.get('status') != 'ok' or obj.get('render_sha256') != page['render_sha256'] or obj.get('document_sha256') != page['document_sha256']:
        return None
    return obj


def margin_signature(text):
    # Numeric masking ONLY in boilerplate detection; never applied to training text.
    return re.sub(r'\d+', '#', normalize(text))


def boilerplate(pages):
    counts = collections.Counter()
    for p in pages:
        h = p['page_size_pt'][1]
        found = {margin_signature(b['text']) for b in p['blocks']
                 if b['bbox'][1] > h*.90 or b['bbox'][3] < h*.035}
        counts.update(found)
    return {text for text, count in counts.items() if count >= max(8, math.ceil(len(pages)*.03))}


def corruption(text):
    return any(c == '\ufffd' or unicodedata.category(c) in ('Co', 'Cs') for c in text)


def baseline_script_candidate(block):
    """Quarantine unflagged raised/lowered small glyphs, especially subscripts."""
    if block['type'] == 'code':
        return False
    for line in block.get('lines', []):
        spans = line.get('spans', [])
        if not spans:
            continue
        base = max(spans, key=lambda s:s['font_size'])
        if any(s['text'].strip() and s['font_size'] < base['font_size']*.9 and
               abs(s['origin'][1]-base['origin'][1]) > base['font_size']*.17 for s in spans):
            return True
    return False


def redact_content(value):
    """Redact nested recognized content while retaining source IDs/geometry."""
    if isinstance(value, str):
        return redact(value)[0]
    if isinstance(value, list):
        return [redact_content(v) for v in value]
    if isinstance(value, dict):
        return {k:redact_content(v) for k,v in value.items()}
    return value


def build(out: Path, annotations: Path | None):
    pages = read_jsonl(out/'native_pages.jsonl')
    document = json.loads((out/'document.json').read_text(encoding='utf-8'))
    notes = {r['page']: r for r in read_jsonl(annotations)} if annotations else {}
    repeated = boilerplate(pages)
    normalized, review, formula_rows, table_rows, visuals, rejected_notes = [], [], [], [], [], []
    statuses, flag_counts = collections.Counter(), collections.Counter()
    for page in pages:
        h, w = page['page_size_pt'][1], page['page_size_pt'][0]
        blocks, removed, pii_events = [], [], []
        flags = []
        for b in page['blocks']:
            value = b['text']
            in_margin = b['bbox'][1] > h*.90 or b['bbox'][3] < h*.035
            page_number = bool(re.fullmatch(r'\d+(?:\s*/\s*\d+)?', value)) and b['bbox'][1] > h*.86
            if page_number or (in_margin and margin_signature(value) in repeated):
                removed.append({'block_id': b['id'], 'reason': 'page_number' if page_number else 'frequent_margin_text', 'bbox': b['bbox']})
                continue
            value, events = redact(value)
            pii_events.extend(events)
            if corruption(value):
                flags.append('corrupt_glyphs')
            blocks.append({'id': b['id'], 'type': b['type'], 'bbox': b['bbox'], 'text': value,
                           'math_candidate': b['math_candidate'] or baseline_script_candidate(b), 'extraction_method': b['extraction_method'],
                           'confidence': b['confidence']})
        pp = pp_result(out, page)
        components = component_result(out, page)
        pred = pp['result'] if pp else (components['result'] if components else {})
        note = notes.get(page['page'])
        if note and (note.get('document_sha256') != page['document_sha256'] or note.get('render_sha256') != page['render_sha256']):
            rejected_notes.append({'page': page['page'], 'reason': 'stale_annotation_source_hash'})
            note = None
        verified = bool(note and note.get('verified') is True and note.get('reviewer') and note.get('evidence') and isinstance(note.get('text'), str))
        # Formula originals consist of source image + native text; LaTeX is a separate hypothesis.
        formulas, ignored_predictions = [], []
        scale = page['render_width']/page['page_size_pt'][0]
        code_boxes = [[v*scale for v in b['bbox']] for b in blocks if b['type'] == 'code']
        def code_region(box):
            return isinstance(box, (list,tuple)) and len(box) == 4 and any(overlap(box,c)/max(1,area(box)) > .65 for c in code_boxes)
        for f in pred.get('formula_res_list', []):
            if code_region(f.get('dt_polys')):
                ignored_predictions.append({'type': 'formula', 'bbox_pixels': f.get('dt_polys'), 'reason': 'overlaps_native_code'})
                continue
            latex = redact(f.get('rec_formula') or '')[0]
            formulas.append({'id': f'{page["id"]}:f{len(formulas)}', 'latex': latex,
                             'bbox_pixels': f.get('dt_polys'), 'confidence': f.get('rec_score'),
                             'validation': latex_check(latex), 'semantic_description': None,
                             'semantic_context': '\n'.join(b['text'] for b in blocks if not b['math_candidate'])[:1500],
                             'source_render': page['render_path'], 'source_crop': f.get('source_crop'),
                             'method': ('PP-StructureV3' if pp else 'PP-StructureV3_components')+'/PP-FormulaNet-S'})
        math_blocks = [b for b in blocks if b['math_candidate'] and b['type'] != 'code']
        if math_blocks and not verified:
            flags.append('math_requires_verification')
        if formulas and not verified:
            flags.append('formula_prediction_requires_verification')
        for b in math_blocks:
            block_pixels = [v*scale for v in b['bbox']]
            matched = any(f.get('bbox_pixels') and overlap(block_pixels, f['bbox_pixels'])/max(1,area(f['bbox_pixels'])) > .3 for f in formulas)
            if not matched:
                formulas.append({'id': f'{page["id"]}:f{len(formulas)}', 'latex': None,
                                 'native_text': b['text'], 'bbox_pt': b['bbox'],
                                 'confidence': None, 'validation': {'semantic_verified': False},
                                 'semantic_description': None, 'semantic_context': None,
                                 'source_render': page['render_path'], 'method': 'native_math_candidate_not_formula_OCR'})
        if verified and 'formulas' in note:
            formulas = [{**redact_content(f), 'id': f'{page["id"]}:f{i}', 'method': 'source_image_visual_review',
                         'validation': {**latex_check(f['latex']), 'semantic_verified': True},
                         'source_render': page['render_path'], 'confidence': None}
                        for i,f in enumerate(note['formulas'])]
        tables = []
        for t in pred.get('table_res_list', []):
            cells = t.get('cell_box_list') or []
            if cells:
                from common import box_union
                if code_region(box_union(cells)):
                    ignored_predictions.append({'type':'table','reason':'overlaps_native_code'})
                    continue
            tables.append({'html': redact_content(t.get('pred_html')), 'bbox_pixels': t.get('cell_box_list'),
                           'method': 'PP-StructureV3', 'verified': False})
        if tables and not verified:
            flags.append('table_requires_verification')
        if verified and 'tables' in note:
            tables = [{**redact_content(t), 'method': 'source_image_visual_review', 'verified': True} for t in note['tables']]
        layout_boxes = pred.get('layout_det_res', {}).get('boxes', [])
        graphic_labels = {'image', 'chart', 'figure', 'table'}
        substantive_images = [im for im in page['images'] if not im['decorative_candidate'] and im['area_fraction'] > .015]
        vector_content = len(page['vector_regions']) >= 3
        pp_graphics = [r for r in layout_boxes if r.get('label') in graphic_labels and not code_region(r.get('coordinate')) and
                       r.get('coordinate', [0,0,0,0])[3] > page['render_width']*h/w*.16 and
                       r.get('coordinate', [0,0,0,0])[1] < page['render_width']*h/w*.9]
        visual_required = bool(substantive_images or vector_content or pp_graphics)
        if visual_required and not verified:
            flags.append('visual_requires_interpretation')
        if page['native_text_chars'] < 60 and not verified:
            flags.append('sparse_page_needs_visual_review')
        if note and not verified:
            flags.append('unverified_annotation')
        # Only source-bound reviewed annotations may replace text or add relations.
        if verified and note.get('text') is not None:
            clean, events = redact(normalize(note['text'], code=True))
            pii_events.extend(events)
            blocks = [{'id': 'verified_transcript', 'type': 'verified_transcript', 'bbox': [0,0,w,h],
                       'text': clean, 'math_candidate': False, 'extraction_method': 'source_image_visual_review',
                       'confidence': {'score': None, 'basis': 'reviewed_not_calibrated'}}]
            flags = [f for f in flags if f not in {'corrupt_glyphs'}]
        visual = {'page': page['page'], 'source_render': page['render_path'], 'required': visual_required,
                  'status': 'verified' if verified else ('pending' if visual_required else 'not_required'),
                  'structured': redact_content(note.get('structured')) if verified else None,
                  'reviewer': note.get('reviewer') if verified else None,
                  'evidence': note.get('evidence') if verified else None,
                  'source_sha256': page['document_sha256'], 'render_sha256': page['render_sha256']}
        text = '\n\n'.join(('```cpp\n'+b['text']+'\n```') if b['type'] == 'code' else b['text'] for b in blocks)
        text = normalize(text, code=True)
        if not text.strip() and not verified:
            flags.append('no_text_pending_OCR_or_vision')
        flags = sorted(set(flags))
        disposition = note.get('disposition', 'keep') if verified else 'keep'
        status = 'excluded_non_content' if disposition == 'non_content' else ('needs_review' if flags else 'accepted')
        if status == 'accepted' and not text.strip():
            status, flags = 'needs_review', ['empty_reviewed_transcript']
        row = {'schema_version': '1.0', 'id': page['id'], 'document_id': page['document_id'],
               'source': {'pdf_path': document['path'], 'document_sha256': page['document_sha256'],
                          'page': page['page'], 'original': page['original_source'],
                          'render_path': page['render_path'], 'render_sha256': page['render_sha256']},
               'page': page['page'], 'course': document['course'], 'course_code': document['course_code'],
               'text': text, 'blocks': blocks, 'removed_blocks': removed,
               'formulas': formulas, 'tables': tables, 'visual': visual, 'ignored_predictions': ignored_predictions,
               'quality': {'status': status, 'flags': flags,
                           'confidence': {'score': None, 'basis': 'no_calibrated_ground_truth'},
                           'pii_redactions': pii_events, 'ppstructure_processed': pp is not None,
                           'paddle_components_processed': components is not None,
                           'visual_verification_level': note.get('verification_level') if verified else None},
               'split': 'train', 'split_group': document['sha256']}
        if status == 'needs_review':
            review.append({'id': row['id'], 'page': row['page'], 'flags': flags,
                           'source': row['source'], 'native_text_preview': text[:1000],
                           'suggested_action': 'verify_source_then_supply_hash_bound_annotation'})
        for item in formulas:
            formula_rows.append({'page': row['page'], 'source': row['source'], **item})
        for item in tables:
            table_rows.append({'page': row['page'], 'source': row['source'], **item})
        visuals.append(visual)
        statuses[status] += 1
        flag_counts.update(flags)
        normalized.append(row)
    # Only eligible text can cause removal from training. Pending diagrams with
    # identical labels cannot suppress a reviewed slide with different edges.
    accepted = [r for r in normalized if r['quality']['status'] == 'accepted']
    edges = find_duplicates(accepted)
    unique = [r for r in accepted if r['duplicate_of'] is None]
    metadata = [{k: r[k] for k in ('id','document_id','source','page','course','course_code','text','quality','split','split_group','exact_hash','simhash64')} for r in unique]
    write_jsonl(out/'normalized.jsonl', normalized)
    write_jsonl(out/'review_queue.jsonl', review)
    write_jsonl(out/'formulas.jsonl', formula_rows)
    write_jsonl(out/'tables.jsonl', table_rows)
    write_jsonl(out/'visuals.jsonl', visuals)
    write_jsonl(out/'cpt/train.metadata.jsonl', metadata)
    write_jsonl(out/'cpt/train.jsonl', ({'text': r['text']} for r in unique))
    write_jsonl(out/'cpt/validation.jsonl', [])
    write_jsonl(out/'cpt/test.jsonl', [])
    dump_json(out/'deduplication.json', {'near_duplicate_policy': 'cluster_only_no_content_deletion',
              'minhash_seed': 42, 'num_perm': 128, 'edges': edges,
              'exact_duplicates': [{'id': r['id'], 'duplicate_of': r['duplicate_of']} for r in accepted if r['duplicate_of']]})
    dump_json(out/'split_manifest.json', {'policy': 'document_group_train_only', 'document_groups': {document['sha256']: 'train'},
              'reason': 'Only one merged course PDF; its two versions can overlap. No independent held-out document.',
              'train_pages': [r['page'] for r in unique], 'validation_pages': [], 'test_pages': []})
    # Metrics needing a reference transcript or annotated facts are explicitly unmeasured.
    reference = lambda reason: {'value': None, 'status': 'not_measured', 'reason': reason}
    report = {'document': document['path'], 'source_sha256': document['sha256'], 'pages_total': len(pages),
              'status_counts': dict(statuses), 'flag_counts': dict(flag_counts), 'accepted_before_dedup': len(accepted),
              'cpt_samples': len(unique), 'cpt_characters': sum(len(r['text']) for r in unique),
              'exact_duplicates_removed': len(accepted)-len(unique), 'near_duplicate_pairs': len(edges),
              'ppstructure_pages': sum(r['quality']['ppstructure_processed'] for r in normalized),
              'paddle_component_pages': sum(r['quality']['paddle_components_processed'] for r in normalized),
              'reviewed_source_pages': sum(r['visual']['status'] == 'verified' for r in normalized),
              'formula_records': len(formula_rows), 'table_records': len(table_rows),
              'visual_pending': sum(r['status'] == 'pending' for r in visuals), 'rejected_annotations': rejected_notes,
              'metrics': {'CER': reference('Needs manually transcribed ground-truth text.'),
                          'WER': reference('Needs manually transcribed ground-truth text.'),
                          'Formula Accuracy': reference('Needs independently verified formula inventory.'),
                          'Diagram Fact Precision': reference('Needs independently labeled facts and a fact inventory.'),
                          'Information Coverage': reference('Needs a reference inventory of important information.'),
                          'Duplicate Rate': {'value': (len(accepted)-len(unique))/max(1,len(accepted)),
                                             'scope': 'exact eligible page text; near duplicates reported separately'},
                          'Source Traceability': {'value': sum(bool(r['source']['original']) for r in normalized)/max(1,len(normalized)),
                                                 'scope': 'all normalized pages with upstream page mapping'}},
              'limitations': ['Native geometric layout is heuristic; formulas and visuals require verification.',
                             'PII detection covers emails and labeled phones/identifiers; it is not exhaustive.',
                             'Single-course training-only pilot cannot estimate generalization.']}
    dump_json(out/'quality_report.json', report)
    print(json.dumps({k: report[k] for k in ['pages_total','status_counts','cpt_samples','cpt_characters','ppstructure_pages','visual_pending']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--annotations', type=Path)
    a = p.parse_args()
    build(a.out, a.annotations)
