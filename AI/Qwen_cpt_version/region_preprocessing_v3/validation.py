"""Schema contracts. Semantic evidence checks live in quality.py, never verify CPT."""
import math
import json
import re
from legacy_validation import validate_prediction as legacy_validate


def parse_json_output(raw):
    value=raw.strip();recovered=False
    if value.startswith('```'):
        match=re.fullmatch(r'```(?:json)?\s*\n(.*?)\n```\s*',value,re.S|re.I)
        if not match:raise ValueError('Incomplete JSON wrapper')
        value=match.group(1);recovered=True
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise ValueError('Duplicate JSON key: '+k)
            result[k]=v
        return result
    def constant(v):raise ValueError('Non-JSON constant '+v)
    parsed=json.loads(value,object_pairs_hook=pairs,parse_constant=constant)
    if not isinstance(parsed,dict):raise ValueError('JSON object required')
    return parsed,recovered


def bbox(value):
    return (isinstance(value,list) and len(value)==4 and all(type(v) in [int,float] and math.isfinite(v) for v in value)
            and 0<=value[0]<value[2]<=1000 and 0<=value[1]<value[3]<=1000)


def validate_stage(stage,p):
    if not isinstance(p,dict):return ['object_required']
    errors=[]
    key={'nodes':'nodes','edges':'edges','attributes':'attributes','state_tree':'states','chart':'axes','illustration':'facts'}[stage]
    extra={'state_tree':{'relations'},'chart':{'series'}}.get(stage,set())
    if set(p)!={key,'uncertain'}|extra:errors.append('stage_fields')
    if not isinstance(p.get('uncertain'),list) or not all(isinstance(x,str) for x in p.get('uncertain',[])):errors.append('uncertain_type')
    rows=p.get(key)
    if not isinstance(rows,list):return errors+['rows_type']
    ids=[]
    for r in rows:
        if not isinstance(r,dict):errors.append('row_object');continue
        if stage=='nodes':
            if set(r)!={'id','label','bbox'}:errors.append('node_fields')
            if not all(isinstance(r.get(k),str) and r[k].strip() for k in ['id','label']):errors.append('node_identity')
            else:ids.append(r['id'])
            if not bbox(r.get('bbox')):errors.append('node_bbox')
        elif stage=='edges':
            if set(r)!={'id','source','target','bbox'}:errors.append('edge_fields')
            if not all(isinstance(r.get(k),str) and r[k].strip() for k in ['id','source','target']):errors.append('edge_identity')
            else:ids.append(r['id'])
            if not bbox(r.get('bbox')):errors.append('edge_bbox')
        elif stage=='attributes':
            expected={'edge_id','directed','weight','highlighted','arrow_target','arrow_bbox','weight_bbox','highlight_bbox','reference_bbox','direction_basis','native_quote'}
            if set(r)!=expected:errors.append('attribute_fields')
            if not isinstance(r.get('edge_id'),str):errors.append('edge_id')
            else:ids.append(r['edge_id'])
            for k in ['directed','highlighted']:
                if r.get(k) is not None and type(r[k]) is not bool:errors.append(k+'_type')
            w=r.get('weight')
            if w is not None and (type(w) not in [int,float,str] or isinstance(w,float) and not math.isfinite(w)):errors.append('weight_type')
            for k in ['arrow_bbox','weight_bbox','highlight_bbox','reference_bbox']:
                if r.get(k) is not None and not bbox(r[k]):errors.append(k)
            if r.get('direction_basis') not in ['arrowhead','explicit_undirected_caption','unknown']:errors.append('direction_basis')
            if not isinstance(r.get('native_quote'),str):errors.append('native_quote')
            if r.get('arrow_target') is not None and not isinstance(r['arrow_target'],str):errors.append('arrow_target')
        elif stage=='state_tree':
            if set(r)!={'id','bbox','board_size','queens','removed_cells'}:errors.append('state_fields')
            if not isinstance(r.get('id'),str) or not r['id']:errors.append('state_id')
            else:ids.append(r['id'])
            if not bbox(r.get('bbox')):errors.append('state_bbox')
            n=r.get('board_size')
            if type(n) is not int or not 1<=n<=32:errors.append('board_size');continue
            for k in ['queens','removed_cells']:
                cells=r.get(k)
                if not isinstance(cells,list):errors.append(k);continue
                valid=[c for c in cells if isinstance(c,list) and len(c)==2 and all(type(v) is int and 0<=v<n for v in c)]
                if len(valid)!=len(cells):errors.append(k+'_coordinates')
                if len({tuple(c) for c in valid})!=len(valid):errors.append(k+'_duplicates')
            if isinstance(r.get('queens'),list) and isinstance(r.get('removed_cells'),list):
                if any(c in r['removed_cells'] for c in r['queens']):errors.append('queen_removed_overlap')
        elif stage=='chart':
            if set(r)!={'name','label','unit','bbox'} or r.get('name') not in ['x','y']:errors.append('axis_fields')
            if not bbox(r.get('bbox')):errors.append('axis_bbox')
        elif stage=='illustration':
            if set(r)!={'text','bbox'} or not isinstance(r.get('text'),str):errors.append('fact_fields')
            if not bbox(r.get('bbox')):errors.append('fact_bbox')
    if len(set(ids))!=len(ids):errors.append('duplicate_ids')
    if stage=='state_tree':
        relations=p.get('relations')
        if not isinstance(relations,list):errors.append('relations_type')
        else:
            for e in relations:
                if not isinstance(e,dict) or set(e)!={'parent','child','bbox'}:errors.append('relation_fields');continue
                if e['parent'] not in ids or e['child'] not in ids or e['parent']==e['child']:errors.append('relation_reference')
                if not bbox(e['bbox']):errors.append('relation_bbox')
    if stage=='chart':
        series=p.get('series')
        if not isinstance(series,list):errors.append('series_type')
        else:
            for s in series:
                if not isinstance(s,dict) or set(s)!={'name','points'} or not isinstance(s.get('points'),list):errors.append('series_fields');continue
                for pt in s['points']:
                    if not isinstance(pt,dict) or set(pt)!={'x','y','bbox'}:errors.append('point_fields');continue
                    if not bbox(pt.get('bbox')):errors.append('point_bbox')
                    if any(type(pt.get(k)) not in [str,int,float] or isinstance(pt.get(k),float) and not math.isfinite(pt[k]) for k in ['x','y']):errors.append('point_values')
    return sorted(set(errors))


