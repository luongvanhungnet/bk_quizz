"""Read a single source PDF. No LLM rewriting, no source PDF mutation."""
from __future__ import annotations

import argparse
import collections
import json
import re
import statistics
from pathlib import Path

import pymupdf as fitz

from common import area, box_union, digest, dump_json, normalize, write_jsonl


CODE = re.compile(r'(?:\b(?:void|int|bool|double|return|scanf|printf|cout|cin|include)\b|\bfor\s*\(|\bif\s*\(|\+\+|&&|->|\[\w+\]\s*=)')
MATH_FONT = re.compile(r'(?:CM(?:MI|SY|EX)|Math|Symbol|CMSY|CMMI)', re.I)


def line_text(line: dict, code: bool) -> tuple[str, list[dict]]:
    """Recover spaces absent from ToUnicode text using physical character gaps.

    Scripts retain their baseline and font metadata; explicit PDF superscript
    flags become ^{...}. No guessed formula expansion or spelling correction.
    """
    pieces, runs, prev = [], [], None
    for span in line['spans']:
        is_super = bool(span['flags'] & 1)
        run = ''
        for ch in span['chars']:
            c = ch['c']
            # Verified against the rendered source (e.g. page 869). Other PUA
            # glyphs are kept and quarantined; never delete unknown math symbols.
            if span['font'] == 'Wingdings2' and c == '\uf097':
                c = '•'
            if prev and not prev['c'].isspace() and not c.isspace():
                gap = ch['bbox'][0] - prev['bbox'][2]
                if gap > max(0.45, span['size'] * (0.22 if code else 0.18)):
                    run += ' '
            run += c
            prev = ch
        if is_super and run.strip() and not code:
            # Treat a contiguous superscript run as one script, not ordinary digits.
            run = '^{' + run.strip() + '}'
        pieces.append(run)
        runs.append({'text': ''.join(c['c'] for c in span['chars']), 'font': span['font'],
                     'font_size': round(span['size'], 3), 'flags': span['flags'],
                     'origin': list(span['origin']), 'bbox': list(span['bbox']),
                     'superscript': is_super, 'math_font': bool(MATH_FONT.search(span['font']))})
    return normalize(''.join(pieces), code), runs


def reading_order(blocks: list[dict]) -> list[dict]:
    """Recursive whitespace cuts, with full-width headings splitting columns."""
    if len(blocks) < 2:
        return blocks
    box = box_union(b['bbox'] for b in blocks)
    font = statistics.median(b['font_size'] for b in blocks)
    # Horizontal cuts at genuine paragraph/section whitespace first.
    # Prefer a vertical column gutter when one exists. A full-width heading
    # prevents that cut until it has first been separated by a horizontal cut.
    for axis, threshold in [(0, font * 2.5), (1, font * 1.8)]:
        ordered = sorted(blocks, key=lambda b: b['bbox'][axis])
        edge = ordered[0]['bbox'][axis+2]
        cuts = []
        for i, b in enumerate(ordered[1:], 1):
            gap = b['bbox'][axis] - edge
            if gap > threshold:
                cuts.append((gap, i))
            edge = max(edge, b['bbox'][axis+2])
        if cuts:
            _, i = max(cuts)
            return reading_order(ordered[:i]) + reading_order(ordered[i:])
    return sorted(blocks, key=lambda b: (round(b['bbox'][1]/max(font*0.4, 1)), b['bbox'][0]))


