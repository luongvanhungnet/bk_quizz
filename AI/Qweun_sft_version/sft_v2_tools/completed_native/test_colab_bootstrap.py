import ast
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import colab_bootstrap as boot
from build_notebook import notebook


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='colab_bootstrap_test_');self.root=Path(self.temp.name).resolve()
        self.assertEqual(self.root.parent,Path(tempfile.gettempdir()).resolve());self.env=self.root/'test_venv';self.commands=[]
    def tearDown(self):self.temp.cleanup()
    def runner(self,command,**kwargs):
        self.commands.append(command)
        if '--without-pip' in command:
            (self.env/'bin').mkdir(parents=True);(self.env/'bin/python').write_text('fixture');(self.env/'pyvenv.cfg').write_text('fixture')
        return subprocess.CompletedProcess(command,0,stdout='')
    def download(self,path):Path(path).write_text('# isolated test fixture');return 'a'*64
    def test_healthy_environment_is_reused_without_installs(self):
        with patch.object(boot,'healthy_venv',return_value=True):
            result=boot.ensure_colab_venv(self.env,allowed_root=self.root,runner=self.runner,downloader=self.download)
        self.assertEqual(result,self.env/'bin/python');self.assertEqual(self.commands,[])
    def test_missing_pip_venv_is_retained_and_recreated(self):
        (self.env/'bin').mkdir(parents=True);(self.env/'bin/python').write_text('broken');(self.env/'pyvenv.cfg').write_text('fixture')
        with patch.object(boot,'healthy_venv',side_effect=[False,True]):
            boot.ensure_colab_venv(self.env,allowed_root=self.root,runner=self.runner,downloader=self.download)
        old=list(self.root.glob('test_venv.broken.*'));self.assertEqual(len(old),1)
        self.assertEqual((old[0]/'bin/python').read_text(),'broken')
        self.assertIn('--without-pip',self.commands[0]);self.assertIn('--system-site-packages',self.commands[0])
        self.assertEqual(self.commands[1][0],str(self.env/'bin/python'))
        self.assertTrue((self.env/'colab_bootstrap.json').is_file())
    def test_unknown_nonempty_directory_is_not_replaced(self):
        self.env.mkdir();data=self.env/'dataset.json';data.write_text('preserve')
        with patch.object(boot,'healthy_venv',return_value=False):
            with self.assertRaises(ValueError):boot.ensure_colab_venv(self.env,allowed_root=self.root)
        self.assertEqual(data.read_text(),'preserve')
    def test_drive_or_outside_path_refused(self):
        for path in (self.root/'drive',self.root.parent/'outside_venv'):
            with self.assertRaises(ValueError):boot.ensure_colab_venv(path,allowed_root=self.root)
    def test_unrelated_creation_failure_does_not_guess_apt_fix(self):
        def failure(command,**kwargs):
            self.commands.append(command);raise subprocess.CalledProcessError(1,command,output='Disk quota exceeded')
        with patch.object(boot,'healthy_venv',return_value=False):
            with self.assertRaises(subprocess.CalledProcessError):boot.ensure_colab_venv(self.env,allowed_root=self.root,runner=failure)
        self.assertEqual(len(self.commands),1)
    def test_missing_venv_fallback_targets_active_python_once(self):
        attempts=[]
        def runner(command,**kwargs):
            if '--without-pip' in command:
                attempts.append(command)
                if len(attempts)==1:
                    self.commands.append(command)
                    raise subprocess.CalledProcessError(1,command,output='No module named venv')
            return self.runner(command,**kwargs)
        version=subprocess.CompletedProcess([],0,stdout='3.13\n')
        with patch.object(boot,'healthy_venv',side_effect=[False,True]),patch.object(boot.shutil,'which',return_value='/usr/bin/apt-get'),patch.object(boot.subprocess,'run',return_value=version):
            boot.ensure_colab_venv(self.env,allowed_root=self.root,runner=runner,downloader=self.download)
        self.assertEqual(len(attempts),2)
        self.assertIn(['apt-get','install','-y','python3.13-venv'],self.commands)
    def test_health_requires_pip_not_only_python_file(self):
        (self.env/'bin').mkdir(parents=True);(self.env/'bin/python').write_text('fixture')
        values=[subprocess.CompletedProcess([],0,stdout=json.dumps({'prefix':str(self.env),'base':'base','version':[3,13]})),
                subprocess.CompletedProcess([],0,stdout=json.dumps({'prefix':'base','base':'base','version':[3,13]})),
                subprocess.CompletedProcess([],1,stdout='',stderr='No module named pip')]
        with patch.object(boot.subprocess,'run',side_effect=values):self.assertFalse(boot.healthy_venv(self.env))
    def test_failed_command_keeps_both_output_streams(self):
        log=self.root/'setup.log'
        with redirect_stdout(io.StringIO()):
            with self.assertRaises(subprocess.CalledProcessError) as failure:
                boot.run_logged([sys.executable,'-c','import sys;print("stdout detail");print("stderr detail",file=sys.stderr);sys.exit(3)'],log_path=log)
        self.assertIn('stdout detail',failure.exception.output);self.assertIn('stderr detail',failure.exception.output)
        self.assertIn('EXIT: 3',log.read_text(encoding='utf-8'))
    def test_generated_notebook_setup_has_valid_child_code(self):
        nb=notebook({'sha256':'a'*64})
        for cell in nb['cells']:
            if cell['cell_type']!='code':continue
            tree=ast.parse(''.join(cell['source']))
            for node in ast.walk(tree):
                if isinstance(node,ast.List):
                    for i,entry in enumerate(node.elts[:-1]):
                        if isinstance(entry,ast.Constant) and entry.value=='-c' and isinstance(node.elts[i+1],ast.Constant):
                            ast.parse(node.elts[i+1].value)


if __name__=='__main__':unittest.main()
