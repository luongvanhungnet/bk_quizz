import ast
import json
from pathlib import Path
import unittest

class NotebookTests(unittest.TestCase):
    def setUp(self):
        self.nb=json.loads(Path(__file__).with_name('Colab_Region_Preprocessing_V5.ipynb').read_text(encoding='utf-8'))
        self.cells=[ ''.join(c['source']) for c in self.nb['cells'] if c['cell_type']=='code']
    def test_all_cells_compile_without_execution(self):
        for cell in self.cells:ast.parse(cell)
        self.assertTrue(all(c.get('execution_count') is None and not c.get('outputs') for c in self.nb['cells'] if c['cell_type']=='code'))
    def test_default_pilot_and_no_implicit_failure_retry(self):
        config=next(s for s in self.cells if 'RUN_ALL=False' in s)
        self.assertIn('RETRY_VLM_ERRORS=False',config)
        self.assertIn('RERUN_SPECIALISTS=False',config)
        self.assertIn("MANIFEST['scope']=='all'",config)
    def test_env_restore_and_worker_isolation(self):
        source='\n'.join(self.cells)
        self.assertIn('BKQuiz_preprocessing',source)
        self.assertIn("'uv==0.13.3'",source)
        self.assertIn("'it3170_docling_v5_env'",source)
        self.assertIn("'it3170_mineru_v5_env'",source)
        self.assertIn("'parser_worker.py'",source)
        self.assertNotIn("from transformers import",source)
    def test_download_cell_does_not_require_successful_inference(self):
        last=self.cells[-1]
        self.assertIn('files.download',last)
        self.assertIn('semantic_verified',last)
        self.assertNotIn('assert ENV_OK',last)

if __name__=='__main__':unittest.main()