def native_blocks(page) -> list[dict]:
    raw = page.get_text('rawdict', flags=fitz.TEXTFLAGS_RAWDICT & ~fitz.TEXT_PRESERVE_IMAGES)
    result = []
    for b in raw['blocks']:
        if b['type'] != 0:
            continue
        original = '\n'.join(''.join(c['c'] for s in l['spans'] for c in s['chars']) for l in b['lines'])
        mono = any('Courier' in s['font'] or 'Consolas' in s['font'] or s['flags'] & 8 for l in b['lines'] for s in l['spans'])
        code = mono or len(CODE.findall(original)) >= 2
        lines, spans = [], []
        for line in b['lines']:
            text, runs = line_text(line, code)
            lines.append({'text': text, 'bbox': list(line['bbox']), 'spans': runs})
            spans.extend(runs)
        # Restore indentation from x coordinates for code, retain line boundaries.
        if code and lines:
            left = min(l['bbox'][0] for l in lines)
            unit = max(1, statistics.median(s['font_size'] for s in spans) * 0.6)
            text = '\n'.join(' ' * min(80, round((l['bbox'][0]-left)/unit)) + l['text'] for l in lines)
        else:
            text = ''
            for line in lines:
                value = line['text']
                join = bool(text and value and value[0].islower() and not re.search(r'[.!?:;]$', text) and
                            abs(line['bbox'][0] - lines[0]['bbox'][0]) < 8 and not re.match(r'^[•●▪◦\-]|^\d+[.)]', value))
                text += (' ' if join else '\n') + value
            text = text.strip()
        if not text:
            continue
        math = any(s['math_font'] or s['superscript'] for s in spans)
        result.append({'id': f'b{len(result):04d}', 'type': 'code' if code else 'text',
                       'bbox': list(b['bbox']), 'text': normalize(text, code), 'original_text': original,
                       'font_size': statistics.median(s['font_size'] for s in spans), 'lines': lines,
                       'math_candidate': math, 'extraction_method': 'native_pdf_char_geometry',
                       'confidence': {'score': None, 'basis': 'native_pdf_not_an_OCR_probability'}})
    ordered = reading_order(result)
    merged = []
    for b in ordered:
        if merged and b['type'] == 'code' and merged[-1]['type'] == 'code' and (
                b['bbox'][1] - merged[-1]['bbox'][3] < b['font_size']*1.5 and
                b['bbox'][1] >= merged[-1]['bbox'][1]):
            prev = merged[-1]
            prev['bbox'] = box_union([prev['bbox'], b['bbox']])
            prev['lines'].extend(b['lines'])
            prev['original_text'] += '\n' + b['original_text']
            prev.setdefault('merged_ids', [prev['id']]).append(b['id'])
            left = min(l['bbox'][0] for l in prev['lines'])
            unit = max(1, prev['font_size']*.6)
            prev['text'] = '\n'.join(' '*min(80,round((l['bbox'][0]-left)/unit)) + l['text'] for l in prev['lines'])
        else:
            merged.append(b)
    return merged


def part_map(pdf: Path, manifest_path: Path | None) -> tuple[dict, dict]:
    if not manifest_path or not manifest_path.exists():
        return {}, {}
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    source = next((r for r in manifest if r.get('filename') == pdf.name), {})
    mapping = {}
    for p in source.get('parts', []):
        for n, orig in enumerate(p['pages_selected'], p['output_start']):
            mapping[n] = {'source_id': p['file_id'], 'source_path': p['path'],
                          'source_sha256': p['source_sha256'], 'source_page': orig,
                          'source_member': p['member'], 'source_archive': p['source']}
    return source, mapping


