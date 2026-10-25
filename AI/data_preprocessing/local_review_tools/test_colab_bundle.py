import ast
import unittest


class ColabBundleTests(unittest.TestCase):
    def test_notebook_cells_compile_and_gate_bundle_gpu_smoke_and_resume(self):
        from build_training_colab import notebook
        digest='a'*64
        nb=notebook(digest)
        self.assertEqual(nb['nbformat'],4)
        code=[]
        for cell in nb['cells']:
            if cell['cell_type']=='code':
                source=''.join(cell['source']);ast.parse(source);code.append(source)
                self.assertIsNone(cell['execution_count']);self.assertEqual(cell['outputs'],[])
        joined='\n'.join(code)
        self.assertIn(digest,joined)
        self.assertIn('is_relative_to',joined)
        self.assertIn('RESUME_TRAIN',joined)
        self.assertIn("'smoke/completed.json'",joined)
        self.assertIn("'--mode', 'train'",joined)
        self.assertNotIn('files.upload',joined)


if __name__=='__main__':unittest.main()
