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
        if text:print(text,end='',flush=True)

    def call(self,action,**kwargs):
        response=self.work/'ipc'/f'client_{time.time_ns()}.json';response.parent.mkdir(parents=True,exist_ok=True)
        self.process.stdin.write(json.dumps({'action':action,'response':str(response),**kwargs})+'\n');self.process.stdin.flush()
        last=0
        while not response.exists():
            if self.process.poll() is not None:
                self.drain();raise RuntimeError(f'Coordinator exited {self.process.returncode}; log: {self.log_path}')
            if time.monotonic()-last>=5:self.drain();last=time.monotonic()
            time.sleep(.25)
        self.drain()
        reply=load(response)
        if not reply['ok']:raise RuntimeError(reply['error']+'\n'+reply['traceback'])
        return reply['result']

    def process_input(self,path):return self.call('process',archive=str(path))
    def commit(self,result):return self.call('commit',index=result['bundle_index'],archive_sha256=result['archive_sha256'])
    def close(self):
        if self.process.poll() is None:
            self.process.stdin.write('{"action":"close"}\n');self.process.stdin.flush()
            try:self.process.wait(timeout=60)
            except subprocess.TimeoutExpired:self.process.terminate();self.process.wait(timeout=10)
        self.drain();self.process.stdin.close();self.log.close()
