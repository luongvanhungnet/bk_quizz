"""Conservative native-geometry classification; uncertain material stays in review."""
import re


def area(b):return max(0,b[2]-b[0])*max(0,b[3]-b[1])


def intersection(a,b):
    return area([max(a[0],b[0]),max(a[1],b[1]),min(a[2],b[2]),min(a[3],b[3])])


def union(boxes):
    return [min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]


def is_prose(text):
    words=re.findall(r'[^\W\d_]+',text,flags=re.UNICODE)
    # Vietnamese words with diacritics are prose evidence, never stripped from native.
    return bool(re.search(r'[\u00c0-\u024f\u1e00-\u1eff]',text)) or sum(len(w)>2 and w.lower() not in ['log','sin','cos','tan','min','max','exp','lim'] for w in words)>=3


def table_geometry(lines):
    """At least 3 rows with 3+ aligned columns and repeated column starts."""
    rows={}
    for line in lines:
        y=round(line['bbox'][1]/5)
        rows.setdefault(y,[]).append(line['bbox'][0])
    starts=[sorted(xs) for xs in rows.values() if len(xs)>=3]
    if len(starts)<3:return False
    anchor=starts[0]
    return sum(sum(any(abs(x-a)<8 for x in xs) for a in anchor)>=3 for xs in starts)>=3


def classify_formula(region,page,tables):
    scale=page['render_width']/page['page_size_pt'][0]
    clip=region['bbox_pixels']
    for table in tables:
        box=table['bbox_pixels']
        if intersection(clip,box)/max(1,area(clip))>=.6:
            return {'decision':'table_existing','table_id':table['id'],'reason':'formula_overlaps_table','formula_boxes':[]}
    lines=[]
    for block in page['blocks']:
        for line in block.get('lines',[]):
            box=[v*scale for v in line['bbox']]
            if intersection(clip,box)/max(1,area(box))>=.7:
                lines.append({**line,'bbox':box,'block_type':block['type']})
    if table_geometry(lines):
        return {'decision':'table_candidate','reason':'aligned_native_rows_and_columns','formula_boxes':[]}
    if any(l['block_type']=='code' for l in lines):
        return {'decision':'native_review','reason':'native_code_or_unresolved_tabular_block','formula_boxes':[]}
    boxes=[]
    for line in lines:
        text=line['text'].strip()
        if not is_prose(text) and re.search(r'[=<>≤≥≈∑∏√∞^_+×÷]|\blog\b|O\s*\(',text):
            content=[s for s in line.get('spans',[]) if s.get('text','').strip() and s['text'].strip() not in ['▶','►','▸','•','‣','▹','▷']]
            boxes.append(union([[v*scale for v in s['bbox']] for s in content]) if content else line['bbox']);continue
        # Mixed prose: retain the original native paragraph, crop only runs
        # containing mathematical-font/superscript spans and nearby math tokens.
        spans=line.get('spans',[]);groups=[];current=[];has_math=False
        for span in spans:
            t=span.get('text','').strip()
            prose_token=bool(re.search(r'[\u00c0-\u024f\u1e00-\u1eff]',t))
            math=bool(span.get('math_font') or span.get('superscript')) and not prose_token
            allowed=math or bool(t and re.fullmatch(r'[A-Za-z0-9\s.,()\[\]{}=<>≤≥≈∑∏√∞^_+*/×÷−–-]+',t) and len(t)<=12)
            if not t:continue
            if allowed:
                current.append([v*scale for v in span['bbox']]);has_math|=math
            else:
                if current and has_math:groups.append(current)
                current=[];has_math=False
        if current and has_math:groups.append(current)
        boxes.extend(union(group) for group in groups)
    if boxes:
        # Deduplicate nested candidates, without deleting small indices/symbols.
        selected=[]
        for box in sorted(boxes,key=area,reverse=True):
            if not any(intersection(box,b)/max(1,area(box))>.95 for b in selected):selected.append(box)
        return {'decision':'formula_crops','reason':'native_math_runs_only','formula_boxes':selected,
                'native_text_preserved':True,'semantic_verified':False}
    return {'decision':'native_review' if lines else 'visual_review',
            'reason':'no_isolated_formula_evidence','formula_boxes':[],
            'native_text_preserved':True,'semantic_verified':False}
