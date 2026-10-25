"""Structural checks only: passing these never establishes semantic accuracy."""
import json
import math
import re
import collections
from html.parser import HTMLParser


def parse_json_output(raw):
    value=raw.strip();recovered=False
    if value.startswith('```'):
        match=re.fullmatch(r'```(?:json)?\s*\n(.*?)\n```\s*',value,re.S|re.I)
        if not match:raise ValueError('Incomplete Markdown JSON wrapper')
        value=match.group(1);recovered=True
    def nonfinite(value):raise ValueError('Non-JSON constant '+value)
    parsed=json.loads(value,parse_constant=nonfinite)
    if not isinstance(parsed,dict):raise ValueError('Object required')
    return parsed,recovered


class TableShape(HTMLParser):
    def __init__(self):super().__init__();self.rows=[];self.current=None;self.has_table=False
    def handle_starttag(self,tag,attrs):
        if tag=='table':self.has_table=True
        if tag=='tr':self.current=[];self.rows.append(self.current)
        if tag in ['td','th'] and self.current is not None:self.current.append(dict(attrs))


def validate_prediction(engine,prediction):
    if not isinstance(prediction,dict):return ['prediction_not_object']
    errors=[]
    if engine=='formula':
        latex=prediction.get('latex')
        if not isinstance(latex,str) or not latex.strip():return ['empty_latex']
        depth=0
        for token in re.findall(r'(?<!\\)[{}]',latex):
            depth+=1 if token=='{' else -1
            if depth<0:break
        if depth!=0:errors.append('unbalanced_latex_braces')
        tokens=re.findall(r'\\[A-Za-z]+|\S',latex)
        counts=collections.Counter(tokens)
        if len(latex)>8000:errors.append('excessive_latex_length')
        if len(tokens)>60 and max(counts.values(),default=0)/len(tokens)>.45:
            errors.append('repetitive_latex_tokens')
        if re.search(r'(.{2,40}?)\1{7,}',latex):errors.append('repeated_latex_sequence')
        if '\ufffd' in latex or any(ord(c)<32 and c not in '\n\r\t' for c in latex):
            errors.append('corrupt_latex_characters')
        environments=[]
        for kind,name in re.findall(r'\\(begin|end)\{([^}]+)\}',latex):
            if kind=='begin':environments.append(name)
            elif not environments or environments.pop()!=name:
                errors.append('unbalanced_latex_environments');break
        if environments:errors.append('unbalanced_latex_environments')
    elif engine=='table':
        html=prediction.get('html')
        if not isinstance(html,str) or not html.strip():return ['empty_table_html']
        parser=TableShape()
        try:parser.feed(html)
        except Exception:return ['invalid_table_html']
        if not parser.has_table or not parser.rows or not any(parser.rows):errors.append('table_cells_missing')
    elif engine=='vlm':
        required={'image_type','nodes','edges','observed_facts','uncertain'}
        if set(prediction)!=required:errors.append('root_fields')
        if prediction.get('image_type') not in ['diagram','graph','chart','illustration','unknown']:errors.append('unknown_image_type')
        nodes=prediction.get('nodes');edges=prediction.get('edges')
        if not isinstance(nodes,list) or not isinstance(edges,list):return errors+['nodes_edges_not_lists']
        ids=[]
        for node in nodes:
            if not isinstance(node,dict) or set(node)!={'id','label'} or not all(isinstance(node.get(k),str) and node[k].strip() for k in ['id','label']):errors.append('invalid_node')
            else:ids.append(node['id'])
        if len(set(ids))!=len(ids):errors.append('duplicate_node_ids')
        # Empty arrays are legal JSON/schema; completeness is a separate quality gate.
        for edge in edges:
            if not isinstance(edge,dict) or set(edge)!={'source','target','directed','weight','highlighted'}:errors.append('edge_fields');continue
            if not isinstance(edge['source'],str) or not isinstance(edge['target'],str) or edge['source'] not in ids or edge['target'] not in ids:errors.append('dangling_edge_reference')
            if edge['directed'] is not None and type(edge['directed']) is not bool:errors.append('invalid_direction')
            if edge['highlighted'] is not None and type(edge['highlighted']) is not bool:errors.append('invalid_highlight')
            if edge['weight'] is not None and (type(edge['weight']) not in [str,int,float]):errors.append('invalid_weight')
            if isinstance(edge['weight'],float) and not math.isfinite(edge['weight']):errors.append('nonfinite_weight')
        for key in ['observed_facts','uncertain']:
            if not isinstance(prediction.get(key),list) or not all(isinstance(x,str) for x in prediction[key]):errors.append('invalid_'+key)
    else:errors.append('unknown_engine')
    return sorted(set(errors))


def semantic_warnings(prediction):
    """Flags for review, never a claim of correctness or automatic verification."""
    warnings=[]
    if prediction.get('image_type') in ['graph','diagram'] and not prediction.get('nodes'):
        warnings.append('diagram_nodes_missing')
    labels=[n.get('label') for n in prediction.get('nodes',[]) if isinstance(n,dict)]
    if len(set(labels))!=len(labels):warnings.append('duplicate_visible_labels_require_review')
    if prediction.get('edges') and all(e.get('directed') is None for e in prediction['edges'] if isinstance(e,dict)):
        warnings.append('all_edge_directions_unknown')
    if prediction.get('image_type')=='unknown':warnings.append('unclassified_image')
    return warnings


def cache_is_valid(record,request):
    return (isinstance(record,dict) and record.get('cache_key')==request['cache_key'] and
            record.get('engine')==request['engine'] and record.get('status')=='ok' and
            not validate_prediction(request['engine'],record.get('prediction')))
