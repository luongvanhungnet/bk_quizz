"""Install/validate each isolated environment once per runtime, before any queue worker."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
from common import atomic_json

SPECS = {
    'controller': ('bkquiz_v5_controller_env', {'PyMuPDF': '1.28.2', 'Pillow': '13.0.0', 'pydantic': '2.14.1', 'ImageHash': '4.3.2'},
                   [['PyMuPDF==1.28.2', 'Pillow==13.0.0', 'pydantic==2.14.1', 'ImageHash==4.3.2', 'python-pptx==1.0.2']]),
    'paddle': ('it3170_paddle_env', {'paddleocr': '3.7.0', 'paddlex': '3.7.2', 'paddlepaddle-gpu': '3.2.2'},
               [['paddlepaddle-gpu==3.2.2', '--index-url', 'https://www.paddlepaddle.org.cn/packages/stable/cu118/'],
                ['paddleocr[doc-parser]==3.7.0', 'paddlex[ocr]==3.7.2', 'Pillow==11.3.0']]),
    'vlm': ('it3170_vlm_env', {'torch': '2.6.0', 'torchvision': '0.21.0', 'transformers': '4.57.6', 'accelerate': '1.12.0', 'bitsandbytes': '0.48.1'},
            [['torch==2.6.0', 'torchvision==0.21.0', '--index-url', 'https://download.pytorch.org/whl/cu124/'],
             ['transformers==4.57.6', 'accelerate==1.12.0', 'bitsandbytes==0.48.1', 'Pillow==11.3.0']]),
    'docling': ('it3170_docling_v5_env', {'docling': '2.140.0'}, [['docling==2.140.0', 'Pillow==11.3.0']]),
}


def matches(python, expected):
    if not Path(python).exists():
        return False
    code = 'import importlib.metadata as m,json; print(json.dumps({n:m.version(n).split("+")[0] for n in ' + repr(list(expected)) + '}))'
    p = subprocess.run([str(python), '-c', code], capture_output=True, text=True)
    return p.returncode == 0 and json.loads(p.stdout) == expected


def ensure(name, cache, uv):
    env = Path('/content') / name
    python = env / 'bin/python'
    def runnable():
        return python.exists() and subprocess.run([str(python), '-c', 'import sys; assert sys.version_info[:2] == ' + repr(sys.version_info[:2])], capture_output=True).returncode == 0
    if runnable():
        return python
    if env.exists() or env.is_symlink():
        env.rename(env.with_name(name + '_retained_' + str(time.time_ns())))
    archive = Path(cache) / f'{name}_py{sys.version_info.major}{sys.version_info.minor}_v1.tar.gz'
    if archive.exists():
        local = Path('/content') / ('restore_' + archive.name)
        shutil.copy2(archive, local)
        with tarfile.open(local) as tar:
            for member in tar.getmembers():
                p = Path(member.name)
                if p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0] != name or member.isdev() or member.isfifo():
                    raise ValueError('Unsafe environment archive')
                if member.issym() or member.islnk():
                    target = (Path('/content') / p.parent / member.linkname).resolve()
                    internal = target.is_relative_to(env.resolve())
                    python_link = p.as_posix() in {f'{name}/bin/python', f'{name}/bin/python3', f'{name}/bin/python{sys.version_info.major}.{sys.version_info.minor}'} and target == Path(sys.executable).resolve()
                    if not internal and not python_link:
                        raise ValueError('Unexpected external environment link')
        subprocess.run(['tar', '-xzf', str(local), '-C', '/content'], check=True)
    if not runnable():
        if env.exists():
            env.rename(env.with_name(name + '_incompatible_' + str(time.time_ns())))
        subprocess.run([uv, 'venv', '--python', sys.executable, '--seed', str(env)], check=True)
    return python


def setup(base, roles=None):
    if not (3, 10) <= sys.version_info[:2] <= (3, 13):
        raise RuntimeError('Use the locked Python 3.10–3.13 runtime')
    subprocess.run(['nvidia-smi'], check=True)
    uv = shutil.which('uv')
    if not uv:
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'uv==0.13.3'], check=True)
        uv = shutil.which('uv')
    result = {}
    logs = Path(base) / 'environment_logs'
    logs.mkdir(parents=True, exist_ok=True)
    for role in roles or SPECS:
        name, expected, commands = SPECS[role]
        py = ensure(name, '/content/drive/MyDrive/BKQuiz_preprocessing', uv)
        if not matches(py, expected):
            for packages in commands:
                subprocess.run([uv, 'pip', 'install', '--python', str(py), *packages], check=True)
        if not matches(py, expected):
            raise RuntimeError('Environment verification failed: ' + role)
        frozen = subprocess.check_output([uv, 'pip', 'freeze', '--python', str(py)], text=True)
        (logs / f'{role}_{time.time_ns()}_freeze.txt').write_text(frozen, encoding='utf-8')
        result[role] = str(py)
        print('Environment ready:', role, flush=True)
    # Worker logs/processes are never stored as proof of a successful GPU inference.
    atomic_json(Path(base) / 'environments.json', result)
    return result
