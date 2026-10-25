"""Native PDF cell text adapter for PaddleOCR 3.7.0 / PaddleX 3.7.2."""
from pathlib import Path


def native_ocr_result(path, cells):
    import cv2
    import numpy as np
    from paddlex.inference.pipelines.ocr.result import OCRResult
    image=cv2.imread(str(path))
    if image is None:raise ValueError('Cannot read table crop')
    if not cells:raise ValueError('No native cell text; OCR/manual review required')
    boxes=np.asarray([v['bbox'] for v in cells],dtype=np.float32)
    if boxes.ndim!=2 or boxes.shape[1]!=4 or not np.isfinite(boxes).all():
        raise ValueError('Invalid native cell geometry')
    height,width=image.shape[:2]
    if np.any(boxes[:,:2]<0) or np.any(boxes[:,2]>width+.01) or np.any(boxes[:,3]>height+.01):
        raise ValueError('Native cell bbox outside crop')
    if np.any(boxes[:,2:]<=boxes[:,:2]):raise ValueError('Degenerate cell geometry')
    polys=np.asarray([[[b[0],b[1]],[b[2],b[1]],[b[2],b[3]],[b[0],b[3]]] for b in boxes])
    return OCRResult({
        'input_path':str(Path(path)),'page_index':None,
        'doc_preprocessor_res':{'output_img':image},
        'model_settings':{'use_doc_preprocessor':False,'use_textline_orientation':False},
        'text_det_params':{},'text_type':'general','text_rec_score_thresh':0.0,
        'return_word_box':False,'rec_texts':[v['text'] for v in cells],
        'rec_boxes':boxes,'rec_polys':polys,'dt_polys':polys,
        'rec_scores':np.ones(len(boxes),dtype=np.float32),
    })


def create_pipeline(device):
    from paddleocr import TableRecognitionPipelineV2
    opts={'device':device,'use_doc_orientation_classify':False,'use_doc_unwarping':False,
          'use_layout_detection':False,'use_ocr_model':False}
    if device=='cpu':opts.update(enable_mkldnn=False,cpu_threads=4)
    return TableRecognitionPipelineV2(**opts)


def predict_table(pipeline,path,cells):
    # Rotation/dewarping must remain off: supplied boxes use the original crop.
    result=next(iter(pipeline.predict(str(path),overall_ocr_res=native_ocr_result(path,cells),
        use_doc_orientation_classify=False,use_doc_unwarping=False,
        use_ocr_model=False,use_layout_detection=False,use_table_orientation_classify=False)))
    html='\n'.join(t.get('pred_html','') for t in result.get('table_res_list',[]))
    return {'html':html,'text_source':'native_pdf',
            'note':'Native geometry scores=1 are API placeholders, not OCR confidence.'}
