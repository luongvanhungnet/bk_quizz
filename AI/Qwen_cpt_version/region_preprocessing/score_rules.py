"""Explainable rule-based scoring; no quota or top-k promotion/truncation."""
import argparse
import collections
import copy
import json
import math
import re
import shutil
import time
import zipfile
from pathlib import Path

from route import ROOT,BASE,DEFAULT_TOKENIZER,load,read_jsonl,write_jsonl,dump_json,digest,area,overlap,contains,pack

POLICY={
    'version':'it3170-rule-score-v3','formula':'4D+3C+2U+R-4B-3E',
    'vlm_threshold':7,'confirmed_chart_threshold':6,'review_threshold':2,
    'target_page_ratio':[.04,.08],'sparse_body_characters':120,'large_image_ratio':.15,
    'poor_native_region_coverage':.6,'minimum_native_label_count':4,
    'minimum_native_vector_count':3,'minimum_cv_link_count':3,
    'raster_min_white_fraction':.45,'raster_min_circle_count':3,
    'raster_min_box_count':4,'raster_min_box_link_count':5,
    'raster_circle_min_diagonal_links':2,'suspected_cover_blocks_diagram_detection':True,
    'cv_probe_max_side':512,'quota_enforced':False,
}
TEXT_LABELS={'text','paragraph_title','doc_title','algorithm','abstract','footnote','figure_title','chart_title'}
SHORT_LABEL=re.compile(r'(?:[A-Za-z]|\d{1,3}(?:[,. ]\d{1,3})*)')
DIAGRAM_WORDS=re.compile(r'đồ thị|sơ đồ|lưu đồ|\bcây\b|\bgraph\b|\btree\b|\bdfs\b|\bbfs\b|kruskal|dijkstra|flowchart|backtracking|\bheap\b|quay lui|trạng thái',re.I)
CHART_WORDS=re.compile(r'biểu đồ|histogram|accuracy|\bepoch\b|tần suất|thống kê|trục\s*[xy]|\baxis\b|\baxes\b',re.I)


def score(terms):
    if set(terms)!={'D','C','U','R','B','E'} or any(type(v) is not int or v not in [0,1] for v in terms.values()):
        raise ValueError('All six terms must be binary integers')
    return 4*terms['D']+3*terms['C']+2*terms['U']+terms['R']-4*terms['B']-3*terms['E']


def decide(terms,is_duplicate=False,policy=POLICY):
    s=score(terms)
    if terms['B']:return 'exclude_verified_decoration'
    if terms['E']:return 'reuse_verified_extraction'
    if is_duplicate:return 'reuse_pending_canonical'
    if s>=policy['vlm_threshold'] or (terms['C'] and s>=policy['confirmed_chart_threshold']):return 'vlm'
    # A low score never asserts complete image understanding.
    return 'review' if terms['U'] or terms['R'] or s>=policy['review_threshold'] else 'native_or_specialist'


