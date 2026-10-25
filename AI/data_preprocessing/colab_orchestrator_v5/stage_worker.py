"""Bound CPU native/merge stages in killable subprocesses; preserve frozen sources."""
import argparse
from pathlib import Path
import sys

from common import atomic_json,digest,load
from stage_guard import progress


def main():
    p=argparse.ArgumentParser();p.add_argument('request',type=Path);a=p.parse_args();r=load(a.request)
    sys.path.insert(0,r['engine']);import io_utils
    io_utils.file_sha=digest
    from jsonl_adapter import install as install_jsonl
    install_jsonl()
    from layout_merge import install
    install()
    progress(r['stage'],status='start')
    if r['stage']=='native':
        from native_batches import prepare_native
        prepare_native(r['job'],None,20);result={'status':'ok'}
    else:
        from merge_adapter import install as install_merge
        install_merge()
        from corpus import merge_job
        result=merge_job(r['config'],r['job'],r['packet'],r['archive'])
    atomic_json(r['output'],result);progress(r['stage'],status='complete')


if __name__=='__main__':main()
