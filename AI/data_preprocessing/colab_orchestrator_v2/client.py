"""Notebook client; a process call returns one ZIP before another input is accepted."""
import json
from pathlib import Path
import subprocess
import time
from common import load


class Session:
    def __init__(self,python,base,keep_model=True):
        self.base=Path(base);self.log_path=self.base/f'session_{time.time_ns()}.log'
        self.log=self.log_path.open('w',encoding='utf-8')
        command=[str(python),str(Path(__file__).with_name('daemon.py')),'--base',str(base)]
        if not keep_model:command.append('--reload-model-per-input')
        self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=self.log,stderr=subprocess.STDOUT,
                                      text=True,encoding='utf-8',bufsize=1)

    def call(self,action,**kwargs):
        response=self.base/'ipc'/f'{time.time_ns()}.json';response.parent.mkdir(parents=True,exist_ok=True)
        self.process.stdin.write(json.dumps({'action':action,'response':str(response),**kwargs})+'\n');self.process.stdin.flush()
        position=0;last=time.monotonic()
        while not response.exists():
            if self.process.poll() is not None:raise RuntimeError('Coordinator stopped; see '+str(self.log_path))
            if time.monotonic()-last>=5:
                with self.log_path.open(encoding='utf-8',errors='replace') as f:
                    f.seek(position);text=f.read();position=f.tell()
                if text:print(text,end='',flush=True)
                last=time.monotonic()
            time.sleep(.25)
        reply=load(response)
        if not reply['ok']:raise RuntimeError(reply['error']+'\n'+reply['traceback'])
        return reply['result']

    def process_input(self,path):return self.call('process',archive=str(path))
    def acknowledge(self,result):return self.call('acknowledge',index=result['bundle_index'],archive_sha256=result['archive_sha256'])

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.write('{"action":"close"}\n');self.process.stdin.flush()
            try:self.process.wait(timeout=45)
            except subprocess.TimeoutExpired:self.process.terminate();self.process.wait(timeout=10)
        self.process.stdin.close();self.log.close()
