"""Respect partial Docling child coverage without changing frozen v5 files."""
import json
from pathlib import Path
import types
import zipfile


def route_scope(records, scope):
    """Keep source identities; allocate a unit-wide page budget across its PDFs."""
    import batch_layout
    count=scope['pages'];budget=scope['vlm_page_budget']
    if not 0 <= budget <= count:raise ValueError('Invalid unit VLM budget')
    result=batch_layout.route(records,count,1,1)
    candidates=result['scheduled_pages']
    visual=[r for r in records if r['kind'] in {'image','diagram','chart'} and r.get('routing')]
    ranked=sorted(candidates,key=lambda p:(-max(r['routing']['score'] for r in visual if r['page']==p and r.get('legacy_routing_state')=='scheduled'),p))
    chosen=set(ranked[:budget])
    for r in visual:
        if r.get('legacy_routing_state')=='scheduled' and r['page'] not in chosen:
            r['legacy_routing_state']='score_review'
            r['pending_engines']=[x for x in r.get('pending_engines',[]) if x!='vlm']
    result.update(scheduled_pages=sorted(chosen),scheduled_regions=sum(r.get('legacy_routing_state')=='scheduled' for r in visual),
                  deferred_pages=sorted(set(candidates)-chosen),page_percent=100*len(chosen)/count,
                  target_fraction=.05,maximum_fraction=.08,unit_allocated_budget=budget,
                  budget_scope='this_unit_component_not_entire_document')
    return result


def install():
    import batch_layout
    if getattr(batch_layout,'_v3_coverage_adapter',False):return
    original=batch_layout.materialize

    def materialize(run,archive,packet,target=.05,maximum=.08):
        manifest_path=(Path(packet)/'manifest.json').resolve()
        original_load=original.__globals__['load'];pm=original_load(manifest_path)
        covered=set();has_child=False
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if 'parser_candidates_' not in name or not name.endswith('.json'):continue
                envelope=json.loads(z.read(name))
                if envelope.get('status')!='ok':continue
                pages=envelope.get('covered_source_pages')
                if pages is None:covered.update(pm['page_map'].values())  # Legacy full-job envelope.
                else:
                    has_child=True
                    if not set(pages).issubset(pm['page_map'].values()):raise ValueError('Parser coverage outside parent packet')
                    covered.update(pages)
        run_manifest=original_load(Path(run)/'manifest.json');scope=run_manifest.get('processing_scope')
        if not has_child and not scope:return original(run,archive,packet,target,maximum)

        def scoped_load(path):
            value=original_load(path)
            if has_child and Path(path).resolve()==manifest_path:
                # Preserve the original file/hash and parent-local candidate indices.
                # Only parser-success coverage is narrowed; successful structure
                # records still add their own source pages independently.
                value={**value,'page_map':{k:v for k,v in value['page_map'].items() if v in covered}}
            return value

        globals_for_call={**original.__globals__,'load':scoped_load}
        if scope:globals_for_call['route']=lambda records,*args:route_scope(records,scope)
        scoped=types.FunctionType(original.__code__,globals_for_call,
                                  original.__name__,original.__defaults__,original.__closure__)
        result=scoped(run,archive,packet,target,maximum)
        if scope:
            from common import atomic_json
            path=Path(run)/'manifest.json';m=original_load(path)
            expected=set(range(scope['first_page'],scope['last_page']+1))
            progress=set(m.get('layout_pages_processed',[]))
            if not progress.issubset(expected):raise ValueError('Layout escaped unit page scope')
            m['layout_inventory_status']='ready' if progress==expected else 'partial_layout'
            m['layout_scope']='unit_pages_only'
            m['document_layout_complete']=len(progress)==m['document']['pages']
            atomic_json(path,m);result['layout_inventory_status']=m['layout_inventory_status']
        return result

    batch_layout.materialize=materialize;batch_layout._v3_coverage_adapter=True
