"""Run the independent-unit regression suite and save a compact evidence record."""
import contextlib
import json
from pathlib import Path
import time
import unittest
from common import atomic_json,load

ROOT=Path(__file__).resolve().parent


if __name__=='__main__':
    start=time.monotonic()
    with (ROOT/'tests_20261022.txt').open('w',encoding='utf-8') as stream:
        suite=unittest.defaultTestLoader.discover(str(ROOT),pattern='test_*.py')
        with contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
            result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    evidence={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'successful':result.wasSuccessful(),'seconds':time.monotonic()-start,'actual_GPU_inference':False,
        'actual_Colab_executed':False,'unit_semantics':'Only complete hash-verified Drive ZIPs are durable progress',
        'input_validation':load(ROOT/'INPUT_VALIDATION_20261022.json')}
    atomic_json(ROOT/'test_evidence_20261022.json',evidence)
    print(json.dumps(evidence,indent=2))
    if not result.wasSuccessful():raise SystemExit(1)
