"""Persistent controller, independent of browser file transfers."""
import argparse
import json
from pathlib import Path
import sys
import traceback

from common import atomic_json,load
from sequential import SequentialCoordinator
from telemetry import Monitor,span,event
from ownership import CoordinatorLock


def main():
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True)
    p.add_argument('--work',type=Path,default=Path('/content/bkquiz_v5_drive_v3'))
    p.add_argument('--batch-pages',type=int,default=20);p.add_argument('--reload-model-per-input',action='store_true')
    args=p.parse_args();args.work.mkdir(parents=True,exist_ok=True)
    with CoordinatorLock(args.base), Monitor(args.work,args.base) as monitor:
        c=SequentialCoordinator(args.base,args.work,load(args.base/'environments.json'),keep_model=not args.reload_model_per_input,batch_pages=args.batch_pages)
        try:
            for line in sys.stdin:
                command=json.loads(line)
                if command['action']=='close':break
                try:
                    with span('command',action=command['action']):
                        if command['action']=='process':result=c.process(command['archive'])
                        elif command['action']=='commit':result=c.acknowledge(command['index'],command['archive_sha256'])
                        else:raise ValueError('Unknown command')
                    reply={'ok':True,'result':result}
                except Exception as exc:reply={'ok':False,'error':repr(exc),'traceback':traceback.format_exc()}
                atomic_json(command['response'],reply)
                monitor.request_sync()  # Telemetry I/O must not delay an IPC reply.
        finally:c.close()


if __name__=='__main__':main()
