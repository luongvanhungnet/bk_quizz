"""Materialize independent layout regions for new documents, never verified facts.

This adapter supports corpus execution around the v5 engines. It does not change
the VLM prompt, require structured VLM output, or delete deferred regions.
"""
from collections import defaultdict
import copy
import math
from pathlib import Path
import re
import zipfile
import json
import pymupdf
from PIL import Image
from io_utils import load,jsonl,write_json,file_sha,sha,canonical
from prepare import context_crop,image_diagnostics,text_in_box
from workflow import publish,iou

def route(records,total_pages,target=.05,maximum=.08):
    if not 0<target<=maximum<=1:raise ValueError('Invalid VLM page budget')
    visual=[r for r in records if r['kind'] in ['image','diagram','chart']]
    groups=defaultdict(list)
    for r in visual:groups[r['image_quality']['pixel_sha256']].append(r)
    by_page=defaultdict(list)
    for r in visual:
        b=r['bbox'];area=(b[2]-b[0])*(b[3]-b[1])/1e6
        group=groups[r['image_quality']['pixel_sha256']]
        small_margin=area<=.025 and (b[3]<=180 or b[1]>=820)
        decoration=small_margin and len({x['page'] for x in group})>=3
        canonical_record=min(group,key=lambda x:(x['page'],x['id']))
        duplicate=r['id']!=canonical_record['id']
        hint=r.get('native_text','')+' '+r.get('context_text','')
        diagram=r['kind']=='diagram' or bool(re.search(r'đồ thị|sơ đồ|flowchart|\bgraph\b|architecture|backtracking|forward checking|\b[BD]FS\b',hint,re.I))
        chart=r['kind']=='chart'
        unknown=not decoration
        risk=area>=.1 and len(r.get('native_text',''))<80
        score=4*diagram+3*chart+2*unknown+risk-4*decoration
        features={'D':bool(diagram),'C':chart,'U':unknown,'R':risk,'B':decoration,'E':False}
        r['routing']={'score':score,'features':features,'image_area_ratio':area,
            'duplicate_of':canonical_record['id'] if duplicate else None,
            'decoration_evidence':'identical_pixels_on_3_pages_small_margin' if decoration else None}
        r['legacy_routing_state']='exact_duplicate' if duplicate else 'decoration_rule' if decoration else 'score_review'
        r['pending_engines']=[x for x in r.get('pending_engines',[]) if x!='vlm']
        if not decoration and not duplicate and score>=5:by_page[r['page']].append(r)
    limit=max(1,math.ceil(target*total_pages));cap=max(1,math.ceil(maximum*total_pages))
    ranked=sorted(by_page,key=lambda p:(-max(r['routing']['score'] for r in by_page[p]),p))
    chosen=set(ranked[:min(limit,cap)])
    for page,items in by_page.items():
        for r in items:
            r['legacy_routing_state']='scheduled' if page in chosen else 'score_review'
            if page in chosen:r['pending_engines'].append('vlm')
    return {'total_pages':total_pages,'candidate_pages':len(by_page),'scheduled_pages':sorted(chosen),
        'scheduled_regions':sum(len(by_page[p]) for p in chosen),'page_percent':100*len(chosen)/total_pages if total_pages else 0,
        'target_fraction':target,'maximum_fraction':maximum,'deferred_pages':sorted(set(by_page)-chosen),
        'unresolved_or_deferred_regions_retained':True,'semantic_verified':False,
        'small_document_rounding_exception':bool(chosen and len(chosen)/total_pages>maximum)}

