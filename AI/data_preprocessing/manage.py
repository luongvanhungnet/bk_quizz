"""Canonical entry point. Verify the selected immutable release before executing."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def selected_release():
    current=json.loads((ROOT/'CURRENT.json').read_text(encoding='utf-8'))
    release=(ROOT/current['release_path']).resolve()
    if not release.is_relative_to(ROOT.parent):raise ValueError('Release must stay inside AI workspace')
    manifest=release/'RELEASE.json'
    if digest(manifest)!=current['release_manifest_sha256']:raise ValueError('Official release manifest changed')
    metadata=json.loads(manifest.read_text(encoding='utf-8'))
    for name,expected in metadata['files'].items():
        p=(release/name).resolve()
        if not p.is_relative_to(release) or digest(p)!=expected:raise ValueError('Official release file changed: '+name)
    return release,metadata

def validate_plan_config(config,plan_path):
    snapshot=json.loads((Path(plan_path)/'config_snapshot.json').read_text(encoding='utf-8'))
    if snapshot!=config:raise ValueError('Operational config changed; create a new plan instead of silently changing an existing run')

def main():
    args=sys.argv[1:];release,metadata=selected_release()
    if not args or args==['verify']:
        print(json.dumps({'release':metadata['version'],'status':metadata['status'],'path':str(release),'files_verified':len(metadata['files'])},ensure_ascii=False,indent=2));return
    config=json.loads((ROOT/'production.json').read_text(encoding='utf-8'))
    if '--plan' in args:
        index=args.index('--plan')
        if index+1>=len(args):raise ValueError('--plan needs a path')
        validate_plan_config(config,args[index+1])
    if args[0]=='review-it3170':
        cmd=[sys.executable,str(release/'review_app.py'),'--run',config['reuse_runs'][0],*args[1:]]
    else:cmd=[sys.executable,str(release/'corpus.py'),'--config',str(ROOT/'production.json'),*args]
    raise SystemExit(subprocess.call(cmd))

if __name__=='__main__':main()
