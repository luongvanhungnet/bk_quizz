import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from common import latex_check, normalize, redact
from extract import line_text, reading_order
from build_dataset import find_duplicates
from pack_qwen import pack_records


def test_normalization_preserves_math_vietnamese_and_code():
    assert normalize('Tiếng Việt  n ≤ 10^{18}; a[i] != 0; ∑ xᵢ') == 'Tiếng Việt n ≤ 10^{18}; a[i] != 0; ∑ xᵢ'
    assert normalize('  if (a[i] <= 10) {\n    ++i;\n  }', code=True).startswith('  if')


def test_pii_does_not_erase_algorithm_numbers():
    text, events = redact('n=1000000000; phone: +84 912 345 678; a@hust.edu.vn; MSSV: 20201234')
    assert 'n=1000000000' in text
    assert '912 345' not in text and '20201234' not in text and '@' not in text
    assert len(events) == 3
    assert all('value' not in e for e in events)


def test_coordinate_spacing_and_superscript_not_1018():
    def span(text, x, size=10, flags=0):
        return {'font': 'Test', 'size': size, 'flags': flags, 'origin': [x,10], 'bbox': [x,0,x+len(text)*5,10],
                'chars': [{'c': c, 'bbox': [x+i*5,0,x+(i+1)*5,10]} for i,c in enumerate(text)]}
    text, _ = line_text({'spans': [span('Sử',0), span('dụng',14)]}, False)
    assert text == 'Sử dụng'
    text, _ = line_text({'spans': [span('10',0), span('18',10,7,1)]}, False)
    assert text == '10^{18}'


def test_two_columns_read_top_to_bottom_with_heading():
    def b(name, box): return {'text': name, 'bbox': box, 'font_size': 10}
    rows = [b('R2',[180,130,260,145]), b('L2',[0,130,80,145]), b('H',[0,0,260,20]),
            b('R1',[180,100,260,115]), b('L1',[0,100,80,115])]
    assert [r['text'] for r in reading_order(rows)] == ['H','L1','L2','R1','R2']


def test_dedup_preserves_changed_numeric_formula():
    text = 'Quy hoạch động với điều kiện chỉ số i và j. ' * 10
    rows = [{'id':'a','page':1,'text':text+'n <= 10'}, {'id':'b','page':2,'text':text+'n <= 11'},
            {'id':'c','page':3,'text':text+'n <= 10'}]
    find_duplicates(rows)
    assert rows[1]['duplicate_of'] is None
    assert rows[2]['duplicate_of'] == 'a'


def test_invalid_latex_never_passes_semantic_verification():
    assert not latex_check(r'\frac{a}{b')['syntax_valid']
    assert latex_check(r'10^{18}')['syntax_valid']
    assert not latex_check(r'10^{18}')['semantic_verified']


def test_code_lines_in_separate_pdf_blocks_keep_indentation():
    import pymupdf
    from extract import native_blocks
    doc = pymupdf.open()
    page = doc.new_page()
    for x,y,text in [(30,40,'int main(){'), (54,60,'if (n > 0) {'), (78,80,'++n;'), (54,100,'}'), (30,120,'}')]:
        page.insert_text((x,y), text, fontname='cour', fontsize=10)
    blocks = native_blocks(page)
    assert len(blocks) == 1
    assert blocks[0]['text'] == 'int main(){\n    if (n > 0) {\n        ++n;\n    }\n}'


def test_packing_preserves_all_tokens_eos_labels_and_source_mapping():
    rows = [{'id':'a','page':1,'text':'abcd'}, {'id':'b','page':2,'text':'efgh'}]
    packs = list(pack_records(rows, lambda x: [ord(c) for c in x], 99, 3))
    assert [i for p in packs for i in p['input_ids']] == [97,98,99,100,99,101,102,103,104,99]
    for p in packs:
        assert p['labels'] == p['input_ids'] and p['attention_mask'] == [1]*len(p['input_ids'])
        assert sum(s['token_end']-s['token_start'] for s in p['source_spans']) == len(p['input_ids'])


def test_stale_visual_annotation_cannot_override_source(tmp_path):
    from build_dataset import build
    from common import dump_json, write_jsonl, read_jsonl
    doc = {'path': 'source.pdf', 'sha256': 'sha', 'course': 'test', 'course_code': 'IT3170'}
    page = {'id':'p1','document_id':'doc','page':1,'page_size_pt':[100,100], 'document_sha256':'sha',
            'render_sha256':'image','render_path':'assets/1.png','render_width':100,'original_source':{'source_page':1},
            'blocks':[], 'images':[], 'vector_regions':[], 'native_text_chars':0}
    dump_json(tmp_path/'document.json', doc)
    write_jsonl(tmp_path/'native_pages.jsonl', [page])
    ann = tmp_path/'ann.jsonl'
    write_jsonl(ann, [{'page':1, 'verified':True,'reviewer':'test','evidence':'test','text':'invented',
                      'document_sha256':'WRONG','render_sha256':'image'}])
    build(tmp_path, ann)
    assert read_jsonl(tmp_path/'cpt/train.jsonl') == []
    assert read_jsonl(tmp_path/'normalized.jsonl')[0]['quality']['status'] == 'needs_review'


