"""Optional parsers; source geometry and backend lineage are never inferred by vote.

Imports use only the standard library. Heavy parsers must run in their own process.
Candidate coordinates: page is 1-based, bbox=[left,top,right,bottom] in full-page
0..1000 units. Missing geometry stays None and cannot support region agreement.
Raw files are retained; imports never rewrite them or declare semantic verification.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import importlib.metadata
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import traceback


KINDS = {'text', 'formula', 'table', 'diagram', 'image', 'chart', 'code'}
LABELS = {'equation':'formula', 'interline_equation':'formula', 'inline_formula':'formula',
          'display_formula':'formula', 'isolate_formula':'formula', 'inline_equation':'formula',
          'picture':'image', 'figure':'image', 'graph':'diagram', 'flowchart':'diagram',
          'algorithm':'code', 'code':'code', 'table':'table', 'chart':'chart'}


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def available():
    return {name:{'available':importlib.util.find_spec(module) is not None,
                  'version':package_version(name)}
            for name,module in [('docling','docling'), ('mineru','mineru'),
                                ('python-pptx','pptx'), ('paddleocr','paddleocr')]}


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def _kind(value):
    value = str(value or '').lower()
    return value if value in KINDS else LABELS.get(value, 'text')


def _page(value, base=1):
    if isinstance(base,bool) or base not in (0,1):
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < base:
        return None
    return value + (1 - base)


def normalized_box(box, width=None, height=None, units='pixels', origin='TOPLEFT'):
    """Strict conversion. Invalid/outside/unknown frames return None, never clamp.

    BOTTOMLEFT uses Docling's l,t,r,b semantics: t is the greater Y coordinate.
    """
    if isinstance(box, dict):
        origin = box.get('coord_origin', origin)
        box = [box.get(k) for k in ('l','t','r','b')]
    if not isinstance(box, (list,tuple)) or len(box) != 4:
        return None
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in box):
        return None
    x0,y0,x1,y1 = map(float,box)
    if units == 'normalized_1000':
        width = height = 1000.0
    elif units == 'normalized_1':
        width = height = 1.0
    elif units not in {'pixels','points','emu'}:
        return None
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x <= 0
           for x in (width,height)):
        return None
    if origin == 'BOTTOMLEFT':
        y0,y1 = height-y0,height-y1
    elif origin != 'TOPLEFT':
        return None
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        return None
    return [round(x0/width*1000,5),round(y0/height*1000,5),
            round(x1/width*1000,5),round(y1/height*1000,5)]


def _candidate(*, path, page, bbox, kind, text, engine, order, raw, metadata=None,
               confidence=None, backend_family=None):
    metadata = metadata or {}
    evidence = {'parser_output_file':str(Path(path).resolve()),
                'parser_output_sha256':file_hash(path), 'reading_order':order,
                'parser':engine, 'parser_version':metadata.get('version'),
                'source_sha256':metadata.get('source_sha256'),
                'source_file':metadata.get('source_file'),
                'backend_family':backend_family or metadata.get('backend_family',engine),
                'geometry_status':'known' if bbox is not None else 'unknown_or_invalid',
                'original':raw, 'semantic_verified':False}
    return {'page':page,'bbox':bbox,'kind':_kind(kind),'text':str(text or ''),
            'engine':engine,'status':'ok' if page is not None else 'error',
            'confidence':confidence if isinstance(confidence,(int,float)) and not isinstance(confidence,bool)
                          and math.isfinite(confidence) and 0<=confidence<=1 else None,
            'evidence':evidence}


def _resolve(document, ref):
    if not isinstance(ref,dict) or not isinstance(ref.get('$ref'),str):
        return ref if isinstance(ref,dict) else None
    value = document
    try:
        for part in ref['$ref'].removeprefix('#/').split('/'):
            part=part.replace('~1','/').replace('~0','~')
            value=value[int(part)] if isinstance(value,list) else value[part]
        return value
    except (KeyError,ValueError,IndexError,TypeError):
        return None


def _docling_order(document):
    seen=set()
    ordered=[]
    def walk(item):
        item=_resolve(document,item)
        if not isinstance(item,dict) or id(item) in seen:
            return
        seen.add(id(item))
        if item.get('prov'):
            ordered.append(item)
        for child in item.get('children',[]):
            walk(child)
    walk(document.get('body',{}))
    walk(document.get('furniture',{}))
    # Preserve otherwise-orphaned elements; flag order source instead of dropping.
    for name in ('texts','tables','pictures','groups'):
        for item in document.get(name,[]):
            walk(item)
    return ordered


def _table_html(data):
    cells=data.get('table_cells',[])
    if not cells:
        return ''
    rows={}
    for cell in cells:
        row=cell.get('start_row_offset_idx')
        col=cell.get('start_col_offset_idx')
        if not isinstance(row,int) or not isinstance(col,int):
            continue
        row_span=cell.get('row_span',1)
        col_span=cell.get('col_span',1)
        tag='th' if cell.get('column_header') or cell.get('row_header') else 'td'
        attrs=''
        for label,value in [('rowspan',row_span),('colspan',col_span)]:
            if isinstance(value,int) and not isinstance(value,bool) and value>1:
                attrs+=f' {label}="{value}"'
        rows.setdefault(row,[]).append((col,f'<{tag}{attrs}>{html.escape(str(cell.get("text","")))}</{tag}>'))
    return '<table>'+''.join('<tr>'+''.join(c for _,c in sorted(rows[r]))+'</tr>' for r in sorted(rows))+'</table>'


def import_docling(path:Path)->list[dict]:
    payload=_read(path)
    document=payload.get('document',payload)
    metadata=payload.get('metadata',{})
    metadata.setdefault('backend_family','docling_native_layout' if metadata.get('do_ocr') is False else 'docling_backend_unspecified')
    pages=document.get('pages',{})
    records=[]
    for order,item in enumerate(_docling_order(document)):
        text=item.get('text','')
        if item.get('label')=='table':
            text=item.get('html') or _table_html(item.get('data',{})) or text
        for prov_i,prov in enumerate(item.get('prov',[])):
            page=_page(prov.get('page_no'))
            page_info=pages.get(str(page),{}) if isinstance(pages,dict) else next((p for p in pages if p.get('page_no')==page),{})
            size=page_info.get('size',{})
            box=normalized_box(prov.get('bbox'),size.get('width'),size.get('height'),units='points')
            part=text
            span=prov.get('charspan')
            # Multi-page paragraph text must not be duplicated onto every page.
            if len(item.get('prov',[]))>1:
                if isinstance(span,list) and len(span)==2 and all(isinstance(i,int) for i in span) and 0<=span[0]<=span[1]<=len(text):
                    part=text[span[0]:span[1]]
                else:
                    box=None;part=''
            records.append(_candidate(path=path,page=page,bbox=box,kind=item.get('label'),text=part,
                engine='docling',order=order,raw={'self_ref':item.get('self_ref'),'provenance':prov,
                    'provenance_index':prov_i,'table_data':item.get('data') if item.get('label')=='table' else None},metadata=metadata))
    return records


def import_mineru(path:Path)->list[dict]:
    """Legacy content_list plus explicit modern block envelopes.

    Legacy content_list page_idx is zero-based and bbox is normalized 0..1000.
    Other schemas MUST declare coordinates/page_base; values alone cannot reveal
    whether [0,0,1,1] is pixels or normalized. Unknown geometry stays None.
    """
    payload=_read(path)
    modern=payload.get('document',payload) if isinstance(payload,dict) else payload
    if isinstance(modern,dict) and modern.get('schema')=='docvortex.middle':
        return _import_docvortex(path,modern,payload.get('metadata',{}))
    metadata=payload.get('metadata',{}) if isinstance(payload,dict) else {}
    if isinstance(payload,list):
        blocks=payload; legacy=True
    elif isinstance(payload,dict) and isinstance(payload.get('content_list'),list):
        blocks=payload['content_list'];legacy=True
    elif isinstance(payload,dict) and isinstance(payload.get('blocks'),list):
        blocks=payload['blocks'];legacy=False
    else:
        raise ValueError('Unsupported MinerU schema. Export content_list.json or explicit blocks+metadata; retain raw output.')
    metadata.setdefault('backend_family','mineru_pipeline_paddle' if metadata.get('backend')=='pipeline' else 'mineru_backend_unspecified')
    records=[]
    for order,item in enumerate(blocks):
        page=_page(item.get('page_idx'),base=0) if legacy else _page(item.get('page'),base=metadata.get('page_base',1))
        units='normalized_1000' if legacy else metadata.get('coord_system','unknown')
        box=normalized_box(item.get('bbox'),item.get('page_width'),item.get('page_height'),units=units)
        kind=item.get('type',item.get('kind','text'))
        text=item.get('text','')
        if kind=='table':
            text=item.get('table_body') or item.get('html') or text
        elif kind=='image':
            # Captions remain observations by the parser, not invented semantics.
            text='\n'.join(str(s) for s in item.get('image_caption',[]) if isinstance(s,str))
        if kind in ('equation','interline_equation'):
            text=item.get('latex') or text
        records.append(_candidate(path=path,page=page,bbox=box,kind=kind,text=text,engine='mineru',order=order,
            raw={'block':item,'coord_system':units,'page_base':0 if legacy else metadata.get('page_base',1)},metadata=metadata))
    return records


def _import_docvortex(path,document,envelope):
    """MinerU 4 MiddleJson protocol 2.0 (not CLI status JSON or ModelJson).

    Official contract: extensions.docvortex_layout version1 pages stores source
    page_idx and width_pt/height_pt in the same orientation as block bbox.
    No layout extension means no geometric cross-validation, even if bbox exists.
    """
    if document.get('schema_version')!='2.0':
        raise ValueError('Unsupported DocVortex MiddleJson protocol; preserve raw file for review')
    meta=dict(document.get('metadata',{}));meta.update(envelope)
    producer=document.get('metadata',{}).get('producer',{})
    meta['version']=producer.get('version')
    extensions=document.get('extensions',{})
    miner=extensions.get('mineru',{})
    tier=miner.get('tier','unspecified');parse_mode=miner.get('parse_mode','unspecified')
    meta['backend_family']=f'mineru_{tier}_{parse_mode}'
    layout=extensions.get('docvortex_layout',{})
    sizes={}
    if layout.get('version')==1:
        for p in layout.get('pages',[]):
            idx=p.get('page_idx')
            if _page(idx,0) is not None:
                sizes[idx]=p
    def content_text(value):
        if isinstance(value,str):
            return value
        if isinstance(value,list):
            return ''.join(content_text(v) for v in value)
        if isinstance(value,dict):
            return content_text(value.get('content',''))
        return ''
    records=[]
    for source_page in document.get('pages',[]):
        idx=source_page.get('page_idx');page=_page(idx,0);size=sizes.get(idx,{})
        def emit(block,path_in_page):
            block_type=block.get('type','text');content=block.get('content','')
            if block_type in {'list','index'} and isinstance(content,list):
                # Children already have spatial identity; do not repeat all list
                # text on a parent candidate and create spurious agreement.
                for i,child in enumerate(content):
                    if isinstance(child,dict):
                        emit(child,path_in_page+[i])
                return
            if block_type in {'image','table','chart','code'} and isinstance(content,list):
                body_types={'image_body','table_body','chart_body','code_body','algorithm_body'}
                text='\n'.join(content_text(c) for c in content if isinstance(c,dict) and c.get('type') in body_types)
            else:
                text=content_text(content)
            box=normalized_box(block.get('bbox'),size.get('width_pt'),size.get('height_pt'),units='points')
            records.append(_candidate(path=path,page=page,bbox=box,kind=block_type,text=text,engine='mineru',
                order=len(records),raw={'block':block,'block_path':path_in_page,'layout_page':size,
                    'schema':'docvortex.middle','schema_version':'2.0','tier':tier,'parse_mode':parse_mode},metadata=meta))
            if block_type in {'image','table','chart','code'} and isinstance(content,list):
                for i,child in enumerate(content):
                    if isinstance(child,dict) and str(child.get('type','')).endswith(('_caption','_footnote')):
                        emit(child,path_in_page+[i])
        for i,block in enumerate(source_page.get('blocks',[])):
            emit(block,[i])
    return records


def _crop_map(box,crop):
    if box is None or crop is None:
        return None
    if normalized_box(crop,units='normalized_1000') is None:
        return None
    x0,y0,x1,y1=crop
    return [round(x0+box[0]*(x1-x0)/1000,5),round(y0+box[1]*(y1-y0)/1000,5),
            round(x0+box[2]*(x1-x0)/1000,5),round(y0+box[3]*(y1-y0)/1000,5)]


def import_paddle(path:Path)->list[dict]:
    payload=_read(path)
    items=payload if isinstance(payload,list) else payload.get('records',[payload])
    records=[]
    for item_i,item in enumerate(items):
        if 'candidates' in item:
            # Worker-owned candidates already have normalized full-slide coords.
            for c in item['candidates']:
                c=dict(c);c['evidence']=dict(c.get('evidence',{}))
                c['evidence'].update(parser_output_file=str(Path(path).resolve()),parser_output_sha256=file_hash(path))
                c['evidence']['semantic_verified']=False
                if normalized_box(c.get('bbox'),units='normalized_1000') is None:
                    c['bbox']=None;c['evidence']['geometry_status']='unknown_or_invalid'
                if _page(c.get('page')) is None:
                    c['page']=None;c['status']='error'
                records.append(c)
            continue
        res=item.get('res',item)
        metadata=item.get('metadata',payload.get('metadata',{}) if isinstance(payload,dict) else {})
        page=_page(metadata.get('page'))
        if page is None and res.get('page_index') is not None:
            page=_page(res['page_index'],base=0)
        width=metadata.get('image_width') or res.get('width')
        height=metadata.get('image_height') or res.get('height')
        crop=metadata.get('crop_bbox')
        is_full_page=metadata.get('is_full_page') is True
        for order,block in enumerate(res.get('parsing_res_list',[])):
            box=normalized_box(block.get('block_bbox'),width,height)
            if crop is not None:
                box=_crop_map(box,crop)
            elif not is_full_page:
                box=None
            records.append(_candidate(path=path,page=page,bbox=box,kind=block.get('block_label'),
                text=block.get('block_content',''),engine='paddle_structure',order=order,
                raw={'block':block,'frame':metadata},metadata=metadata,backend_family='paddle_structure'))
        # OCR-only native output. Do not duplicate it if Structure already emitted text.
        if not res.get('parsing_res_list'):
            ocr=res.get('overall_ocr_res',res)
            for order,text in enumerate(ocr.get('rec_texts',[])):
                boxes=ocr.get('rec_boxes',[]);polys=ocr.get('rec_polys',[])
                b=boxes[order] if order<len(boxes) else None
                if b is None and order<len(polys) and polys[order]:
                    poly=polys[order];b=[min(p[0] for p in poly),min(p[1] for p in poly),max(p[0] for p in poly),max(p[1] for p in poly)]
                box=normalized_box(b,width,height)
                box=_crop_map(box,crop) if crop is not None else box if is_full_page else None
                scores=ocr.get('rec_scores',[])
                records.append(_candidate(path=path,page=page,bbox=box,kind='text',text=text,engine='paddle_ocr',order=order,
                    confidence=scores[order] if order<len(scores) else None,raw={'box':b,'item_index':item_i},
                    metadata=metadata,backend_family='paddle_ocr'))
            # Standalone formula/table outputs need an explicit source frame.
            if isinstance(res.get('rec_formula'),str):
                box=crop if normalized_box(crop,units='normalized_1000') is not None else [0,0,1000,1000] if is_full_page else None
                records.append(_candidate(path=path,page=page,bbox=box,kind='formula',text=res['rec_formula'],
                    engine='paddle_formula',order=0,raw={'frame':metadata,'result':res},metadata=metadata,backend_family='paddle_formula'))
            for order,table in enumerate(res.get('table_res_list',[])):
                box=normalized_box(table.get('bbox',table.get('table_bbox')),width,height)
                box=_crop_map(box,crop) if crop is not None else box if is_full_page else None
                records.append(_candidate(path=path,page=page,bbox=box,kind='table',text=table.get('pred_html',''),
                    engine='paddle_table',order=order,raw={'table':table,'frame':metadata},metadata=metadata,backend_family='paddle_table'))
    return records


def _write_new(path,payload):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:
        json.dump(payload,f,ensure_ascii=False,indent=2,allow_nan=False)


def run_docling(input_path,out_json,*,do_ocr=False,page_range=None):
    """Call in a separate Docling venv; defaults native layout to avoid fake OCR independence."""
    input_path=Path(input_path);out_json=Path(out_json)
    if out_json.exists():
        raise FileExistsError(out_json)
    started=time.perf_counter()
    metadata={'source_file':str(input_path.resolve()),'source_sha256':file_hash(input_path),
              'version':package_version('docling'),'do_ocr':do_ocr,
              'backend_family':'docling_default_ocr' if do_ocr else 'docling_native_layout'}
    try:
        from docling.document_converter import DocumentConverter,PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        options=PdfPipelineOptions(do_ocr=do_ocr,do_table_structure=True,
                                   do_formula_enrichment=False,do_code_enrichment=False)
        converter=DocumentConverter(format_options={InputFormat.PDF:PdfFormatOption(pipeline_options=options)})
        kwargs={'page_range':tuple(page_range)} if page_range is not None else {}
        result=converter.convert(str(input_path),**kwargs)
        payload={'status':'ok','metadata':metadata,'document':result.document.export_to_dict()}
    except ModuleNotFoundError as exc:
        payload={'status':'unavailable','metadata':metadata,'error':str(exc),'traceback':traceback.format_exc()}
    except Exception as exc:
        payload={'status':'error','metadata':metadata,'error':str(exc),'traceback':traceback.format_exc()}
    payload['elapsed_seconds']=time.perf_counter()-started
    _write_new(out_json,payload)
    return payload


def mineru_command(executable,input_path,out_dir,help_text,*,backend='pipeline'):
    """Support documented legacy parse flags or modern stateless mineru-kit.

    Do not silently switch to a server/default VLM backend or truncate pages.
    """
    executable=str(executable)
    if '--path' in help_text and '--output' in help_text and '--backend' in help_text:
        return [executable,'-p',str(input_path),'-o',str(out_dir),'-b',backend]
    if 'parse' in help_text and 'mineru-kit' in help_text:
        if backend!='standard':
            raise ValueError('Modern MinerU uses --tier standard, not legacy backend=pipeline. Select backend=standard explicitly.')
        return [executable,'parse',str(input_path),'-o',str(out_dir),'--format','zip','--tier','standard']
    raise ValueError('Unrecognized MinerU CLI. Read --help; do not guess flags or change backend.')


def run_mineru(input_path,out_dir,*,executable='mineru',backend='pipeline',timeout=3600):
    input_path=Path(input_path);out_dir=Path(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError('MinerU output directory must be new/empty')
    out_dir.mkdir(parents=True,exist_ok=True)
    payload={'source_file':str(input_path.resolve()),'source_sha256':file_hash(input_path),'backend':backend,
             'semantic_verified':False,'status':'pending'}
    try:
        probe=subprocess.run([str(executable),'--help'],capture_output=True,text=True,timeout=30,check=True)
        (out_dir/'cli_help.txt').write_text(probe.stdout+'\n'+probe.stderr,encoding='utf-8')
        command=mineru_command(executable,input_path,out_dir/'raw',probe.stdout+'\n'+probe.stderr,backend=backend)
        if 'parse' in command:
            subhelp=subprocess.run([str(executable),'parse','--help'],capture_output=True,text=True,timeout=30,check=True)
            (out_dir/'parse_help.txt').write_text(subhelp.stdout+'\n'+subhelp.stderr,encoding='utf-8')
            if not all(flag in subhelp.stdout+subhelp.stderr for flag in ('--format','--tier','--output')):
                raise ValueError('MinerU parse CLI lacks required export/tier flags')
        payload['command']=command
        result=subprocess.run(command,capture_output=True,text=True,timeout=timeout,check=False)
        (out_dir/'stdout.txt').write_text(result.stdout,encoding='utf-8')
        (out_dir/'stderr.txt').write_text(result.stderr,encoding='utf-8')
        payload.update(status='ok' if result.returncode==0 else 'error',returncode=result.returncode,
                       note='Import structured JSON with explicit coordinates; Markdown alone cannot validate region agreement.')
    except FileNotFoundError as exc:
        payload.update(status='unavailable',error=str(exc),traceback=traceback.format_exc())
    except Exception as exc:
        payload.update(status='error',error=str(exc),traceback=traceback.format_exc())
    _write_new(out_dir/'run.json',payload)
    return payload


def extract_pptx(path:Path)->list[dict]:
    """Read original shapes/tables in EMU; does not render or invent diagram semantics.

    Nontrivial grouped/rotated shapes keep unknown geometry, so they cannot create
    false PDF/PPTX matches. Original drawing order is retained, not called reading order.
    """
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    deck=Presentation(str(path));records=[]
    metadata={'version':package_version('python-pptx'),'source_sha256':file_hash(path),
              'source_file':str(Path(path).resolve()),'backend_family':'native_office'}
    for page,slide in enumerate(deck.slides,1):
        order=0
        def walk(shapes,in_group=False):
            nonlocal order
            for shape in shapes:
                if shape.shape_type==MSO_SHAPE_TYPE.GROUP:
                    walk(shape.shapes,True);continue
                b=[shape.left,shape.top,shape.left+shape.width,shape.top+shape.height]
                box=None if in_group or shape.rotation else normalized_box(b,deck.slide_width,deck.slide_height,units='emu')
                kind='table' if shape.has_table else 'text' if shape.has_text_frame else 'chart' if shape.has_chart else 'image'
                if shape.has_table:
                    table_rows=[]
                    for row in shape.table.rows:
                        cells=[]
                        for c in row.cells:
                            if c.is_spanned:
                                continue
                            attrs=''
                            if c.is_merge_origin:
                                if c.span_height>1:attrs+=f' rowspan="{c.span_height}"'
                                if c.span_width>1:attrs+=f' colspan="{c.span_width}"'
                            cells.append('<td'+attrs+'>'+html.escape(c.text)+'</td>')
                        table_rows.append('<tr>'+''.join(cells)+'</tr>')
                    text='<table>'+''.join(table_rows)+'</table>'
                elif shape.has_chart:
                    chart=shape.chart
                    data={'title':chart.chart_title.text_frame.text if chart.has_title else None,
                          'series':[{'name':s.name,'values':list(s.values)} for s in chart.series]}
                    # Category labels belong to each plot in combination charts.
                    data['plots']=[{'categories':[str(c.label) for c in plot.categories]} for plot in chart.plots]
                    text=json.dumps(data,ensure_ascii=False,allow_nan=False)
                else:
                    text=shape.text if shape.has_text_frame else ''
                records.append(_candidate(path=path,page=page,bbox=box,kind=kind,text=text,engine='native_pptx',order=order,
                    raw={'shape_id':shape.shape_id,'name':shape.name,'bbox_emu':b,'grouped':in_group,'rotation':shape.rotation,
                         'order_semantics':'drawing_order','pptx_to_pdf_alignment':'must_be_verified'},metadata=metadata))
                order+=1
        walk(slide.shapes)
    return records


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation',choices=['available','import-docling','import-mineru','import-paddle','extract-pptx','run-docling','run-mineru'])
    p.add_argument('--input',type=Path);p.add_argument('--out',type=Path)
    p.add_argument('--ocr',action='store_true');p.add_argument('--pages',type=int,nargs=2)
    p.add_argument('--mineru-executable',default='mineru');p.add_argument('--backend',default='pipeline',help='Legacy: pipeline. Modern mineru-kit: standard (explicit tier, not the legacy backend).')
    a=p.parse_args()
    if a.operation=='available':
        print(json.dumps(available(),indent=2));return
    if a.input is None or a.out is None:
        p.error('--input and --out required')
    if a.operation=='run-docling':
        result=run_docling(a.input,a.out,do_ocr=a.ocr,page_range=a.pages)
    elif a.operation=='run-mineru':
        result=run_mineru(a.input,a.out,executable=a.mineru_executable,backend=a.backend)
    else:
        fn={'import-docling':import_docling,'import-mineru':import_mineru,'import-paddle':import_paddle,'extract-pptx':extract_pptx}[a.operation]
        records=fn(a.input);_write_new(a.out,records);result={'status':'ok','candidate_count':len(records)}
    print(json.dumps({k:v for k,v in result.items() if k!='document'},ensure_ascii=False,indent=2))
    return 0 if result.get('status')=='ok' else 2


if __name__=='__main__':
    sys.exit(main())
