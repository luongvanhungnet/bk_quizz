"""Reproducible local regression evidence; never opens the user's corpus ZIPs."""
import contextlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from common import atomic_json,digest,load,restore_checkpoint


def preserve_runtime_sources():
    backup=ROOT/'releases/l4_before_stability_20261022'
    release=load(backup/'RUNTIME_RELEASE.json')
    with zipfile.ZipFile(backup/release['runtime_zip']) as z:
        for name,sha in release['files'].items():
            path=backup/name
            if not path.exists():path.write_bytes(z.read(name))
            assert digest(path)==sha,name
    return backup


def restore_experiment(backup):
    from test_stability import history
    spec=importlib.util.spec_from_file_location('baseline_common',backup/'common.py')
    baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
    results=[]
    for legacy in [True,False]:
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(sys.stderr):
            root=Path(d);_,remote=history(root,legacy=legacy)
            inventory={p.resolve():digest(p) for p in remote.iterdir()}
            for label,restore in [('before',baseline.restore_checkpoint),('after',restore_checkpoint)]:
                counter={'remote_archive_opens':0,'remote_archive_bytes_read':0}
                original_open=Path.open
                class Counted:
                    def __init__(self,f):self.f=f
                    def __enter__(self):return self
                    def __exit__(self,*args):return self.f.__exit__(*args)
                    def __getattr__(self,name):return getattr(self.f,name)
                    def read(self,n=-1):
                        data=self.f.read(n);counter['remote_archive_bytes_read']+=len(data);return data
                def counting_open(path,*args,**kw):
                    f=original_open(path,*args,**kw)
                    if path.resolve().parent==remote.resolve() and path.suffix=='.zip':
                        counter['remote_archive_opens']+=1;return Counted(f)
                    return f
                start=time.monotonic()
                with patch.object(Path,'open',counting_open):restore(remote,root/label)
                results.append({'index':'legacy' if legacy else 'with_archive_file_inventory','implementation':label,
                                **counter,'local_fixture_seconds':time.monotonic()-start})
            for name,info in load(remote/'index.json')['files'].items():
                assert digest(root/'before'/name)==digest(root/'after'/name)==info['sha256']
            assert {p.resolve():digest(p) for p in remote.iterdir()}==inventory
    return results


def main():
    backup=preserve_runtime_sources()
    output=ROOT/'tests_stability_20261022.txt'
    with output.open('w',encoding='utf-8') as stream:
        suite=unittest.defaultTestLoader.discover(str(ROOT),pattern='test_*.py')
        started=time.monotonic()
        with contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
            result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        elapsed=time.monotonic()-started
    record={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'seconds':elapsed,'successful':result.wasSuccessful(),'actual_Colab_L4_executed':False,
            'frontend_reconnection_verified':False,'user_observation':'Telemetry on Drive continues updating during Connecting',
            'restore_fixture':restore_experiment(backup),'runtime_release':load(ROOT/'RUNTIME_RELEASE.json')}
    atomic_json(ROOT/'test_evidence_stability_20261022.json',record)
    print(json.dumps({k:v for k,v in record.items() if k not in {'runtime_release'}},indent=2))
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':main()