def cv_probe(path):
    """Cheap geometry counts; not a learned image classifier or semantic proof."""
    import cv2
    import numpy as np
    im=cv2.imread(str(path));h,w=im.shape[:2]
    scale=min(1,POLICY['cv_probe_max_side']/max(h,w))
    if scale<1:im=cv2.resize(im,(max(1,int(w*scale)),max(1,int(h*scale))),interpolation=cv2.INTER_AREA)
    h,w=im.shape[:2];gray=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)
    white=float(np.mean(np.all(im>=225,axis=2)))
    _,binary=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    edges=cv2.Canny(gray,50,150)
    contours,_=cv2.findContours(binary,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    colored_contours,_=cv2.findContours(cv2.morphologyEx(edges,cv2.MORPH_CLOSE,np.ones((2,2),np.uint8)),cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    contours=list(contours)+list(colored_contours)
    circles=[];boxes=[]
    for contour in contours:
        a=cv2.contourArea(contour);perimeter=cv2.arcLength(contour,True)
        if a<30 or a>w*h*.2 or perimeter<=0:continue
        x,y,bw,bh=cv2.boundingRect(contour);aspect=bw/max(1,bh)
        if .65<=aspect<=1.5 and a<w*h*.04 and 4*math.pi*a/perimeter**2>=.65:
            center=(x+bw/2,y+bh/2)
            if not any(math.dist(center,c)<max(4,min(bw,bh)*.25) for c in circles):circles.append(center)
        approx=cv2.approxPolyDP(contour,.025*perimeter,True)
        if len(approx)==4 and cv2.isContourConvex(approx) and .3<=aspect<=5 and a>50:
            center=(x+bw/2,y+bh/2)
            if not any(math.dist(center,c)<4 for c in boxes):boxes.append(center)
    lines=cv2.HoughLinesP(edges,1,np.pi/180,threshold=20,minLineLength=max(12,int(w*.035)),maxLineGap=3)
    vectors=[] if lines is None else [tuple(int(v) for v in line[0]) for line in lines]
    horizontal=sum(abs(v[3]-v[1])<=max(2,abs(v[2]-v[0])*.15) for v in vectors)
    vertical=sum(abs(v[2]-v[0])<=max(2,abs(v[3]-v[1])*.15) for v in vectors)
    return {'white_fraction':round(white,5),'circles':len(circles),'rectangles':len(boxes),
            'line_segments':len(vectors),'horizontal_segments':horizontal,'vertical_segments':vertical,
            'measurement_scope':'deterministic_geometry_not_graph_ground_truth'}


def body_context(page,layout):
    W,H=page['page_size_pt'];scale=page['render_width']/W
    blocks=[b for b in page['blocks'] if b['bbox'][1]>=H*.05 and b['bbox'][3]<=H*.9]
    text='\n'.join(b['text'] for b in blocks)
    zones=[b for b in layout if b['label'] in TEXT_LABELS and b.get('score',0)>=.5 and
           b['coordinate'][1]>=H*scale*.05 and b['coordinate'][3]<=H*scale*.9]
    lines=[line for b in blocks for line in b.get('lines',[]) if line['text'].strip()]
    covered=0
    for z in zones:
        count=sum(len(line['text'].strip()) for line in lines if contains(z['coordinate'],[v*scale for v in line['bbox']],.5))
        covered+=count>=3
    return {'body_text':text,'body_characters':len(text),'native_text_coverage':covered/len(zones) if zones else None,
            'native_text_zone_count':len(zones),
            'coverage_definition':'fraction of detected body text zones with at least 3 native characters; not OCR CER or graph-relation coverage'}


def region_features(region,page,context,probe):
    scale=page['render_width']/page['page_size_pt'][0];box=region['bbox_pixels']
    ratio=min(1,area(box)/(page['render_width']*page['page_size_pt'][1]*scale))
    lines=[line['text'].strip() for b in page['blocks'] for line in b.get('lines',[])
           if contains(box,[v*scale for v in line['bbox']],.8)]
    labels=[v for v in lines if SHORT_LABEL.fullmatch(v)]
    native_vectors=sum(contains(box,[v*scale for v in d['bbox']],.8) for d in page.get('vector_regions',[]))
    keyword=bool(DIAGRAM_WORDS.search(context['body_text']))
    native_topology=(len(labels)>=POLICY['minimum_native_label_count'] and native_vectors>=POLICY['minimum_native_vector_count']
                     and probe['line_segments']>=POLICY['minimum_cv_link_count'])
    raster_topology=(probe['white_fraction']>=POLICY['raster_min_white_fraction'] and (
                     (probe['circles']>=POLICY['raster_min_circle_count'] and probe['line_segments']>=3 and
                      probe['line_segments']-probe['horizontal_segments']-probe['vertical_segments']>=POLICY['raster_circle_min_diagonal_links']) or
                     (probe['rectangles']>=POLICY['raster_min_box_count'] and probe['line_segments']>=POLICY['raster_min_box_link_count'])))
    # Low-confidence/fallback crops need native topology or corroborating context.
    raster_topology=raster_topology and (region.get('layout_score') is not None and region['layout_score']>=.5 or keyword)
    diagram=bool(native_topology or raster_topology)
    chart=bool(region['label']=='chart' and CHART_WORDS.search(context['body_text']) and len(labels)>=4
               and probe['horizontal_segments']>=2 and probe['vertical_segments']>=2 and ratio>=.08)
    suspected_cover=bool(re.search(r'thuật\s+toán\s+ứng\s+dụng',context['body_text'],re.I) and
                         re.search(r'@|bộ\s+môn|giảng\s+viên|lecturer',context['body_text'],re.I) and len(labels)<4)
    if suspected_cover:diagram=False;chart=False
    complete=region['state']=='reviewed_source'
    coverage=context['native_text_coverage']
    risk=not complete and ratio>=POLICY['large_image_ratio'] and (context['body_characters']<POLICY['sparse_body_characters'] or
             coverage is not None and coverage<POLICY['poor_native_region_coverage'])
    terms={'D':int(diagram),'C':int(chart),'U':int(not complete),'R':int(risk),'B':0,'E':int(complete)}
    return {'has_diagram':diagram,'has_chart':chart,'native_text_coverage':coverage,
            'image_area_ratio':round(ratio,6),'is_duplicate':region['state']=='exact_duplicate',
            'specialist_success':complete,'terms':terms,'score':score(terms),
            'base_decision':decide(terms),'decision':decide(terms,region['state']=='exact_duplicate'),
            'evidence':{'native_short_labels':len(labels),'native_vector_regions':native_vectors,
                        'body_characters':context['body_characters'],'diagram_keyword':keyword,'cv':probe,
                        'suspected_cover_not_verified_decoration':suspected_cover,
                        'specialist_success_basis':'source_hash_bound_semantic_review' if complete else None}}


def choose_representatives(regions):
    groups=collections.defaultdict(list)
    for r in regions:
        if r['engine']=='vlm' and r['state']!='reviewed_source':groups[r['raw_pixel_sha256']].append(r)
    for items in groups.values():
        representative=max(items,key=lambda r:(r['routing_features']['base_decision']=='vlm',
                               r['routing_features']['score'],float(r.get('layout_score') or 0),-r['page']))
        for r in items:
            duplicate=r is not representative
            r['routing_features']['is_duplicate']=duplicate
            r['routing_features']['decision']=decide(r['routing_features']['terms'],duplicate)
            if duplicate:r.update(state='exact_duplicate',duplicate_of=representative['id'])
            else:
                r.pop('duplicate_of',None)
                r['state']='scheduled' if r['routing_features']['base_decision']=='vlm' else 'score_review'


def run(a):
    start=time.perf_counter();source=a.source_run.resolve();out=a.out.resolve()
    if (out/'manifest.json').exists():raise ValueError('Completed scored run exists; choose a new --out')
    m=load(source/'manifest.json');original_config=m['config']
    for name,key in [('worker.py','worker_sha256'),('prompt.txt','prompt_sha256'),('validation.py','validation_sha256')]:
        if digest((ROOT/name).read_bytes())!=original_config[key]:raise ValueError('Source worker/schema changed; create a new base plan')
    regions=read_jsonl(source/'regions.jsonl')
    if digest((source/'regions.jsonl').read_bytes())!=m['regions_sha256']:raise ValueError('Source region inventory changed')
    native=Path(m['source_native_root']);document=m['document']
    if digest(Path(document['path']).read_bytes())!=document['sha256']:raise ValueError('Source PDF changed')
    pages={p['page']:p for p in read_jsonl(native/'native_pages.jsonl')}
    for p in pages.values():
        if p['document_sha256']!=document['sha256'] or p['render_sha256']!=m['source_render_hashes'][str(p['page'])]:
            raise ValueError('Source native page changed')
    contexts={}
    for page in pages:
        layout_path=a.layout_root/'components'/f'page_{page:04d}.json';layout=load(layout_path)
        if any(layout[k]!=pages[page][k] for k in ['document_sha256','render_sha256']):raise ValueError('Stale layout')
        if m['layout_sources'][str(page)].get('sha256')!=digest(layout_path.read_bytes()):raise ValueError('Layout cache changed')
        contexts[page]=body_context(pages[page],layout['result']['layout_det_res']['boxes'])
    probes={};scored=[]
    for i,r in enumerate(regions):
        if r['engine']=='vlm':
            image=source/r['image']
            if digest(image.read_bytes())!=r['input_file_sha256']:raise ValueError('Changed crop')
            key=r['input_pixel_sha256']
            if key not in probes:probes[key]=cv_probe(image)
            features=region_features(r,pages[r['page']],contexts[r['page']],probes[key])
            r['routing_features']=features;scored.append({'id':r['id'],'page':r['page'],**features})
            if r['state'] not in ['exact_duplicate','reviewed_source']:
                r['state']='scheduled' if features['decision']=='vlm' else 'score_review'
        if i%200==0:print('scored regions',i,'/',len(regions),flush=True)
    choose_representatives(regions)
    scored=[{'id':r['id'],'page':r['page'],**r['routing_features']} for r in regions if 'routing_features' in r]
    chosen={r['page'] for r in regions if r['engine']=='vlm' and r['state']=='scheduled'}
    original_review=read_jsonl(source/'review_queue.jsonl')
    rows_by_page=collections.defaultdict(list)
    for r in regions:rows_by_page[r['page']].append(r)
    carried=read_jsonl(source/'carried_train.metadata.jsonl');carried_pages={r['page'] for r in carried}
    base_review_pages={r['page'] for r in original_review}
    excluded=set(pages)-base_review_pages-carried_pages
    page_features=[]
    for n,p in pages.items():
        candidates=[r['routing_features'] for r in rows_by_page[n] if 'routing_features' in r]
        if candidates:
            feature=copy.deepcopy(max(candidates,key=lambda v:v['score']))
            feature['vlm_requested_on_page']=n in chosen
        else:
            B=int(n in excluded);E=int(n in carried_pages and not B)
            pending=[r for r in rows_by_page[n] if r['state']!='reviewed_source']
            image_ratio=min(1,sum(area(r['bbox_pixels']) for r in pending)/(p['render_width']**2*p['page_size_pt'][1]/p['page_size_pt'][0]))
            U=int(bool(pending) and not E and not B)
            R=int(bool(U) and image_ratio>=POLICY['large_image_ratio'] and contexts[n]['body_characters']<POLICY['sparse_body_characters'])
            terms={'D':0,'C':0,'U':U,'R':R,'B':B,'E':E}
            feature={'has_diagram':False,'has_chart':False,'native_text_coverage':contexts[n]['native_text_coverage'],
                     'image_area_ratio':image_ratio,'is_duplicate':any(r['state']=='exact_duplicate' for r in pending),'specialist_success':bool(E),
                     'terms':terms,'score':score(terms),'decision':decide(terms),
                     'vlm_requested_on_page':False,'evidence':{'note':'No unresolved VLM region; formula/table remain in specialist pipeline or source review.'}}
            if pending and all(r['engine'] in ['formula','table'] for r in pending):feature['decision']='specialist_pending'
        feature['pipeline_destination']='cpt' if n in carried_pages else 'excluded_verified_non_content' if n in excluded else 'review_queue'
        page_features.append({'page':n,'document_sha256':p['document_sha256'],'render_sha256':p['render_sha256'],**feature})
    shutil.copytree(source/'crops',out/'crops',dirs_exist_ok=True)
    config=copy.deepcopy(original_config)
    config['scoring_policy']=POLICY;config['scoring_rules_sha256']=digest(Path(__file__).read_bytes())
    for r in regions:
        identity={'engine':r['engine'],'raw_pixel_sha256':r['raw_pixel_sha256'],
                  'input_pixel_sha256':r['input_pixel_sha256'],'native_ocr':r.get('native_ocr'),'config':config}
        r['cache_key']=digest(json.dumps(identity,sort_keys=True,ensure_ascii=False,separators=(',',':')))
    write_jsonl(out/'regions.jsonl',regions);write_jsonl(out/'region_scores.jsonl',scored)
    write_jsonl(out/'page_features.jsonl',page_features)
    write_jsonl(out/'carried_train.metadata.jsonl',carried)
    for q in original_review:
        q['reasons']=[v for v in q['reasons'] if v not in ['deferred_budget','scheduled']]
        q['reasons']=sorted(set(q['reasons'])|{r['state'] for r in rows_by_page[q['page']] if r['state'] not in ['reviewed_source']})
    write_jsonl(out/'review_queue.jsonl',original_review)
    selected=[r for r in regions if r['state']=='scheduled']
    ratio=len(chosen)/len(pages)
    budget={'policy':'score_only_no_quota','formula':POLICY['formula'],'target_page_ratio':[.04,.08],
            'scheduled_vlm_pages':sorted(chosen),'scheduled_vlm_page_ratio':ratio,
            'within_target_range':.04<=ratio<=.08,'budget_truncated_pages':0,
            'score_review_pages':sorted({r['page'] for r in regions if r['state']=='score_review'})}
    manifest={**m,'schema_version':'region-routing-score-v1','config':config,'budget':budget,
              'requests':selected,'regions_sha256':digest((out/'regions.jsonl').read_bytes()),
              'source_routing_manifest_sha256':digest((source/'manifest.json').read_bytes())}
    dump_json(out/'manifest.json',manifest);dump_json(out/'score_policy.json',POLICY)
    with zipfile.ZipFile(out/'region_input.zip','w',zipfile.ZIP_DEFLATED) as z:
        z.write(out/'manifest.json','manifest.json')
        for r in selected:z.write(out/r['image'],r['image'])
        for name in ['worker.py','prompt.txt','validation.py']:z.write(ROOT/name,name)
    report={**budget,'pages_total':len(pages),'scheduled_requests_by_engine':dict(collections.Counter(r['engine'] for r in selected)),
            'score_histogram_unique_vlm_regions':dict(sorted(collections.Counter(r['routing_features']['score'] for r in regions
                   if r['engine']=='vlm' and r['state'] not in ['exact_duplicate','reviewed_source']).items())),
            'cv_features_unique_crops':len(probes),'native_coverage_definition':next(iter(contexts.values()))['coverage_definition'],
            'review_queue_pages':len(original_review),'carried_train_samples':len(carried),
            'threshold_sweep_diagnostic':{str(t):len({r['page'] for r in regions if r['engine']=='vlm' and
                r['state'] not in ['exact_duplicate','reviewed_source'] and r['routing_features']['score']>=t}) for t in [5,6,7,8]},
            'elapsed_local_seconds':time.perf_counter()-start,'gpu_inference_executed':False,
            'semantic_precision_recall_measured':False,'full_knowledge_coverage_met':False,
            'note':'Rules prioritize automatic VLM. Medium/uncertain figures remain in review; target ratio alone does not prove coverage.'}
    dump_json(out/'scoring_report.json',report);pack(carried,out/'cpt',a.tokenizer)
    notebook=load(ROOT/'IT3170_Region_Routing.ipynb')
    notebook['cells'][0]['source']=['# IT3170 — Rule-based + PP-DocLayout-M, mục tiêu VLM 4–8%\n',
        'S = 4D + 3C + 2U + R - 4B - 3E. Không top-k, không thêm/bớt trang để đủ tỷ lệ.\n',
        'S≥7 → VLM; chart đã có bằng chứng rõ được chọn từ S≥6. Các vùng trung gian/không chắc chắn vào Review Queue.\n',
        'Kiểm tra scoring_report.json và within_target_range trước khi chạy. Chưa có gold độc lập để kết luận đủ kiến thức.\n']
    for cell in notebook['cells']:
        if cell['cell_type']=='code':
            cell['source']=[s.replace('it3170_regions_v4',out.name).replace('BKQuiz_region_preprocessing','BKQuiz_scored_preprocessing') for s in cell['source']]
    notebook['cells'][-1]['source']=['Nhập ZIP kết quả với route.py merge --out đúng thư mục scored.\n',
        'Review Queue giữ hình điểm trung gian, vùng thiếu bằng chứng và lỗi nhận dạng. Điểm cao không thay thế kiểm tra ngữ nghĩa.\n']
    (ROOT/'IT3170_Scored_Routing.ipynb').write_text(json.dumps(notebook,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source-run',type=Path,default=ROOT/'runs/it3170_regions_v4')
    p.add_argument('--layout-root',type=Path,default=BASE/'outputs/it3170')
    p.add_argument('--out',type=Path,default=ROOT/'runs/it3170_scored_v3')
    p.add_argument('--tokenizer',type=Path,default=DEFAULT_TOKENIZER)
    run(p.parse_args())
