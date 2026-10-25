"""Fixed annotation queue, grouped by source 50-page segments and near pairs, not gold."""
import hashlib


def make_benchmark(pages,features,requests,near_pairs,known_pages,development_pages=None,visual_duplicate_groups=None):
    parent={p:p for p in pages}
    def find(p):
        while parent[p]!=p:parent[p]=parent[parent[p]];p=parent[p]
        return p
    def union(a,b):
        if a in parent and b in parent:
            a,b=find(a),find(b)
            if a!=b:parent[max(a,b)]=min(a,b)
    chapters={}
    for n,p in pages.items():
        source=p['original_source'];key=(source['source_sha256'],(source['source_page']-1)//50)
        if key in chapters:union(n,chapters[key])
        else:chapters[key]=n
    for pair in near_pairs:union(pair['page_a'],pair['page_b'])
    for members in visual_duplicate_groups or []:
        for page in members[1:]:union(members[0],page)
    forced={find(p) for p in set(known_pages)|set(development_pages or [])}
    groups={n:find(n) for n in pages}
    split={g:('development' if g in forced or int(hashlib.sha256(f'it3170-v3:{g}'.encode()).hexdigest()[:8],16)%3==0 else 'holdout') for g in set(groups.values())}
    engines={n:set() for n in pages}
    for r in requests:engines[r['page']].add(r['engine'])
    def category(n):
        if n==129:return 'graph'
        if 'table' in engines[n]:return 'table'
        if 'vlm' in engines[n] or features[n].get('has_diagram') or features[n].get('has_chart'):return 'graph'
        if 'formula' in engines[n]:return 'formula'
        return 'native_or_sparse'
    chosen=set(known_pages);rows=[]
    # Deterministic sampling includes below-threshold pages to audit routing recall.
    for cat,target in [('graph',24),('formula',18),('table',8),('native_or_sparse',10)]:
        existing=sum(category(n)==cat for n in chosen)
        candidates=[n for n in pages if category(n)==cat and n not in chosen]
        candidates.sort(key=lambda n:hashlib.sha256(f'v3-annotation:{n}'.encode()).hexdigest())
        holdout_target={'graph':8,'formula':6,'table':2,'native_or_sparse':4}[cat]
        holdouts=[n for n in candidates if split[groups[n]]=='holdout']
        chosen.update(holdouts[:min(holdout_target,max(0,target-existing))])
        existing=sum(category(n)==cat for n in chosen)
        # Mix requested/non-requested figures; do not create VLM jobs for these pages.
        if cat=='graph':
            below=[n for n in candidates if 'vlm' not in engines[n]]
            for n in below[:min(8,max(0,target-existing))]:chosen.add(n)
        existing=sum(category(n)==cat for n in chosen)
        fill=[n for n in candidates if n not in chosen]
        fill.sort(key=lambda n:split[groups[n]]=='holdout')
        chosen.update(fill[:max(0,target-existing)])
    for n in sorted(chosen):
        p=pages[n]
        rows.append({'page':n,'document_sha256':p['document_sha256'],'render_sha256':p['render_sha256'],
                     'category':category(n),'group_id':groups[n],'split':split[groups[n]],
                     'scheduled_vlm': 'vlm' in engines[n], 'annotation_status':'pending',
                     'known_development_case':n in known_pages,
                     'gold':None,'reviewer':None,'evidence':None,
                     'note':'Annotation task only, never treat empty gold as a correct answer.'})
    protected_groups={r['group_id'] for r in rows if r['split']=='holdout'}
    # Protect the whole group, not merely the 40-ish pages selected for annotation.
    protected={n for n,g in groups.items() if g in protected_groups}
    return rows,groups,protected
