"""Restore verified batch products, including failed batches with no output files.

ZIPs written by v3 store files only, so an empty output directory has no member.
An empty FAILED checkpoint must retain its failure; an empty SUCCESS is invalid.
"""
from pathlib import Path
import shutil

from common import atomic_json
from telemetry import event


def restore_output(restore,batch_out,manifest):
    restore,batch_out=Path(restore),Path(batch_out)
    output_files=[name for name in manifest['files'] if name.startswith('output/')]
    response=manifest['response']
    if output_files:
        shutil.copytree(restore/'output',batch_out,dirs_exist_ok=True)
        return len(output_files)
    if response.get('completed') is True and response.get('result',{}).get('status')=='ok':
        raise ValueError('Batch checkpoint reports success but contains no output files; retain the archive and explicitly rerun this batch')
    # Materialize a container and audit note, not a fake successful parser result.
    batch_out.mkdir(parents=True,exist_ok=True)
    atomic_json(batch_out/'_restored_failure.json',{'reason':'failed_checkpoint_without_output_files',
        'stage_key':manifest.get('stage_key'),'original_response':response,'semantic_verified':False})
    event('batch_restored_without_outputs',stage_key=manifest.get('stage_key'),original_response=response)
    print('REUSE FAILED BATCH (no output files):',manifest.get('stage_key'),response.get('error',response.get('result')),flush=True)
    return 0