def validate_prediction(engine,p):
    if engine in ['formula','table']:return legacy_validate(engine,p)
    if not isinstance(p,dict):return ['object_required']
    kind=p.get('image_type')
    if kind in ['state_tree','chart','illustration']:
        payload={k:v for k,v in p.items() if k!='image_type'}
        return validate_stage(kind,payload)
    if kind not in ['graph','diagram','flowchart','unknown']:return ['image_type']
    errors=validate_stage('nodes',{'nodes':p.get('nodes'),'uncertain':p.get('uncertain')})
    edges=p.get('edges')
    if not isinstance(edges,list):return errors+['edges_type']
    nodes=p.get('nodes') if isinstance(p.get('nodes'),list) else []
    ids={n['id'] for n in nodes if isinstance(n,dict) and isinstance(n.get('id'),str)}
    if set(p)!={'image_type','nodes','edges','uncertain'}:errors.append('graph_fields')
    for e in edges:
        if not isinstance(e,dict):errors.append('edge_object');continue
        if set(e)!={'id','source','target','bbox','attributes'}:errors.append('final_edge_fields')
        errors+=validate_stage('edges',{'edges':[{k:e.get(k) for k in ['id','source','target','bbox']}],'uncertain':[]})
        if not all(isinstance(e.get(k),str) and e[k] in ids for k in ['source','target']):errors.append('dangling_edge_reference')
        errors+=validate_stage('attributes',{'attributes':[e.get('attributes')],'uncertain':[]})
        if isinstance(e.get('attributes'),dict) and e['attributes'].get('edge_id')!=e.get('id'):errors.append('attribute_edge_reference')
    edge_ids=[e['id'] for e in edges if isinstance(e,dict) and isinstance(e.get('id'),str)]
    if len(set(edge_ids))!=len(edge_ids):errors.append('duplicate_edge_ids')
    return sorted(set(errors))
