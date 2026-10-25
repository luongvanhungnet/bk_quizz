import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import contextlib
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from runtime_profile import validate_hardware,safetensors_header,audit_docling_cache,check_environments
from common import atomic_json,load,digest


class L4ProfileTests(unittest.TestCase):
    def good(self):
        return {'system':'Linux','python':[3,13,0],'ram_total_bytes':52*1024**3,'ram_available_bytes':45*1024**3,
                'gpus':[{'name':'NVIDIA L4','memory_total_mib':23034,'memory_free_mib':22000}]}

    def test_l4_high_ram_accepts_python3_without_pinning_minor(self):
        for minor in [10,11,12,13]:
            info=self.good();info['python']=[3,minor,1];self.assertEqual(validate_hardware(info),[])

    def test_wrong_gpu_or_standard_ram_or_wrong_python_rejected(self):
        for change in [{'gpus':[{'name':'Tesla T4','memory_total_mib':15360,'memory_free_mib':15000}]},
                       {'ram_total_bytes':13*1024**3},{'python':[3,14,0]},{'ram_available_bytes':4*1024**3}]:
            self.assertTrue(validate_hardware({**self.good(),**change}))

    def test_safetensors_structural_audit_preserves_corrupt_cache(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);repo=root/'hub/models--docling-project--docling-layout-heron/snapshots/abc';repo.mkdir(parents=True)
            header=json.dumps({'w':{'dtype':'F32','shape':[1],'data_offsets':[0,4]}}).encode()
            valid=repo/'model.safetensors';valid.write_bytes(len(header).to_bytes(8,'little')+header+b'\0'*4)
            self.assertEqual(safetensors_header(valid)['tensors'],1)
            bad=repo/'bad.safetensors';bad.write_bytes(b'<html>not weights</html>');before=digest(bad)
            audit=audit_docling_cache(root)
            self.assertEqual(audit['invalid_files'],1);self.assertEqual(digest(bad),before)

    def test_readiness_failure_stops_before_later_roles_and_keeps_diagnostics(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            root=Path(d);calls=[]
            def fake_run(args,**kw):
                role=args[args.index('--role')+1];calls.append(role);target=Path(args[args.index('--output')+1])
                atomic_json(target,{'status':'error','error':'simulated CUDA issue','traceback':'complete traceback'})
                class Result:returncode=1
                return Result()
            with patch('runtime_profile.stage_engine',return_value=root/'engine'),patch('runtime_profile.subprocess.run',side_effect=fake_run):
                with self.assertRaises(RuntimeError):check_environments({'controller':'python'},root/'input.zip',root/'base',root/'work',root/'clean_cache')
            self.assertEqual(calls,['controller'])
            outputs=list((root/'base/preflight_runs').glob('*/controller.json'))
            self.assertEqual(len(outputs),1);self.assertEqual(load(outputs[0])['traceback'],'complete traceback')

    def test_docling_worker_uses_its_own_cache_not_qwen_cache(self):
        from orchestrator import Coordinator
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c=Coordinator(root/'base',root/'work',{'docling':'python'});c.engine=root/'engine'
            with (patch.object(c,'needs_stage',return_value=True),patch.object(c,'execute_stage'),
                  patch('orchestrator.Worker') as worker,patch.dict('os.environ',{'BKQUIZ_DOCLING_HF_HOME':'/new/docling_cache'})):
                c.group_stage('docling',[({'job_id':'j'},'discovery')])
                env=worker.call_args.args[4]
            self.assertEqual(env['HF_HOME'],'/new/docling_cache');self.assertEqual(env['CUDA_VISIBLE_DEVICES'],'')

    def test_notebook_records_l4_profile_and_runs_preflight_before_process(self):
        from build_notebook import build
        nb=load(build());code='\n'.join(''.join(c['source']) for c in nb['cells'] if c['cell_type']=='code')
        self.assertEqual(nb['metadata']['colab']['gpuType'],'L4');self.assertEqual(nb['metadata']['colab']['machine_shape'],'hm')
        self.assertEqual(nb['metadata']['kernelspec']['name'],'python3')
        self.assertLess(code.index('check_hardware(BASE)'),code.index('setup(BASE)'))
        self.assertLess(code.index('READINESS=check_environments('),code.index('SESSION.process_input('))
        self.assertIn(load(ROOT/'RUNTIME_RELEASE.json')['runtime_zip'],code)

    def test_current_input_errors_are_separate_from_historical_errors(self):
        from orchestrator import Coordinator
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            root=Path(d);c=Coordinator(root/'base',root/'work',{})
            run=root/'run';atomic_json(run/'manifest.json',{'layout_inventory_status':'ready'})
            packet=root/'packet';atomic_json(packet/'manifest.json',{'requests':[]})
            c.jobs=[{'job_id':'new','run':str(run),'layout_required':False}]
            c.state['merged']['new:inference']={};c.state['stages']={'old:inference:ocr':{'completed':True,'result':{'status':'error'}}}
            with patch.object(c,'prepare'),patch.object(c,'group_stage'),patch.object(c,'merge'),patch.object(c,'packet',return_value=packet):
                summary=c.run()
            self.assertEqual(summary['stages_with_errors'],0);self.assertEqual(summary['historical_stages_with_errors'],1)
            c.state['stages']['new:inference:ocr']={'completed':True,'result':{'status':'error'}}
            with patch.object(c,'prepare'),patch.object(c,'group_stage'),patch.object(c,'merge'),patch.object(c,'packet',return_value=packet):
                summary=c.run()
            self.assertEqual(summary['stages_with_errors'],1);self.assertEqual(summary['historical_stages_with_errors'],1)
            self.assertEqual(summary['cumulative_stages_with_errors'],2)


if __name__=='__main__':unittest.main()
