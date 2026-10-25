"""One schema source for validation, complete examples and model instructions."""
import copy
import json
import math
import re

def obj(**fields):return {'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}
def arr(items,maximum=64):return {'type':'array','items':items,'maxItems':maximum}
S={'type':'string','maxLength':160}
ID={'type':'string','minLength':1,'maxLength':40}
BOOL={'type':'boolean'}
TRI={'type':['boolean','null']}
BOX={'type':'array','items':{'type':'number','minimum':0,'maximum':1000},'minItems':4,'maxItems':4,'format':'bbox'}
NB={**BOX,'type':['array','null']}
CELL={'type':'array','items':{'type':'integer','minimum':0,'maximum':15},'minItems':2,'maxItems':2}
UNC=arr(S,12)
NODE=obj(id=ID,label=S,bbox=BOX)
EDGE=obj(id=ID,source=ID,target=ID,bbox=BOX)
ATTR=obj(edge_id=ID,visible=TRI,weight={'type':['number','string','null'],'maxLength':40},weight_bbox=NB,
         directed=TRI,arrow_target={'type':['string','null'],'maxLength':40},arrow_bbox=NB,
         highlighted=TRI,highlight_bbox=NB,reference_bbox=NB,
         direction_basis={'type':'string','enum':['arrowhead','explicit_undirected_caption','unknown']},native_quote=S)
REL=obj(parent=ID,child=ID,bbox=BOX)
SCHEMAS={
 'inventory':obj(node_ids=arr(ID,24),edge_ids=arr(ID,96),complete=TRI,uncertain=UNC),
 'edge_attributes':obj(attributes=arr(ATTR,4),uncertain=UNC),
 'nodes':obj(nodes=arr(NODE,16),uncertain=UNC),
 'edges':obj(edges=arr(EDGE,32),uncertain=UNC),
 'board':obj(id=ID,is_board=BOOL,board_size={'type':'integer','minimum':1,'maximum':16},queens=arr(CELL,16),removed_cells=arr(CELL,256),uncertain=UNC),
 'tree_links':obj(relations=arr(REL,48),complete=TRI,uncertain=UNC),
}
ATTR_EXAMPLE={'edge_id':'e1','visible':True,'weight':None,'weight_bbox':None,'directed':None,'arrow_target':None,'arrow_bbox':None,
              'highlighted':None,'highlight_bbox':None,'reference_bbox':None,'direction_basis':'unknown','native_quote':''}
EXAMPLES={
 'inventory':{'node_ids':['n1','n2'],'edge_ids':['e1'],'complete':True,'uncertain':[]},
 'edge_attributes':{'attributes':[ATTR_EXAMPLE],'uncertain':[]},
 'nodes':{'nodes':[{'id':'n1','label':'a','bbox':[100,100,160,160]}],'uncertain':[]},
 'edges':{'edges':[{'id':'e1','source':'n1','target':'n2','bbox':[150,150,400,400]}],'uncertain':[]},
 'board':{'id':'b1','is_board':True,'board_size':4,'queens':[[0,1]],'removed_cells':[],'uncertain':[]},
 'tree_links':{'relations':[{'parent':'b1','child':'b2','bbox':[150,200,400,450]}],'complete':True,'uncertain':[]},
}

def validate(value,schema,path='$'):
    types=schema['type'];types=[types] if isinstance(types,str) else types
    kind='null' if value is None else 'boolean' if type(value) is bool else 'integer' if type(value) is int else 'number' if type(value) is float else 'string' if isinstance(value,str) else 'array' if isinstance(value,list) else 'object' if isinstance(value,dict) else 'unsupported'
    if kind not in types and not(kind=='integer' and 'number' in types):return [path+':type']
    if value is None:return []
    errors=[]
    if 'enum' in schema and value not in schema['enum']:errors.append(path+':enum')
    if kind in ['integer','number']:
        if not math.isfinite(value) or value<schema.get('minimum',-math.inf) or value>schema.get('maximum',math.inf):errors.append(path+':range')
    if kind=='string' and not schema.get('minLength',0)<=len(value)<=schema.get('maxLength',100000):errors.append(path+':length')
    if kind=='array':
        if not schema.get('minItems',0)<=len(value)<=schema.get('maxItems',100000):errors.append(path+':items')
        for i,item in enumerate(value):errors+=validate(item,schema['items'],f'{path}[{i}]')
        if schema.get('format')=='bbox' and (len(value)!=4 or any(type(v) not in [int,float] for v in value) or not(value[0]<value[2] and value[1]<value[3])):errors.append(path+':bbox')
    if kind=='object':
        if set(schema['required'])-set(value):errors.append(path+':required')
        if set(value)-set(schema['properties']):errors.append(path+':extra_fields')
        for key,item in value.items():
            if key in schema['properties']:errors+=validate(item,schema['properties'][key],path+'.'+key)
    return errors

def parse(raw,stage):
    """Only allow lossless structural repairs; never recover missing facts."""
    repairs=[];value=raw.strip()
    if value.startswith('```'):
        match=re.fullmatch(r'```(?:json)?\s*\n(.*?)\n```\s*',value,re.S|re.I)
        if not match:raise ValueError('Incomplete Markdown wrapper')
        value=match.group(1);repairs.append('remove_markdown_fence')
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise ValueError('Duplicate JSON key: '+k)
            out[k]=v
        return out
    def constant(v):raise ValueError('Invalid JSON constant '+v)
    value=json.loads(value,object_pairs_hook=pairs,parse_constant=constant)
    if isinstance(value,list) and len(value)==1 and isinstance(value[0],dict):value=value[0];repairs.append('unwrap_singleton_object_array')
    if stage=='edge_attributes' and isinstance(value,dict) and isinstance(value.get('attributes'),list):
        value=copy.deepcopy(value)
        for a in value['attributes']:
            if isinstance(a,dict) and 'native_quote' in a and a['native_quote'] is None:
                a['native_quote']='';repairs.append('null_native_quote_to_empty_string:'+str(a.get('edge_id')))
    errors=validate(value,SCHEMAS[stage])
    return value,repairs,errors

def validate_task(stage,p,payload):
    errors=validate(p,SCHEMAS[stage])
    if errors:return errors
    if stage=='inventory':
        for key,source in [('node_ids','nodes'),('edge_ids','edges')]:
            if len(set(p[key]))!=len(p[key]) or not set(p[key])<={v['id'] for v in payload[source]}:errors.append(key+':unknown_or_duplicate')
        nodes=set(p['node_ids'])
        if any(e['id'] in p['edge_ids'] and not {e['source'],e['target']}<=nodes for e in payload['edges']):errors.append('edge_with_rejected_node')
    if stage=='edge_attributes':
        expected={e['id']:e for e in payload['edges']};ids=[a['edge_id'] for a in p['attributes']]
        if len(set(ids))!=len(ids) or set(ids)!=set(expected):errors.append('attribute_inventory')
        for a in p['attributes']:
            if a['directed'] is True and a['edge_id'] in expected and a['arrow_target'] not in [expected[a['edge_id']]['source'],expected[a['edge_id']]['target']]:errors.append('arrow_not_endpoint')
    if stage in ['nodes','edges']:
        ids=[r['id'] for r in p[stage]]
        if len(set(ids))!=len(ids):errors.append('duplicate_ids')
    if stage=='edges':
        nodes={n['id'] for n in payload['nodes']}
        if any(e['source'] not in nodes or e['target'] not in nodes or e['source']==e['target'] for e in p['edges']):errors.append('dangling_edge')
    if stage=='board':
        if p['id']!=payload['id'] or p['board_size']!=payload['board_size']:errors.append('board_identity')
        for field in ['queens','removed_cells']:
            cells=[tuple(c) for c in p[field]]
            if len(set(cells))!=len(cells) or any(max(c)>=p['board_size'] for c in cells):errors.append(field+':cells')
        if {tuple(c) for c in p['queens']} & {tuple(c) for c in p['removed_cells']}:errors.append('queen_removed_overlap')
    if stage=='tree_links':
        ids={b['id'] for b in payload['boards']};pairs=[]
        for e in p['relations']:
            if e['parent'] not in ids or e['child'] not in ids or e['parent']==e['child']:errors.append('relation_identity')
            pairs.append((e['parent'],e['child']))
        if len(set(pairs))!=len(pairs):errors.append('duplicate_relations')
    return sorted(set(errors))
