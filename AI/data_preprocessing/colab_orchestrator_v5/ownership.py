"""One coordinator per BASE on the same VM; OS releases the lock on process exit.

This is not a cross-VM Drive lock and cannot resolve a Colab document save conflict.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile


class CoordinatorLock:
    def __init__(self, base):
        key = hashlib.sha256(str(Path(base).resolve()).encode()).hexdigest()
        self.path = Path(tempfile.gettempdir())/'bkquiz_coordinator_locks'/(key+'.lock')
        self.file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        f = self.path.open('a+b')
        if f.seek(0, 2) == 0: f.write(b' '); f.flush()
        f.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            f.close()
            raise RuntimeError('Another coordinator owns this BASE on this VM. Reuse/close that SESSION first; do not run the queue from two notebooks.') from exc
        self.file = f
        f.seek(0); f.truncate()
        f.write(json.dumps({'pid':os.getpid(),'base_lock':str(self.path)}).encode());f.flush()
        return self

    def __exit__(self, *args):
        if self.file is not None:
            self.file.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
            self.file.close(); self.file = None
