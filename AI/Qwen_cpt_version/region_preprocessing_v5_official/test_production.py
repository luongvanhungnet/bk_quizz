import io
import tempfile
from pathlib import Path
import unittest
import pymupdf
from PIL import Image
from prepare import prepare
from package_cloud import package
from io_utils import load,jsonl,file_sha,write_jsonl

def make_pdf(path,pages=2):
    image=io.BytesIO();Image.new('RGB',(24,24),'blue').save(image,format='PNG')
    doc=pymupdf.open()
    for _ in range(pages):
        page=doc.new_page(width=300,height=200)
        page.insert_image(pymupdf.Rect(30,20,160,120),stream=image.getvalue())
        page.insert_image(pymupdf.Rect(180,20,270,120),stream=image.getvalue())
        page.insert_text((40,50),'Alpha x = 2')
    doc.save(path);doc.close()

class ProductionPreparation(unittest.TestCase):
    def test_generic_repeated_image_has_unique_region_ids_and_native_context(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);make_pdf(root/'source.pdf');prepare(root/'source.pdf',root/'run')
            rows=jsonl(root/'run/records.jsonl')
            self.assertEqual(len({r['id'] for r in rows}),len(rows))
            self.assertTrue(any(r['kind']=='diagram' and 'Alpha' in r['native_text'] for r in rows))
            m=load(root/'run/manifest.json');self.assertEqual(m['pilot_pages'],[1,2])
            self.assertEqual(m['layout_inventory_status'],'requires_layout_enrichment')
    def test_shard_preserves_original_pdf_and_page_mapping(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);make_pdf(root/'source.pdf');prepare(root/'source.pdf',root/'run')
            package(root/'run',root/'packet',scope='all',page_numbers=[2])
            m=load(root/'packet/manifest.json')
            self.assertEqual(m['document']['sha256'],file_sha(root/'source.pdf'))
            self.assertEqual(m['page_map'],{'1':2});self.assertEqual({r['page'] for r in m['requests']},{2})
            with pymupdf.open(root/'packet/parser_input.pdf') as pdf:self.assertEqual(pdf.page_count,1)
    def test_changed_source_fails_before_writing_packet(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);make_pdf(root/'source.pdf');prepare(root/'source.pdf',root/'run')
            (root/'source.pdf').write_bytes(b'changed')
            with self.assertRaises(ValueError):package(root/'run',root/'packet')
            self.assertFalse((root/'packet').exists())
    def test_empty_or_invalid_source_page_selection_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);make_pdf(root/'source.pdf');prepare(root/'source.pdf',root/'run')
            for i,selection in enumerate([[],[0],[3],[True]]):
                with self.assertRaises(ValueError):package(root/'run',root/f'packet{i}',scope='all',page_numbers=selection)
    def test_cached_specialist_failure_is_deferred_without_blind_rerun(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);make_pdf(root/'source.pdf');prepare(root/'source.pdf',root/'run')
            rows=jsonl(root/'run/records.jsonl');r=rows[0];r['kind']='formula'
            r['candidates'].append({'engine':'paddle_formula','status':'error','text':'bad',
                'evidence':{'reuse_only':True,'input_file_sha256':r['crop_sha256']}})
            write_jsonl(root/'run/records.jsonl',rows);package(root/'run',root/'packet',scope='all',page_numbers=[1])
            q=next(q for q in load(root/'packet/manifest.json')['requests'] if q['id']==r['id'])
            self.assertTrue(q['skip_specialist']);self.assertTrue(q['specialist_cached_failure_deferred'])

if __name__=='__main__':unittest.main()
