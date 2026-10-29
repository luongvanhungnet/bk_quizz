"""Bound region expansion without dropping unknown small mathematical content."""
from collections import defaultdict
import hashlib
from io import BytesIO
import json
from pathlib import Path

from common import atomic_json
from telemetry import event

VERSION = '6.0.0'
MAX_REGIONS_PER_PAGE = 200
MAX_REQUESTS_PER_BATCH = 256
MAX_BATCH_ASSET_BYTES = 64 * 1024**2
MAX_LAYOUT_REGIONS_PER_PAGE = 200
# RGB pixels inspected against full slide renders of IT4906 pages 3/217/227.
# Size alone NEVER establishes decoration. Limit this approval to the source PDF.
APPROVED_TILES = {('3a91e242e0ad7c283fe4b4a2722036a02403ea6aca4393bb07ac62d7b1613d28',
                  '8af36483ba4adb07fad048515790800ceab2c28d979e487d65de9e64a7318501')}


def proposals(page, source_sha, run, number):
    """Enumerate each displayed occurrence once, auditing approved repeated tiles."""
    from PIL import Image
    groups = defaultdict(list)
    for info in page.get_image_info(xrefs=True):
        groups[info.get('xref', 0)].append(info)
    kept = []; suppressed = 0; audits = []
    for xref, items in groups.items():
        approved = False; pixel_hash = None
        first = items[0]
        if xref and len(items) >= 500 and first['width'] <= 4 and first['height'] <= 16:
            with Image.open(BytesIO(page.parent.extract_image(xref)['image'])) as im:
                pixel_hash = hashlib.sha256(im.convert('RGB').tobytes()).hexdigest()
            extent = [min(i['bbox'][0] for i in items), min(i['bbox'][1] for i in items),
                      max(i['bbox'][2] for i in items), max(i['bbox'][3] for i in items)]
            approved = ((source_sha, pixel_hash) in APPROVED_TILES
                        and (extent[2]-extent[0]) >= .8*page.rect.width
                        and (extent[3]-extent[1]) >= .8*page.rect.height)
        if approved:
            suppressed += len(items)
            audits.append({'source_sha256':source_sha, 'page':number, 'xref':xref,
                           'pixel_sha256':pixel_hash, 'size':[first['width'], first['height']],
                           'occurrences':len(items), 'decision':'exclude_verified_background_from_model_tasks',
                           'evidence':'visually_inspected_IT4906_striped_background_and_exact_RGB_hash',
                           'bbox_units':'pdf_points', 'bboxes':[list(i['bbox']) for i in items],
                           'full_slide_retained':True, 'semantic_verified':False})
        else:
            kept.extend(items)
    overloaded = len(kept) > MAX_REGIONS_PER_PAGE
    audit = {'policy_version':VERSION, 'page':number, 'source_sha256':source_sha,
             'displayed_occurrences':sum(len(v) for v in groups.values()),
             'suppressed_background_occurrences':suppressed, 'remaining_occurrences':len(kept),
             'full_page_layout_fallback':overloaded, 'review_required':overloaded,
             'reason':'region_limit_exceeded_preserve_full_page' if overloaded else None,
             'groups':audits}
    if overloaded:
        audit['deferred_proposals']=[{'xref':i.get('xref'), 'bbox':list(i['bbox']),
                                     'size':[i['width'],i['height']]} for i in kept]
    atomic_json(Path(run)/'region_audit'/f'page_{number:04d}.json', audit)
    event('region_inventory', page=number, occurrences=audit['displayed_occurrences'],
          suppressed=suppressed, kept=0 if overloaded else len(kept), review_required=overloaded)
    return ([] if overloaded else kept), audit


def limit_candidates(candidates, run):
    """Retain an audit of excess specialist regions; preserve page OCR/layout inputs."""
    groups=defaultdict(list)
    for c in candidates: groups[c['page']].append(c)
    accepted=[]
    for page, rows in groups.items():
        if len(rows)>MAX_LAYOUT_REGIONS_PER_PAGE:
            atomic_json(Path(run)/'region_audit'/f'layout_overflow_{page:04d}.json',
                        {'page':page,'reason':'layout_region_limit_exceeded','review_required':True,
                         'candidates':rows,'full_slide_retained':True,'semantic_verified':False})
        else: accepted.extend(rows)
    return accepted


def hold_overflow_pages(records,run):
    from common import load
    held=set()
    for path in (Path(run)/'region_audit').glob('layout_overflow_*.json'):
        held.add(load(path)['page'])
    for record in records:
        if record['page'] in held:
            record['region_overflow_review_required']=True;record['risk']='high'