def test_dataset_integration_invariants():
    from common import read_jsonl
    out = Path(__file__).resolve().parents[1]/'outputs/it3170'
    if not (out/'normalized.jsonl').exists():
        pytest.skip('Run extraction and dataset builder first')
    rows = read_jsonl(out/'normalized.jsonl')
    assert len(rows) == 1060 and len({r['page'] for r in rows}) == 1060
    accepted = read_jsonl(out/'cpt/train.metadata.jsonl')
    assert len({r['exact_hash'] for r in accepted}) == len(accepted)
    assert all(r['quality']['status'] == 'accepted' and not r['quality']['flags'] for r in accepted)
    assert all(r['source']['original'] and r['source']['document_sha256'] for r in rows)
    assert all('@' not in r['text'] or 'include' in r['text'] for r in accepted)
    assert not read_jsonl(out/'cpt/validation.jsonl') and not read_jsonl(out/'cpt/test.jsonl')


def test_formula_detector_cannot_replace_native_source_code(tmp_path):
    from build_dataset import build
    from common import dump_json, write_jsonl, read_jsonl
    dump_json(tmp_path/'document.json', {'path':'source.pdf','sha256':'sha','course':'test','course_code':'IT3170'})
    code = {'id':'b1','type':'code','bbox':[10,20,90,80], 'text':'for(int i=0; i<n; ++i){\n    a[i] = i + 10;\n}',
            'math_candidate':False,'extraction_method':'native_pdf','confidence':{'score':None}}
    page = {'id':'p1','document_id':'doc','page':1,'page_size_pt':[100,100], 'document_sha256':'sha',
            'render_sha256':'image','render_path':'assets/1.png','render_width':100,
            'original_source':{'source_page':1},'blocks':[code], 'images':[], 'vector_regions':[], 'native_text_chars':100}
    write_jsonl(tmp_path/'native_pages.jsonl',[page])
    dump_json(tmp_path/'ppstructure/page_0001.json',{'status':'ok','document_sha256':'sha','render_sha256':'image',
              'result':{'formula_res_list':[{'rec_formula':r'\mathrm{for}', 'dt_polys':[20,30,80,40]}]}})
    build(tmp_path,None)
    row=read_jsonl(tmp_path/'normalized.jsonl')[0]
    assert row['quality']['status']=='accepted'
    assert not row['formulas'] and row['ignored_predictions'][0]['reason']=='overlaps_native_code'


def test_every_unrecognized_math_region_is_retained(tmp_path):
    from build_dataset import build
    from common import dump_json, write_jsonl, read_jsonl
    dump_json(tmp_path/'document.json',{'path':'source.pdf','sha256':'sha','course':'test','course_code':'IT3170'})
    blocks=[{'id':f'b{i}','type':'text','bbox':[10,20+i*30,80,30+i*30],'text':f'x_{{{i}}} = 10',
             'math_candidate':True,'extraction_method':'native','confidence':{'score':None}} for i in [0,1]]
    page={'id':'p1','document_id':'doc','page':1,'page_size_pt':[100,100],'document_sha256':'sha',
          'render_sha256':'image','render_path':'assets/1.png','render_width':100,
          'original_source':{'source_page':1},'blocks':blocks,'images':[],'vector_regions':[],'native_text_chars':100}
    write_jsonl(tmp_path/'native_pages.jsonl',[page])
    build(tmp_path,None)
    assert len(read_jsonl(tmp_path/'formulas.jsonl'))==2
    assert not read_jsonl(tmp_path/'cpt/train.jsonl')


def test_review_can_reject_a_false_positive_table(tmp_path):
    from build_dataset import build
    from common import dump_json, write_jsonl, read_jsonl
    dump_json(tmp_path/'document.json',{'path':'source.pdf','sha256':'sha','course':'test','course_code':'IT3170'})
    page={'id':'p1','document_id':'doc','page':1,'page_size_pt':[100,100],'document_sha256':'sha',
          'render_sha256':'image','render_path':'assets/1.png','render_width':100,
          'original_source':{'source_page':1},'blocks':[],'images':[],'vector_regions':[],'native_text_chars':0}
    write_jsonl(tmp_path/'native_pages.jsonl',[page])
    dump_json(tmp_path/'ppstructure/page_0001.json',{'status':'ok','document_sha256':'sha','render_sha256':'image',
              'result':{'table_res_list':[{'pred_html':'<table><tr><td>wrong</td></tr></table>'}]}})
    ann=tmp_path/'ann.jsonl'
    write_jsonl(ann,[{'page':1,'verified':True,'reviewer':'visual','evidence':'image checked','text':'A paragraph in a colored panel.',
                     'document_sha256':'sha','render_sha256':'image','tables':[]}])
    build(tmp_path,ann)
    row=read_jsonl(tmp_path/'normalized.jsonl')[0]
    assert row['quality']['status']=='accepted' and row['tables']==[]
    assert len(read_jsonl(tmp_path/'cpt/train.jsonl'))==1
