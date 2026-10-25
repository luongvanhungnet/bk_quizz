"""Independent-unit controller; only final results/receipts are durable progress."""
import argparse
import json
from pathlib import Path
import sys
import traceback

from common import atomic_json,load
from ownership import CoordinatorLock
from telemetry import Monitor,span
from unit_queue import UnitRunner
from unit_store import read_index


def main():
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--work',type=Path,required=True)
    p.add_argument('--batch-pages',type=int,default=20);p.add_argument('--reload-model-per-input',action='store_true')
    a=p.parse_args()
    if a.batch_pages!=20:raise ValueError('This release uses internal groups of 20 pages')
    config=load(a.base/'unit_runtime_config.json');index=read_index(config['input_dir'])
    with CoordinatorLock(a.base),Monitor(a.work,a.base) as monitor:
        runner=UnitRunner(a.base,a.work,index,load(a.base/'environments.json'),config.get('precompleted_dir'))
        try:
            for line in sys.stdin:
                command=json.loads(line);action=command['action']
                if action=='close':break
                try:
                    with span('command',action=action):
                        if action=='scan':result=runner.scan()
                        elif action=='status':result=runner.store.summary()
                        elif action=='process':
                            result=runner.process(command['unit_id'])
                            if a.reload_model_per_input:runner.pool.close()
                        else:raise ValueError('Unknown unit command')
                    reply={'ok':True,'result':result}
                except Exception as exc:reply={'ok':False,'error':repr(exc),'traceback':traceback.format_exc()}
                atomic_json(command['response'],reply);monitor.request_sync()
        finally:runner.close()


if __name__=='__main__':main()
