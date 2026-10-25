"""Review gates: source evidence and consistency, never automatic semantic approval."""
from collections import Counter
from html.parser import HTMLParser
import math
import re
import unicodedata
from validation import bbox


def canonical(text):return re.sub(r'\s+',' ',unicodedata.normalize('NFC',text)).strip()
def intersects(a,b):return bbox(a) and bbox(b) and min(a[2],b[2])>max(a[0],b[0]) and min(a[3],b[3])>max(a[1],b[1])


def style_distance(path,subject,reference):
    from PIL import Image
    import numpy as np
    image=Image.open(path).convert('RGB');signatures=[]
    for box in [subject,reference]:
        coords=[int(box[i]*image.size[i%2]/1000) for i in range(4)]
        data=np.asarray(image.crop(coords)).reshape(-1,3)
        foreground=data[np.min(data,axis=1)<210]
        if len(foreground)<4:return None
        signatures.append(np.median(foreground,axis=0))
    return float(np.linalg.norm(signatures[0]-signatures[1]))


def graph_issues(p,context):
    flags=[];nodes=p.get('nodes',[]);edges=p.get('edges',[])
    if not nodes:flags.append('empty_graph_requires_review')
    labels=[n['label'] for n in nodes]
    if len(set(labels))!=len(labels):flags.append('duplicate_visible_labels')
    by_id={n['id']:n for n in nodes};seen={}
    for e in edges:
        a=e['attributes'];pair=tuple(sorted([e['source'],e['target']]))
        if pair in seen:
            flags.append('repeated_endpoint_pair')
            old=seen[pair]
            if old['attributes']['weight']!=a['weight']:flags.append('contradictory_weights_same_pair')
            if (old['source'],old['target'])==(e['target'],e['source']):flags.append('reciprocal_edges_require_source_check')
        seen[pair]=e
        if a['directed'] is True:
            if a.get('arrow_target')!=e['target']:flags.append('arrow_target_mismatch')
            if a['direction_basis']!='arrowhead' or not bbox(a['arrow_bbox']):flags.append('directed_without_arrow_evidence')
            elif not intersects(a['arrow_bbox'],e['bbox']):flags.append('arrow_outside_edge')
            elif e['target'] in by_id:
                target=by_id[e['target']]['bbox'];arrow=a['arrow_bbox']
                cx=(arrow[0]+arrow[2])/2;cy=(arrow[1]+arrow[3])/2
                tx=(target[0]+target[2])/2;ty=(target[1]+target[3])/2
                if math.hypot(cx-tx,cy-ty)>150:flags.append('arrow_not_near_target')
        elif a['directed'] is False:
            quote=canonical(a['native_quote'])
            if (a['direction_basis']!='explicit_undirected_caption' or not quote or
                quote.casefold() not in canonical(context.get('native_text','')).casefold() or
                not re.search(r'vô hướng|undirected',quote,re.I)):
                flags.append('undirected_without_native_caption_evidence')
        else:flags.append('direction_unresolved')
        if a['weight'] is not None:
            if not bbox(a['weight_bbox']) or not intersects(a['weight_bbox'],e['bbox']):flags.append('weight_without_local_evidence')
        if a['highlighted'] is not None:
            if not bbox(a['highlight_bbox']) or not bbox(a['reference_bbox']):flags.append('highlight_without_style_comparison')
            elif a['highlight_bbox']==a['reference_bbox']:flags.append('highlight_reference_equals_subject')
            elif context.get('_image_path'):
                delta=style_distance(context['_image_path'],a['highlight_bbox'],a['reference_bbox'])
                if delta is None:flags.append('insufficient_style_pixels')
                elif a['highlighted'] is True and delta<20:flags.append('highlight_style_not_distinct')
                elif a['highlighted'] is False and delta>=20:flags.append('regular_style_differs_from_reference')
        else:flags.append('highlight_unresolved')
    if edges and all(e['attributes']['highlighted'] is True for e in edges):flags.append('all_edges_highlighted_requires_review')
    if edges and all(e['attributes']['directed'] is True for e in edges) and any(
        e['attributes']['direction_basis']!='arrowhead' or not bbox(e['attributes']['arrow_bbox']) for e in edges):
        flags.append('all_edges_directed_without_complete_arrow_evidence')
    quote=context.get('native_text','')
    if re.search(r'vô hướng|undirected',quote,re.I) and any(e['attributes']['directed'] is True for e in edges):
        flags.append('native_caption_direction_contradiction')
    native=context.get('native_graph_candidates',{});native_nodes={n['id']:n for n in native.get('nodes',[])}
    predicted_pairs={tuple(sorted([by_id[e['source']]['label'],by_id[e['target']]['label']])) for e in edges}
    for node in nodes:
        local=[n for n in native_nodes.values() if intersects(n['bbox'],node['bbox'])]
        if local and all(n.get('label')!=node['label'] for n in local):flags.append('native_node_label_disagreement')
    for edge in native.get('edges',[]):
        a=native_nodes[edge['source']].get('label');b=native_nodes[edge['target']].get('label')
        if a is None or b is None:continue
        pair=tuple(sorted([a,b]))
        if pair not in predicted_pairs:flags.append('native_connection_missing_from_prediction')
        weights={w['text'] for w in edge.get('weight_candidates',[])}
        if len(weights)==1:
            for e in edges:
                pred_pair=tuple(sorted([by_id[e['source']]['label'],by_id[e['target']]['label']]))
                if pred_pair==pair and e['attributes']['weight'] is not None:
                    try:
                        if float(e['attributes']['weight'])!=float(next(iter(weights))):flags.append('native_weight_disagreement')
                    except (ValueError,TypeError):flags.append('native_weight_disagreement')
    return sorted(set(flags))


