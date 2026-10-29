"""Colab environment bootstrap, learned from the reported missing-pip incident.

Standard library only. Importing this file never installs or deletes anything.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import uuid

GET_PIP_URL="https://bootstrap.pypa.io/get-pip.py"


def run_logged(command, *, log_path=None, **kwargs):
    """Stream stdout and stderr together; retain the complete error output."""
    if any(key in kwargs for key in ("stdout","stderr","capture_output","text")):
        raise ValueError("run_logged owns output capture")
    kwargs.pop("check",None)
    print("Running:"," ".join(map(str,command)),flush=True)
    process=subprocess.Popen(list(map(str,command)),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                             text=True,bufsize=1,**kwargs)
    chunks=[]
    with process.stdout:
        for line in process.stdout:
            print(line,end="",flush=True);chunks.append(line)
    code=process.wait();output="".join(chunks)
    if log_path is not None:
        with Path(log_path).open("a",encoding="utf-8") as stream:
            stream.write("COMMAND: "+repr(list(map(str,command)))+"\n"+output+"\nEXIT: "+str(code)+"\n")
    if code:raise subprocess.CalledProcessError(code,command,output=output)
    return subprocess.CompletedProcess(command,code,stdout=output)


def healthy_venv(venv,base_python=sys.executable):
    """An interpreter file alone does not prove that pip or isolation works."""
    venv=Path(venv);python=venv/"bin/python"
    if not python.is_file():return False
    probe="import json,sys;print(json.dumps({'prefix':sys.prefix,'base':sys.base_prefix,'version':list(sys.version_info[:2])}))"
    try:
        own=subprocess.run([str(python),"-c",probe],capture_output=True,text=True,timeout=30)
        base=subprocess.run([str(base_python),"-c",probe],capture_output=True,text=True,timeout=30)
        pip=subprocess.run([str(python),"-m","pip","--version"],capture_output=True,text=True,timeout=30)
        if own.returncode or base.returncode or pip.returncode:return False
        info=json.loads(own.stdout);base_info=json.loads(base.stdout)
        return (Path(info["prefix"]).resolve()==venv.resolve() and info["prefix"]!=info["base"]
                and info["version"]==base_info["version"])
    except (OSError,ValueError,KeyError,subprocess.SubprocessError):return False


def download_get_pip(target):
    """Fetch an official script as a file, not curl|python; record its digest."""
    target=Path(target)
    with urllib.request.urlopen(GET_PIP_URL,timeout=60) as response:
        if not response.geturl().startswith("https://bootstrap.pypa.io/"):
            raise RuntimeError("Unexpected get-pip download destination")
        body=response.read(8*1024*1024+1)
    if not body or len(body)>8*1024*1024:raise RuntimeError("Invalid get-pip download size")
    target.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def ensure_colab_venv(venv, *, allowed_root=Path("/content"), base_python=sys.executable,
                      allow_system_packages=True, runner=run_logged, downloader=download_get_pip):
    """Repair only this disposable venv; never touch Drive/checkpoints/data."""
    requested=Path(venv);root=Path(allowed_root).resolve();venv=requested.resolve()
    if requested.is_symlink() or venv.parent!=root or venv==root or venv.name in {"drive","datasets","runs","checkpoints"}:
        raise ValueError("Venv must be a dedicated direct child of the allowed scratch directory")
    if healthy_venv(venv,base_python):
        print("Reusing healthy Python + pip:",venv,flush=True)
        return venv/"bin/python"
    if venv.exists():
        if not venv.is_dir() or (any(venv.iterdir()) and not (venv/"pyvenv.cfg").is_file()):
            raise ValueError("Existing path is not a recognizable disposable venv; choose a new venv path")
        # Keep the old environment recoverable. No recursive data deletion.
        backup=venv.with_name(venv.name+".broken."+uuid.uuid4().hex[:12])
        if backup.resolve().parent!=root:raise ValueError("Invalid venv backup target")
        venv.rename(backup);print("Old broken venv retained:",backup,flush=True)
    create=[str(base_python),"-m","venv","--system-site-packages","--without-pip",str(venv)]
    log_path=root/(venv.name+"_setup.log")
    try:runner(create,log_path=log_path)
    except subprocess.CalledProcessError as error:
        details=str(error.output or "")+str(error.stderr or "")
        missing_venv="No module named venv" in details or "No module named 'venv'" in details
        if not missing_venv or not allow_system_packages or not shutil.which("apt-get"):raise
        # Generic python3-venv may target a different interpreter than Colab's.
        version=subprocess.run([str(base_python),"-c","import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                               check=True,capture_output=True,text=True).stdout.strip()
        if not __import__('re').fullmatch(r"3\.\d+",version):raise RuntimeError("Cannot identify active Python version")
        runner(["apt-get","update"],log_path=log_path)
        runner(["apt-get","install","-y","python"+version+"-venv"],log_path=log_path)
        runner(create,log_path=log_path)
    python=venv/"bin/python"
    if not python.is_file():raise RuntimeError("Venv creation produced no Python executable; inspect setup log")
    script=root/(venv.name+"_get-pip.py")
    script_sha=downloader(script)
    runner([str(python),str(script)],log_path=log_path)
    if not healthy_venv(venv,base_python):raise RuntimeError("Python/pip health check still failed; stop and inspect setup log")
    (venv/"colab_bootstrap.json").write_text(json.dumps({"base_python":str(base_python),"method":"without-pip_then_official_get-pip",
          "get_pip_url":GET_PIP_URL,"get_pip_sha256":script_sha},indent=2),encoding="utf-8")
    return python
