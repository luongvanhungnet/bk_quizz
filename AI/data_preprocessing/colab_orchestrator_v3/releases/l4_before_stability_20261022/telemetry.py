"""Best-effort Linux process-tree telemetry; no GPU/Python package dependency."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time

_path = None
_lock = threading.Lock()


def configure(path):
    global _path
    _path = Path(path) if path is not None else None
    if _path:_path.parent.mkdir(parents=True, exist_ok=True)


def event(kind, **fields):
    row = {'event': kind, 'unix': time.time(), 'pid': os.getpid(), **fields}
    if _path:
        with _lock, _path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
    return row


@contextmanager
def span(name, **fields):
    start = time.monotonic()
    event('stage_start', stage=name, **fields)
    try:
        yield
    except BaseException as exc:
        event('stage_end', stage=name, seconds=time.monotonic()-start, status='error', error=repr(exc), **fields)
        raise
    else:
        event('stage_end', stage=name, seconds=time.monotonic()-start, status='ok', **fields)


def snapshot(work, root_pid=None):
    include_kernel=root_pid is None
    root_pid = root_pid or os.getpid()
    result = {'available_ram_bytes': None, 'total_ram_bytes': None, 'processes': [], 'gpus': [], 'gpu_processes': []}
    try:
        mem = dict((line.split(':')[0], int(line.split()[1])*1024) for line in Path('/proc/meminfo').read_text().splitlines())
        result.update(available_ram_bytes=mem['MemAvailable'], total_ram_bytes=mem['MemTotal'])
        all_procs = {}
        for path in Path('/proc').glob('[0-9]*/status'):
            try:
                fields = dict(line.split(':', 1) for line in path.read_text().splitlines() if ':' in line)
                pid = int(path.parent.name)
                all_procs[pid] = {'pid': pid, 'ppid': int(fields['PPid']), 'name': fields['Name'].strip(),
                                  'rss_bytes': int(fields.get('VmRSS', '0 kB').split()[0])*1024}
            except (OSError, ValueError, KeyError):
                continue
        selected = {root_pid,os.getppid()} if include_kernel else {root_pid}
        while True:
            more = {p for p, v in all_procs.items() if v['ppid'] in selected}
            if more.issubset(selected): break
            selected |= more
        result['processes'] = [v for p, v in all_procs.items() if p in selected]
        result['process_tree_rss_bytes'] = sum(p['rss_bytes'] for p in result['processes'])
    except (OSError, ValueError, KeyError):
        pass
    for query, key in [('index,name,memory.used,memory.total,utilization.gpu', 'gpus'), ('pid,used_gpu_memory', 'gpu_processes')]:
        try:
            flag = '--query-gpu=' if key == 'gpus' else '--query-compute-apps='
            p = subprocess.run(['nvidia-smi', flag+query, '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=3)
            if p.returncode == 0:
                result[key] = [dict(zip(query.split(','), [x.strip() for x in line.split(',')])) for line in p.stdout.splitlines() if line.strip()]
        except (OSError, subprocess.TimeoutExpired):
            pass
    try: result['disk_free_bytes'] = shutil.disk_usage(work).free
    except OSError: result['disk_free_bytes'] = None
    result['rss_note'] = 'Sum of RSS may count shared pages more than once; GPU values are MiB/percent from nvidia-smi.'
    return result


class Monitor:
    def __init__(self, work, remote, interval=15, sync_seconds=60):
        self.work, self.remote = Path(work), Path(remote)
        self.interval, self.sync_seconds = interval, sync_seconds
        self.stop_event = threading.Event()
        self.sync_lock = threading.Lock()
        self.path = self.work/'telemetry'/f'events_{time.time_ns()}.jsonl'
        configure(self.path)
        self.thread = threading.Thread(target=self._run, daemon=True)

    def sync(self):
        from common import copy_verified
        if not self.sync_lock.acquire(blocking=False):return
        try:
            if self.path.exists():
                # Copy a stable local snapshot while the sampling thread is writing.
                stable = self.path.with_suffix('.snapshot')
                with _lock: shutil.copyfile(self.path, stable)
                copy_verified(stable, self.remote/'telemetry'/self.path.name, replace=True, quiet=True)
                stable.unlink(missing_ok=True)
        finally:self.sync_lock.release()

    def _run(self):
        last = 0
        while not self.stop_event.is_set():
            event('resources', **snapshot(self.work))
            if time.monotonic()-last >= self.sync_seconds:
                try: self.sync()
                except Exception as exc: event('telemetry_sync_error', error=repr(exc))
                last = time.monotonic()
            self.stop_event.wait(self.interval)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop_event.set(); self.thread.join(timeout=10)
        if self.thread.is_alive():
            event('telemetry_final_sync_pending',reason='Background Drive sync still running; do not race its partial file')
            return
        try:self.sync()
        except Exception as exc:event('telemetry_sync_error',error=repr(exc))
