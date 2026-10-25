"""v4 gates add inventory and geometry checks; all results stay in review."""
from quality_base import *
from quality_base import assess as previous_assess
from geometry import endpoint_consistent

def assess(engine,p,context):
    out=previous_assess(engine,p,context);flags=list(out['flags'])
    if engine=='vlm' and p.get('image_type') in ['graph','diagram','flowchart','unknown']:
        by_id={n['id']:n for n in p['nodes']}
        for e in p['edges']:
            if not endpoint_consistent(e,by_id):flags.append('edge_bbox_endpoint_mismatch')
        native=context.get('native_graph_candidates',{}).get('nodes',[])
        if native:
            for n in p['nodes']:
                if not any(intersects(n['bbox'],a['bbox']) for a in native):flags.append('node_without_native_shape_requires_review')
        native_ids={n['id']:n.get('label') for n in native}
        predicted={tuple(sorted([by_id[e['source']]['label'],by_id[e['target']]['label']])):e for e in p['edges']}
        for e in context.get('native_graph_candidates',{}).get('edges',[]):
            labels=[native_ids.get(e['source']),native_ids.get(e['target'])]
            if None in labels:continue
            pair=tuple(sorted(labels))
            if e.get('weight_candidates') and pair in predicted and predicted[pair]['attributes']['weight'] is None:flags.append('native_weight_unread_requires_review')
    if context.get('_inventory_complete') is not True: 
        if engine=='vlm':flags.append('visual_inventory_not_confirmed_complete')
    if context.get('_partial_task_failures'):flags.append('partial_task_failures')
    out['flags']=sorted(set(flags));out['evidence_gate_pass']=not out['flags']
    return out
