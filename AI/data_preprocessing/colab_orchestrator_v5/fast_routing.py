"""Equivalent routing features with one aggregate per exact-pixel group."""
from collections import defaultdict
import math
import re


def route(records,total_pages,target=.05,maximum=.08):
    if not 0<target<=maximum<=1:raise ValueError('Invalid VLM budget')
    visual=[r for r in records if r['kind'] in {'image','diagram','chart'}]
    groups={}
    for r in visual:
        key=r['image_quality']['pixel_sha256']; item=groups.setdefault(key,{'pages':set(),'first':r})
        item['pages'].add(r['page'])
        if (r['page'],r['id'])<(item['first']['page'],item['first']['id']):item['first']=r
    by_page=defaultdict(list)
    for r in visual:
        b=r['bbox'];area=(b[2]-b[0])*(b[3]-b[1])/1e6;group=groups[r['image_quality']['pixel_sha256']]
        decoration=area<=.025 and (b[3]<=180 or b[1]>=820) and len(group['pages'])>=3
        first=group['first'];duplicate=r['id']!=first['id']
        hint=r.get('native_text','')+' '+r.get('context_text','')
        diagram=r['kind']=='diagram' or bool(re.search(r'đồ thị|sơ đồ|flowchart|\bgraph\b|architecture|backtracking|forward checking|\b[BD]FS\b',hint,re.I))
        chart=r['kind']=='chart';unknown=not decoration;risk=area>=.1 and len(r.get('native_text',''))<80
        score=4*diagram+3*chart+2*unknown+risk-4*decoration
        r['routing']={'score':score,'features':{'D':bool(diagram),'C':chart,'U':unknown,'R':risk,'B':decoration,'E':False},
                      'image_area_ratio':area,'duplicate_of':first['id'] if duplicate else None,
                      'decoration_evidence':'identical_pixels_on_3_pages_small_margin' if decoration else None}
        r['legacy_routing_state']='exact_duplicate' if duplicate else 'decoration_rule' if decoration else 'score_review'
        r['pending_engines']=[x for x in r.get('pending_engines',[]) if x!='vlm']
        if not decoration and not duplicate and score>=5:by_page[r['page']].append(r)
    ranked=sorted(by_page,key=lambda p:(-max(r['routing']['score'] for r in by_page[p]),p))
    chosen=set(ranked[:min(max(1,math.ceil(target*total_pages)),max(1,math.ceil(maximum*total_pages)))])
    for p,items in by_page.items():
        for r in items:
            r['legacy_routing_state']='scheduled' if p in chosen else 'score_review'
            if p in chosen:r['pending_engines'].append('vlm')
    return {'total_pages':total_pages,'candidate_pages':len(by_page),'scheduled_pages':sorted(chosen),
            'scheduled_regions':sum(len(by_page[p]) for p in chosen),'page_percent':100*len(chosen)/total_pages if total_pages else 0,
            'target_fraction':target,'maximum_fraction':maximum,'deferred_pages':sorted(set(by_page)-chosen),
            'unresolved_or_deferred_regions_retained':True,'semantic_verified':False,
            'small_document_rounding_exception':bool(chosen and len(chosen)/total_pages>maximum)}
