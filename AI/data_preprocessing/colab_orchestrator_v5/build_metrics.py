"""Real PDF structure and CPU routing evidence; never label fake GPU tests as inference."""
import copy
from pathlib import Path
import sys
import tempfile
import time

from common import atomic_json,digest,load

ROOT=Path(__file__).resolve().parent
ENGINE=ROOT.parent.parent/'Qwen_cpt_version/region_preprocessing_v5_official'


def build():
    import pymupdf
    from region_policy import proposals
    from fast_routing import route
    sys.path.insert(0,str(ENGINE));import batch_layout
    source=Path('D:/bk_quizz_data/slide_processed/pdf/IT4906-Tính toán tiến hóa.pdf');sha=digest(source)
    metrics=[];started=time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp,pymupdf.open(source) as doc:
        for page in [3,10,115,116,122,217,227]:
            kept,audit=proposals(doc[page-1],sha,tmp,page)
            metrics.append({'page':page,'before_raw_image_occurrences':audit['displayed_occurrences'],
                            'after_image_regions':len(kept),'background_occurrences_excluded':audit['suppressed_background_occurrences'],
                            'full_page_ocr_retained':True,'source_render_policy':'retained'})
    pdf_seconds=time.perf_counter()-started
    data=[{'id':str(i),'page':i%20+1,'kind':'diagram','bbox':[100,200,800,800],
           'image_quality':{'pixel_sha256':str(i%5)},'pending_engines':['vlm'],'native_text':'graph'} for i in range(5000)]
    old=copy.deepcopy(data);new=copy.deepcopy(data)
    started=time.perf_counter();before=batch_layout.route(old,20);old_seconds=time.perf_counter()-started
    started=time.perf_counter();after=route(new,20);new_seconds=time.perf_counter()-started
    if before!=after or old!=new:raise AssertionError('Routing behavior changed')
    folder=ROOT.parent/'uploads_134_unit100_20261022';index=load(folder/'UPLOAD_INDEX.json')
    for e in index['bundles']:
        if digest(folder/e['filename'])!=e['sha256']:raise ValueError('Original input ZIP changed')
    result={'preprocessing_version':'6.0.0','source_sha256':sha,'IT4906_pages':metrics,
            'total_background_occurrences_excluded':sum(x['background_occurrences_excluded'] for x in metrics),
            'pdf_structure_check_seconds':pdf_seconds,
            'routing_benchmark':{'records':5000,'old_seconds':old_seconds,'new_seconds':new_seconds,
                'speedup':old_seconds/new_seconds,'equivalent_output':True,'scope':'local_CPU_synthetic_duplicate_groups_not_end_to_end_Colab'},
            'original_input_zip_sha256_verified':len(index['bundles']),'index_sha256':digest(folder/'UPLOAD_INDEX.json'),
            'actual_GPU_inference':False,'actual_Colab_executed':False,'quality_score_measured':False}
    atomic_json(ROOT/'REGRESSION_METRICS.json',result);return result


if __name__=='__main__':print(build())
