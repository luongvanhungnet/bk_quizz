"""Read actual Colab diagnostics without upgrading machine outputs to human gold."""
import argparse
from collections import Counter
from pathlib import Path
import json
import statistics
import zipfile
from io_utils import file_sha,load,write_json,safe_path

def analyze(archive,packet,out):
    archive=Path(archive);packet=Path(packet);out=Path(out)
    if out.exists():raise FileExistsError('Choose a fresh evaluation directory')
    out.mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        if z.testzip():raise ValueError('Corrupt ZIP')
        for info in z.infolist():
            if info.is_dir():continue
            target=safe_path(out/'raw',info.filename);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(info))
        names=z.namelist()
        read=lambda pattern:json.loads(z.read(next(n for n in names if pattern in n)))
        stage=read('stage_status_');vlm=read('vlm_results_')
        expected=file_sha(packet/'manifest.json')
        if stage['packet_manifest_sha256']!=expected or vlm['packet_manifest_sha256']!=expected:raise ValueError('Wrong input packet')
        pm=load(packet/'manifest.json');observations=vlm['observations']
        ocr=next(read(n) for n in names if n.startswith('paddle_ocr/results_'))
        ocr_candidates=[c for r in ocr['records'] for c in r['candidates']]
        confidence=[c['confidence'] for c in ocr_candidates if c.get('confidence') is not None]
        docling=read('parser_candidates_docling.json');dc=docling['parser_candidates']
        formula=read('paddle_formula/results_');table=read('paddle_table/results_')
        warm=[r['elapsed_seconds'] for r in observations[1:] if r['status']=='ok']
        metrics={'source_archive':str(archive.resolve()),'source_archive_sha256':file_sha(archive),'zip_crc_valid':True,
            'zip_members':len(names),'zip_bytes':archive.stat().st_size,'zip_uncompressed_bytes':sum(i.file_size for i in z.infolist()),
            'packet_manifest_sha256':expected,'scope':pm['scope'],'pages':sorted({q['page'] for q in pm['requests']}),
            'request_count':len(pm['requests']),'requests_by_kind':dict(Counter(q['kind'] for q in pm['requests'])),
            'stages':stage['stages'],'sum_logged_stage_seconds':sum(r['seconds'] for r in stage['stages']),
            'vlm':{'observations':len(observations),'success':sum(r['status']=='ok' for r in observations),'not_run':len(vlm['not_run_ids']),
                'truncated':sum(bool(r['telemetry'].get('possibly_truncated')) for r in observations),'cache_hits':sum(bool(r.get('cache_hit')) for r in observations),
                'sum_record_seconds':sum(r['elapsed_seconds'] for r in observations),'first_record_seconds':observations[0]['elapsed_seconds'],
                'warm_records':len(warm),'warm_mean_seconds':statistics.mean(warm),'warm_median_seconds':statistics.median(warm),
                'max_peak_allocated_bytes':max(r['telemetry']['peak_allocated'] for r in observations),
                'model_config':observations[0]['model_config'],'semantic_verified':False},
            'ocr':{'requests':ocr['request_count'],'success':sum(r['status']=='ok' for r in ocr['records']),
                'candidates':len(ocr_candidates),'empty_candidates':sum(not c['text'].strip() for c in ocr_candidates),
                'mean_model_confidence':statistics.mean(confidence),'median_model_confidence':statistics.median(confidence),
                'accuracy':None,'confidence_is_not_accuracy':True},
            'formula':{'new_requests':formula['request_count'],'valid_seeds_in_packet':sum(q['kind']=='formula' and q['specialist_seed_valid'] for q in pm['requests'])},
            'table':{'new_requests':table['request_count'],'valid_seeds_in_packet':sum(q['kind']=='table' and q['specialist_seed_valid'] for q in pm['requests'])},
            'docling':{'status':docling['status'],'candidates':len(dc),'by_kind':dict(Counter(c['kind'] for c in dc)),
                'records_with_replacement_character':sum('\ufffd' in c['text'] for c in dc),
                'text_records_with_replacement_character':sum(c['kind']=='text' and '\ufffd' in c['text'] for c in dc),
                'replacement_characters':sum(c['text'].count('\ufffd') for c in dc),'do_ocr':False,'independent_ocr':False},
            'mineru':{'executed':False},'CER':None,'WER':None,'Q':None,'human_reference_available':False,
            'notes':['Operational success is not factual accuracy.','Warm timing excludes only the first record, not a separately measured model initialization.',
                     'No new FormulaNet or table recognition requests were run.','This analysis never creates human verification or CPT approval.']}
    write_json(out/'metrics.json',metrics);write_json(out/'vlm_outputs.json',vlm)
    print(json.dumps({k:metrics[k] for k in ['source_archive_sha256','pages','request_count','vlm','ocr','formula','table','docling']},ensure_ascii=False,indent=2))
    return metrics

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);p.add_argument('--packet',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();analyze(a.archive,a.packet,a.out)