def state_issues(p,context):
    states=p['states'];relations=p['relations'];flags=[]
    if not states:flags.append('no_board_states')
    parents=Counter(e['child'] for e in relations)
    if any(n>1 for n in parents.values()):flags.append('state_has_multiple_parents')
    ids={s['id'] for s in states};children={i:[] for i in ids}
    for e in relations:children[e['parent']].append(e['child'])
    visiting=set();done=set()
    def visit(node):
        if node in visiting:return True
        if node in done:return False
        visiting.add(node)
        if any(visit(child) for child in children[node]):return True
        visiting.remove(node);done.add(node);return False
    if any(visit(i) for i in ids if i not in done):flags.append('cycle_in_state_tree')
    roots=ids-set(parents)
    if len(roots)!=context.get('expected_tree_roots',1):flags.append('unexpected_tree_root_count')
    by_id={s['id']:s for s in states}
    for e in relations:
        parent={tuple(c) for c in by_id[e['parent']]['queens']};child={tuple(c) for c in by_id[e['child']]['queens']}
        if not parent<=child or len(child-parent)!=1:flags.append('queen_transition_requires_review')
    candidates=context.get('board_candidates',[])
    if candidates and len(states)!=len(candidates):flags.append('board_count_differs_from_cv_proposal')
    if p.get('uncertain'):flags.append('model_uncertainty')
    # Geometry/color candidates are not verified ground truth.
    return sorted(set(flags))


def delimiter_warnings(latex):
    stack=[]
    for token in re.findall(r'(?<!\\)[()\[\]]',latex):
        if token in '([':stack.append(token)
        elif not stack:return ['unmatched_delimiter_requires_context']
        else:stack.pop() # Mixed (a,b] intervals remain legal; do not rewrite.
    return ['unmatched_delimiter_requires_context'] if stack else []


def formula_issues(prediction,context):
    latex=prediction.get('latex','');flags=delimiter_warnings(latex)
    if re.match(r'^\s*(?:[<>≤≥=]|\\(?:leq|geq|approx))',latex):flags.append('relation_fragment_requires_native_context')
    if re.search(r'\^\{\s*\\(?:cdot|bullet)\s*\}',latex):flags.append('possible_punctuation_as_superscript')
    if not context.get('native_text'):flags.append('native_context_missing')
    if context.get('native_crop_text'):
        source_numbers=Counter(re.findall(r'\d+',context['native_crop_text']))
        recognized_numbers=Counter(re.findall(r'\d+',latex))
        if recognized_numbers-source_numbers:flags.append('numbers_not_supported_by_native_crop')
        if source_numbers-recognized_numbers:flags.append('native_numbers_missing_in_formula')
    return sorted(set(flags))