def materialize(run,archive,packet,target=.05,maximum=.08):
    run=Path(run);packet=Path(packet);m=load(run/'manifest.json');pm=load(packet/'manifest.json')
    if (run/'prepare_summary.json').exists() and load(run/'prepare_summary.json').get('reused_layout_and_specialist_cache'):
        raise ValueError('Preserve the existing curated layout inventory; discovery is for new documents')
    if pm['document']['sha256']!=m['document']['sha256']:raise ValueError('Wrong layout document')
    if file_sha(m['document']['path'])!=m['document']['sha256']:raise ValueError('Changed PDF source')
    rows=jsonl(run/'records.jsonl');pages={p['page']:p for p in jsonl(run/'document_pages.jsonl')}
    full={r['page']:r for r in rows if r['kind'] in ['text','code'] and r['bbox']==[0,0,1000,1000]}
    known=set(r['id'] for r in rows);candidates=[];unmapped=[];parsed_pages=set()
    with zipfile.ZipFile(archive) as z:
        if z.testzip():raise ValueError('Corrupt layout ZIP')
        for name in z.namelist():
            if '/records/' in name and name.endswith('.json'):
                p=json.loads(z.read(name))
                if p.get('mode')=='structure' and p.get('status')=='ok':
                    q=next((q for q in pm['requests'] if q['id']==p.get('id')),None)
                    if not q or p.get('input_file_sha256')!=q['crop_sha256']:raise ValueError('Paddle layout image identity mismatch')
                    parsed_pages.add(q['page'])
                    for c in p.get('candidates',[]):
                        if c.get('bbox') and c.get('page')==q['page']:candidates.append(copy.deepcopy(c))
            if 'parser_candidates_' not in name or not name.endswith('.json'):continue
            e=json.loads(z.read(name))
            if e.get('packet_manifest_sha256')!=file_sha(packet/'manifest.json') or e.get('original_source_sha256')!=m['document']['sha256']:raise ValueError('Layout provenance mismatch')
            if e.get('status')!='ok':continue
            parsed_pages.update(pm['page_map'].values())
            for c in e['parser_candidates']:
                c=copy.deepcopy(c);page=pm['page_map'].get(str(c.get('page')))
                if page is None or not c.get('bbox'):unmapped.append(c);continue
                c['page']=page;candidates.append(c)
    if not parsed_pages:raise ValueError('No successful independent layout output in archive')
    # Generic raster proposals are unclassified until layout/rules supply a role.
    for r in rows:
        if m.get('layout_inventory_status')!='cached_inventory' and 'legacy_routing_state' not in r and r['kind']=='diagram':
            r['kind']='image'
    with pymupdf.open(m['document']['path']) as pdf:
        for c in candidates:
            if c['kind'] not in ['formula','table','image','diagram','chart']:continue
            if c['page'] not in pages:unmapped.append(c);continue
            matches=[r for r in rows if r['page']==c['page'] and r['kind']==c['kind'] and iou(r['bbox'],c['bbox'])>=.9]
            if matches:continue
            rid=f"{m['document']['sha256'][:12]}:p{c['page']:04d}:layout:{c['kind']}:{sha(canonical(c['bbox']))[:10]}"
            if rid in known:continue
            known.add(rid);p=pages[c['page']];base=full[c['page']];stem=rid.replace(':','_')
            crop='assets/crops/'+stem+'.png';context='assets/context/'+stem+'.png'
            with Image.open(run/p['render_path']) as im:
                b=tuple(round(x*im.size[i%2]/1000) for i,x in enumerate(c['bbox']))
                if b[2]<=b[0] or b[3]<=b[1]:unmapped.append(c);continue
                im.crop(b).save(run/crop)
            cb=context_crop(run/p['render_path'],run/context,c['bbox'])
            page=pdf[c['page']-1]
            native=text_in_box({'page_size_pt':list(page.rect)[2:],'blocks':[b for b in page.get_text('dict')['blocks'] if b.get('type')==0]},c['bbox'])
            ev=copy.deepcopy(c.get('evidence') or {});ev.update(region_id=rid,source_sha256=m['document']['sha256'],crop_sha256=file_sha(run/crop),same_region=True)
            candidate={**c,'evidence':ev}
            r={'id':rid,'page':c['page'],'kind':c['kind'],'bbox':c['bbox'],'render_path':p['render_path'],'render_sha256':p['render_sha256'],
                'crop_path':crop,'crop_sha256':file_sha(run/crop),'context_path':context,'context_sha256':file_sha(run/context),'context_bbox':cb,
                'source_sha256':m['document']['sha256'],'native_text':native,'context_text':base['native_text'][:240],
                'candidates':[candidate],'image_quality':image_diagnostics(run/crop),'group_id':base['group_id'],'split':base['split'],
                'pending_engines':['paddle_formula'] if c['kind']=='formula' else ['paddle_table'] if c['kind']=='table' else [],
                'human_review_required':c['kind'] in ['diagram','chart','image'],'semantic_verified':False,'layout_source_archive_sha256':file_sha(archive)}
            if native:r['candidates'].append({'engine':'native','text':native,'status':'ok','evidence':{'source_sha256':r['source_sha256'],'region_id':rid,'crop_sha256':r['crop_sha256'],'backend_family':'pymupdf'}})
            # A mislabelled paragraph must not be sent blindly to FormulaNet.
            if c['kind']=='formula' and len(native.split())>24 and not re.search(r'[=∑∏∫√≤≥≠]|\\frac|\\sum',native):
                r['specialist_disabled']=True;r['pending_engines']=[];r['routing_hold']='formula_looks_like_text_paragraph'
            rows.append(r)
    routing=route(rows,m['document']['pages'],target,maximum)
    receipt={'type':'layout_materialization','archive_sha256':file_sha(archive),'packet_manifest_sha256':file_sha(packet/'manifest.json'),
        'source_sha256':m['document']['sha256'],'parsed_pages':sorted(parsed_pages),'unmapped_candidates':unmapped,'routing':routing}
    summary=publish(run,rows,receipt)
    progress=set(m.get('layout_pages_processed',[]))|parsed_pages
    m.update(layout_pages_processed=sorted(progress),layout_inventory_status='ready' if len(progress)==m['document']['pages'] else 'partial_layout')
    write_json(run/'manifest.json',m);write_json(run/'routing_summary.json',routing)
    return {**summary,'layout_inventory_status':m['layout_inventory_status'],'routing':routing}
