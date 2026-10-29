"""Owned subprocess deadlines and progress independent of the notebook log stream."""
import os
from pathlib import Path
import signal
import subprocess
import time

from common import atomic_json,load
from telemetry import event,snapshot


class StageTimeout(TimeoutError):pass


def progress(stage,**fields):
    event('progress',stage=stage,**fields)
    path=os.environ.get('BKQUIZ_STAGE_PROGRESS')
    if path:atomic_json(path,{'stage':stage,'unix':time.time(),'pid':os.getpid(),**fields})


def terminate_tree(process):
    """Only terminate a Popen instance owned by this coordinator and its children."""
    if process.poll() is not None:return
    if os.name=='nt':
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=15)
    else:
        children={process.pid};parents={}
        for p in Path('/proc').glob('[0-9]*/status'):
            try:
                fields=dict(x.split(':',1) for x in p.read_text().splitlines() if ':' in x)
                parents[int(p.parent.name)]=int(fields['PPid'])
            except (OSError,ValueError,KeyError):pass
        while True:
            more={pid for pid,parent in parents.items() if parent in children}
            if more.issubset(children):break
            children|=more
        for pid in sorted(children-{os.getpid()},reverse=True):
            try:os.kill(pid,signal.SIGKILL)
            except ProcessLookupError:pass
    try:process.wait(timeout=15)
    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


def run_guarded(command,work,stage,*,timeout=900,env=None,interval=15):
    work=Path(work);work.mkdir(parents=True,exist_ok=True)
    log=work/(stage+'.log');status=work/(stage+'_progress.json')
    child_env={**os.environ,**(env or {}),'BKQUIZ_STAGE_PROGRESS':str(status),'PYTHONUNBUFFERED':'1'}
    start=last=time.monotonic()
    with log.open('w',encoding='utf-8') as f:
        process=subprocess.Popen(command,stdout=f,stderr=subprocess.STDOUT,env=child_env)
        try:
            while process.poll() is None:
                elapsed=time.monotonic()-start
                if elapsed>timeout:
                    terminate_tree(process)
                    event('stage_timeout',stage=stage,seconds=elapsed,log=str(log))
                    raise StageTimeout(f'{stage} exceeded {timeout}s; incomplete unit retained; log={log}')
                if time.monotonic()-last>=interval:
                    latest=load(status) if status.exists() else {}
                    resources=snapshot(work,process.pid)
                    if resources.get('available_ram_bytes') is not None and resources['available_ram_bytes']<2*1024**3:
                        terminate_tree(process)
                        raise MemoryError('Less than 2 GiB available RAM during '+stage+'; unit not committed')
                    if resources.get('disk_free_bytes') is not None and resources['disk_free_bytes']<512*1024**2:
                        terminate_tree(process)
                        raise OSError('Less than 512 MiB local disk free during '+stage+'; unit not committed')
                    event('guarded_stage_progress',stage=stage,seconds=elapsed,latest=latest,resources=resources)
                    print(f'PROGRESS {stage}: {elapsed:.0f}s; {latest}; RSS={resources.get("process_tree_rss_bytes")}',flush=True)
                    last=time.monotonic()
                time.sleep(min(.25,interval))
        except BaseException:
            terminate_tree(process);raise
    if process.returncode:
        tail=log.read_text(encoding='utf-8',errors='replace')[-5000:]
        raise RuntimeError(f'{stage} exited {process.returncode}; log={log}\n{tail}')
    event('guarded_stage_complete',stage=stage,seconds=time.monotonic()-start)