def extract(pdf: Path, out: Path, manifest_path: Path | None, width: int = 1400):
    if not pdf.name.startswith('IT3170-'):
        raise ValueError('This single-course pilot expects IT3170; configure course metadata before processing another course.')
    out.mkdir(parents=True, exist_ok=True)
    sha = digest(pdf.read_bytes())
    source, mapping = part_map(pdf, manifest_path)
    if source and source['sha256'] != sha:
        raise ValueError('Source SHA-256 differs from upstream manifest')
    document = {'id': 'IT3170-' + sha[:16], 'course': 'Thuật toán ứng dụng', 'course_code': 'IT3170',
                'course_code_evidence': source.get('confidence', 'filename_only'),
                'path': str(pdf.resolve()), 'sha256': sha, 'bytes': pdf.stat().st_size,
                'upstream_manifest': str(manifest_path) if manifest_path else None,
                'upstream_manifest_sha256': digest(manifest_path.read_bytes()) if manifest_path and manifest_path.exists() else None,
                'parts': source.get('parts', []), 'author_note': source.get('note'), 'schema_version': '1.0'}
    doc = fitz.open(pdf)
    document['pages'] = len(doc)
    dump_json(out/'document.json', document)
    pages = []
    for idx, page in enumerate(doc):
        n = idx+1
        cache = out/'raw'/f'page_{n:04d}.json'
        render = out/'assets'/f'page_{n:04d}.png'
        if cache.exists():
            record = json.loads(cache.read_text(encoding='utf-8'))
            if record.get('extractor_version') == 4:
                # PyMuPDF's embedded-image fingerprint is MD5; document/render
                # integrity is separately protected with real SHA-256 hashes.
                for im in record['images']:
                    im['md5'] = im.pop('sha256')
                record['extractor_version'] = 5
                dump_json(cache, record)
            if record.get('extractor_version') == 5 and record.get('document_sha256') == sha and record.get('render_width') == width and render.exists():
                pages.append(record)
                continue
        blocks = native_blocks(page)
        drawings = page.get_drawings()
        # Exclude margins, title separators, and tiny bullet glyphs; preserve diagrams.
        body = [d for d in drawings if d['rect'].y0 > page.rect.height*.16 and d['rect'].y1 < page.rect.height*.9
                and d['rect'].width > page.rect.width*.02 and d['rect'].height > page.rect.height*.015
                and d['rect'].width < page.rect.width*.93]
        images = []
        for info in page.get_image_info(hashes=True):
            images.append({'bbox': list(info['bbox']), 'md5': info['digest'].hex(),
                           'width': info['width'], 'height': info['height'],
                           'area_fraction': area(info['bbox'])/area(list(page.rect))})
        render.parent.mkdir(parents=True, exist_ok=True)
        old = json.loads(cache.read_text(encoding='utf-8')) if cache.exists() else {}
        if not (render.exists() and old.get('document_sha256') == sha and old.get('render_width') == width):
            page.get_pixmap(matrix=fitz.Matrix(width/page.rect.width, width/page.rect.width), alpha=False).save(render)
        record = {'schema_version': '1.0', 'extractor_version': 5, 'id': f'{document["id"]}:p{n:04d}', 'document_id': document['id'],
                  'document_sha256': sha, 'page': n, 'page_size_pt': [page.rect.width, page.rect.height],
                  'coordinate_system': 'PDF_points_top_left', 'render_width': width,
                  'render_path': render.relative_to(out).as_posix(), 'render_sha256': digest(render.read_bytes()),
                  'original_source': mapping.get(n), 'blocks': blocks, 'images': images,
                  'vector_regions': [{'bbox': list(d['rect']), 'primitive_count': len(d['items'])} for d in body],
                  'native_text_chars': sum(len(b['text']) for b in blocks)}
        dump_json(cache, record)
        pages.append(record)
        if n%50 == 0:
            print(f'extracted {n}/{len(doc)}', flush=True)
    # Repeated embedded backgrounds are identified globally, never by sparse text.
    counts = collections.Counter(im['md5'] for p in pages for im in {i['md5']: i for i in p['images']}.values())
    for p in pages:
        for im in p['images']:
            im['document_frequency'] = counts[im['md5']]
            h = p['page_size_pt'][1]
            margin = im['bbox'][1] > h*.88 or im['bbox'][3] < h*.14
            im['decorative_candidate'] = counts[im['md5']] >= 10 and (margin or im['area_fraction'] > .9)
    write_jsonl(out/'native_pages.jsonl', pages)
    print(f'Finished {len(pages)} pages -> {out}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pdf', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--width', type=int, default=1400)
    args = parser.parse_args()
    extract(args.pdf, args.out, args.manifest, args.width)