class GridParser(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.rows=[];self.cell=None;self.errors=[];self.depth=0
    def handle_starttag(self,tag,attrs):
        if tag=='table':self.depth+=1
        if tag=='tr':self.rows.append([])
        if tag in ['td','th']:
            if not self.rows or self.cell is not None:self.errors.append('invalid_cell_nesting')
            attrs=dict(attrs);spans=[]
            for key in ['rowspan','colspan']:
                try:v=int(attrs.get(key,1));assert 1<=v<=1000
                except (ValueError,AssertionError):self.errors.append('invalid_table_span');v=1
                spans.append(v)
            self.cell={'text':'','rowspan':spans[0],'colspan':spans[1]}
    def handle_data(self,data):
        if self.cell is not None:self.cell['text']+=data
    def handle_endtag(self,tag):
        if tag in ['td','th'] and self.cell is not None:
            if self.rows:self.rows[-1].append(self.cell)
            self.cell=None
        if tag=='table':self.depth-=1


def table_issues(prediction,context):
    parser=GridParser();parser.feed(prediction.get('html',''));flags=list(parser.errors)
    if parser.cell is not None or parser.depth!=0:flags.append('unclosed_table_or_cell')
    occupied={};widths=[]
    for row,cells in enumerate(parser.rows):
        col=0
        for cell in cells:
            while (row,col) in occupied:col+=1
            if cell['rowspan']*cell['colspan']>10000 or len(occupied)>20000:
                flags.append('table_grid_too_large_requires_review');continue
            for dy in range(cell['rowspan']):
                for dx in range(cell['colspan']):
                    key=(row+dy,col+dx)
                    if key in occupied:flags.append('overlapping_table_spans')
                    occupied[key]=True
            col+=cell['colspan']
        widths.append(max([c+1 for r,c in occupied if r==row],default=0))
    if len(set(widths))>1:flags.append('inconsistent_table_columns')
    if any(row>=len(parser.rows) for row,col in occupied):flags.append('rowspan_exceeds_table')
    source=' '.join(v['text'] for v in context.get('native_ocr',[]))
    hyp=' '.join(c['text'] for row in parser.rows for c in row)
    native_tokens=Counter(re.findall(r'\w+|[-−]?\d+(?:[.,]\d+)?',canonical(source)))
    html_tokens=Counter(re.findall(r'\w+|[-−]?\d+(?:[.,]\d+)?',canonical(hyp)))
    covered=sum((native_tokens & html_tokens).values());total=sum(native_tokens.values())
    if total and covered/total<.98:flags.append('native_table_text_not_fully_covered')
    # Compare signed numeric substrings separately; generic tokenization drops signs.
    numbers=lambda t:Counter(re.findall(r'(?<!\w)[-−]?\d+(?:[.,]\d+)?',t))
    if numbers(source)!=numbers(hyp):flags.append('table_numeric_inventory_mismatch')
    return sorted(set(flags)),{'native_token_coverage':covered/total if total else None,
                              'rows':len(parser.rows),'column_counts':widths}


def assess(engine,p,context):
    if engine=='formula':flags=formula_issues(p,context);metrics={}
    elif engine=='table':flags,metrics=table_issues(p,context)
    elif p.get('image_type')=='state_tree':flags=state_issues(p,context);metrics={}
    elif p.get('image_type') in ['graph','diagram','flowchart','unknown']:flags=graph_issues(p,context);metrics={}
    else:flags=['specialist_visual_review_required'];metrics={}
    if p.get('uncertain'):flags.append('model_uncertainty')
    flags=sorted(set(flags))
    return {'flags':flags,'metrics':metrics,'evidence_gate_pass':not flags,
            'semantic_verified':False,'destination':'review_queue',
            'note':'Passing heuristics or providing bboxes does not prove semantic correctness.'}
