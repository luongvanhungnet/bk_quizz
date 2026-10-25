"""Keep the controller and parked Qwen worker alive between notebook uploads."""
import argparse
from pathlib import Path
import sys
import traceback
from common import atomic_json, load
from sequential import SequentialCoordinator


def main():
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True)
    p.add_argument('--work',type=Path,default=Path('/content/bkquiz_v5_sequential'))
    p.add_argument('--reload-model-per-input',action='store_true')
    a=p.parse_args();c=SequentialCoordinator(a.base,a.work,load(a.base/'environments.json'),keep_model=not a.reload_model_per_input)
    try:
        for line in sys.stdin:
            command=__import__('json').loads(line)
            if command['action']=='close':break
            try:
                if command['action']=='process':result=c.process(command['archive'])
                elif command['action']=='acknowledge':result=c.acknowledge(command['index'],command['archive_sha256'])
                else:raise ValueError('Unknown command')
                reply={'ok':True,'result':result}
            except Exception as exc:
                reply={'ok':False,'error':repr(exc),'traceback':traceback.format_exc()}
            atomic_json(command['response'],reply)
    finally:c.close()


if __name__=='__main__':main()
