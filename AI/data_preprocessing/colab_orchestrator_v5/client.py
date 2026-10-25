"""Local IPC/logs; notebook connectivity is not used to publish result archives."""
from pathlib import Path
import json
import os
import subprocess
import time

from common import load


class Session:
    def __init__(self,python,base,keep_model=True,batch_pages=20,work='/content/bkquiz_v5_drive_v3'):
        self.base,self.work=Path(base),Path(work)
        self.runtime_profile=os.environ.get('BKQUIZ_RUNTIME_PROFILE')
        self.runtime_revision=os.environ.get('BKQUIZ_RUNTIME_REVISION')
        self.docling_hf_home=os.environ.get('BKQUIZ_DOCLING_HF_HOME')
        self.batch_pages,self.keep_model=batch_pages,keep_model
        self.log_path=self.work/'logs'/f'session_{time.time_ns()}.log'
        self.log_path.parent.mkdir(parents=True,exist_ok=True)
        self.log=self.log_path.open('w',encoding='utf-8');self.position=0
        command=[str(python),str(Path(__file__).with_name('daemon.py')),'--base',str(base),'--work',str(work),'--batch-pages',str(batch_pages)]
        if not keep_model:command.append('--reload-model-per-input')
        self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=self.log,stderr=subprocess.STDOUT,text=True,encoding='utf-8',bufsize=1)

    def drain(self):
        # Bounded reads, and one cursor for the entire session, including final lines.
        with self.log_path.open(encoding='utf-8',errors='replace') as f:
            f.seek(self.position)
            text=f.read(64*1024);self.position=f.tell()
        if text:
            # Full logs stay on disk/export; the notebook receives a bounded tail.
            lines=text.splitlines(True)
            maximum_lines,maximum_chars=20,3500
            shown=''.join(lines[-maximum_lines:])[-maximum_chars:]
            if shown != text:
                print(f'[Log rút gọn; bản đầy đủ: {self.log_path}]',flush=True)
            print(shown,end='',flush=True)

    def call(self,action,**kwargs):
        response=self.work/'ipc'/f'client_{time.time_ns()}.json';response.parent.mkdir(parents=True,exist_ok=True)
        self.process.stdin.write(json.dumps({'action':action,'response':str(response),**kwargs})+'\n');self.process.stdin.flush()
        last=0;started=time.monotonic();last_status=0
        while not response.exists():
            if self.process.poll() is not None:
                self.drain();raise RuntimeError(f'Coordinator exited {self.process.returncode}; log: {self.log_path}')
            if time.monotonic()-started>float(os.environ.get('BKQUIZ_COMMAND_TIMEOUT_SECONDS','10800')):
                from stage_guard import terminate_tree,StageTimeout
                terminate_tree(self.process)
                raise StageTimeout('Coordinator command deadline exceeded; complete Drive ZIPs remain safe; rerun notebook to reconcile. Log: '+str(self.log_path))
            if time.monotonic()-last>=5:self.drain();last=time.monotonic()
            if time.monotonic()-last_status>=30:
                status=self.work/'telemetry/live_status.json'
                if status.exists():
                    s=load(status)
                    print('STATUS',s.get('sampled_unix'),[x.get('stage') for x in s.get('active_stages',[])],flush=True)
                last_status=time.monotonic()
            time.sleep(.25)
        self.drain()
        reply=load(response)
        if not reply['ok']:raise RuntimeError(reply['error']+'\n'+reply['traceback'])
        return reply['result']

    def process_unit(self,unit_id):return self.call('process',unit_id=unit_id)
    def scan(self):return self.call('scan')
    def status(self):return self.call('status')
    def close(self):
        if self.process.poll() is None:
            self.process.stdin.write('{"action":"close"}\n');self.process.stdin.flush()
            try:self.process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                from stage_guard import terminate_tree
                terminate_tree(self.process)
        self.drain();self.process.stdin.close();self.log.close()
