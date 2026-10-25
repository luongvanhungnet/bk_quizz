"""Bind human metric references to the exact run; missing gold never becomes a score."""
from pathlib import Path
from io_utils import jsonl,load,write_json
from metrics import evaluate_metrics
from models import validate_record

def evaluate(run,references,out):
    run=Path(run);rows=jsonl(run/'records.jsonl');by_id={r['id']:r for r in rows};refs=jsonl(references)
    for ref in refs:
        r=by_id.get(ref.get('id'))
        if r is None:raise ValueError('Unknown reference record')
        for key in ['source_sha256','render_sha256','crop_sha256']:
            if ref.get(key)!=r.get(key):raise ValueError('Reference/source mismatch: '+key)
        if ref.get('assessment') and ref.get('machine_revision')!=r['machine_revision']:
            raise ValueError('Human assessment must bind the current machine_revision')
    refs_by_id={r['id']:r for r in refs}
    predictions=[]
    for r in rows:
        try:validate_record(r);valid=True
        except ValueError:valid=False
        prediction={'id':r['id'],'text':r['proposed_text'],'latex':r['proposed_text'] if r['kind']=='formula' else '',
            'label':r['kind'],'bbox':r['bbox'],'structural_valid':valid}
        # Coverage is supplied by a human matching source components to this
        # exact machine proposal, never by asking VLM to invent matching IDs.
        assessment=refs_by_id.get(r['id'],{}).get('assessment',{})
        if 'matched_prediction_component_ids' in assessment:
            prediction['covered_component_ids']=assessment['matched_prediction_component_ids']
        predictions.append(prediction)
    report=evaluate_metrics(refs,predictions)
    report.update(scope='human_reference_subset_only',run_source_sha256=load(run/'manifest.json')['document']['sha256'],
                  coverage_note='Component coverage requires explicit human component matching; no invented graph inventory.')
    if Path(out).exists():raise ValueError('Choose a new evaluation file')
    write_json(out,report);return report

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--references',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();print(evaluate(a.run,a.references,a.out))
