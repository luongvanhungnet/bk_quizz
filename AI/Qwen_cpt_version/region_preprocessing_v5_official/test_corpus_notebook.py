import ast
import json
from pathlib import Path
import unittest

class CorpusNotebook(unittest.TestCase):
    def setUp(self):
        nb=json.loads(Path(__file__).with_name('Colab_V5_Official_Corpus.ipynb').read_text(encoding='utf-8'))
        self.cells=[''.join(c['source']) for c in nb['cells'] if c['cell_type']=='code']
    def test_all_cells_compile(self):
        for s in self.cells:ast.parse(s)
    def test_packet_selection_does_not_silently_reuse_old_drive_zip(self):
        boot=self.cells[0]
        self.assertIn('INPUT_ZIP=None',boot);self.assertIn("BASE/'incoming'/uploaded_sha",boot)
        self.assertNotIn('if not INPUT_ZIP.exists():',boot)
    def test_discovery_does_not_install_or_load_qwen_unnecessarily(self):
        text='\n'.join(self.cells)
        self.assertIn('RUN_VLM=any(',text);self.assertIn('if RUN_VLM:',text)
        self.assertIn("RUN_STRUCTURE='structure' in REQUIRED",text)
        self.assertIn("if RUN_VLM and ENV_OK.get('vlm'):",text)
        self.assertIn("if q['is_full_page']",text)

if __name__=='__main__':unittest.main()
