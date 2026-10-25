import json
import tempfile
import unittest
from argparse import Namespace
from unittest.mock import patch
from pathlib import Path
from import_ollama import validate_model,parameter_signature
from import_ollama import main as import_main
from compare_exports import analyze,load,PROBES


class LocalChecks(unittest.TestCase):
    def test_gguf_import_never_passes_ollama_quantize(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);model=root/'model.gguf';model.write_bytes(b'GGUF')
            show={'template':'chat\ntemplate\n','parameters':'repeat_penalty 1',
                  'details':{'quantization_level':'Q4_K_M'}}
            args=Namespace(model_path=model,base='qwen3:1.7b',name='cpt-test:1.7b',work=root/'work',check_only=False)
            with patch('import_ollama.api',side_effect=[{'models':[]},show,show,{'models':[]}]), patch('import_ollama.subprocess.run') as run, patch('builtins.print'):
                import_main(args)
                self.assertNotIn('--quantize',run.call_args.args[0])
                self.assertNotIn(b'\r\n',(root/'work/Modelfile').read_bytes())

    def test_parameter_order_is_ignored_but_values_are_checked(self):
        self.assertEqual(parameter_signature('top_k 20\nstop "end"'),parameter_signature('stop "end"\ntop_k 20'))
        self.assertNotEqual(parameter_signature('top_k 20'),parameter_signature('top_k 40'))

    def test_hf_import_converts_before_creating_ollama_model(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'hf';source.mkdir();gguf=root/'converted.gguf';gguf.write_bytes(b'GGUF')
            show={'template':'chat template','parameters':'repeat_penalty 1','details':{'quantization_level':'Q4_K_M'}}
            args=Namespace(model_path=source,base='qwen3:1.7b',name='cpt-test:1.7b',work=root/'work',check_only=False)
            with patch('import_ollama.validate_model',return_value=source),patch('convert_local.convert',return_value=gguf) as convert,patch('import_ollama.api',side_effect=[{'models':[]},show,show,{'models':[]}]),patch('import_ollama.subprocess.run') as run,patch('builtins.print'):
                import_main(args)
                convert.assert_called_once()
                self.assertNotIn('--quantize',run.call_args.args[0])
                self.assertIn(gguf.as_posix(),(root/'work/Modelfile').read_text(encoding='utf-8'))

    def test_hf_import_requires_every_weight_shard_and_tokenizer(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'config.json').write_text(json.dumps({'model_type':'qwen3'}))
            (root/'model.safetensors.index.json').write_text(json.dumps({'weight_map':{'a':'part-1.safetensors','b':'part-2.safetensors'}}))
            (root/'part-1.safetensors').write_bytes(b'placeholder')
            (root/'tokenizer.json').write_text('{}')
            with self.assertRaises(ValueError):validate_model(root)
            (root/'part-2.safetensors').write_bytes(b'placeholder')
            self.assertEqual(validate_model(root),root)

    def test_adapter_directory_is_not_a_full_model(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'config.json').write_text(json.dumps({'peft_type':'LORA'}))
            with self.assertRaises(ValueError):validate_model(root)

    def test_wrong_key_is_not_rescued_by_correct_explanation(self):
        cases=load(PROBES/'prompts.json');gold=load(PROBES/'gold.json')['facts']
        q={'slot_id':'integer_width','difficulty':'MEDIUM','question':'a=b=10^18; chọn độ rộng nhỏ nhất trong bốn lựa chọn.',
           'options':[{'id':i,'text':str(n)+' bit'} for i,n in zip('ABCD',[16,32,64,128])],
           'answer':'B','explanation':'64 bit là đáp án đúng.','source_id':'S05',
           'evidence_quote':'Cho hai số nguyên dương a=b=10^18.'}
        results=[{'case_id':c['id'],'messages_sha256':c['messages_sha256'],'seconds':1,
                  'content':json.dumps({'questions':[q] if c['id']=='P05' else [],'rejected':[]})} for c in cases]
        summary,rows=analyze({'results':results},cases,gold)
        self.assertEqual(summary['literal_key_matches'],0)
        width=next(r for r in rows if r['slot_id']=='integer_width')
        self.assertEqual(width['marked_literal'],32)
        self.assertEqual(len(rows),11)


if __name__=='__main__':unittest.main()
