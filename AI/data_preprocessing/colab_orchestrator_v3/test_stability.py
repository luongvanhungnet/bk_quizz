"""Regression evidence for restore cost, interruptions and notebook output pressure."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import common
from common import atomic_json, checkpoint, copy_verified, digest, load, restore_checkpoint, restore_pending_path


def history(root, legacy=False):
    run=root/'original';remote=root/'remote';run.mkdir()
    (run/'image.png').write_bytes(b'immutable bytes')
    for i in range(6):
        atomic_json(run/'manifest.json',{'version':i})
        checkpoint(run,remote)
    index=load(remote/'index.json')
    if legacy:
        for a in index['archives']:a.pop('files');a.pop('bytes')
        atomic_json(remote/'index.json',index)
    return run,remote


class StabilityTests(unittest.TestCase):
    def test_expected_hash_reads_source_once_and_verifies_local_copy(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'remote';source.write_bytes(b'payload');wanted=digest(source)
            real=common.digest
            def local_only(path):
                if Path(path)==source:raise AssertionError('Redundant source hash pass')
                return real(path)
            with patch('common.digest',side_effect=local_only):
                copy_verified(source,root/'local',expected_sha256=wanted,quiet=True)
            self.assertEqual(digest(root/'local'),wanted)
            source.unlink()
            # A known, validated local cache does not require a fresh Drive read.
            copy_verified(source,root/'local',expected_sha256=wanted,quiet=True)

    def test_bad_source_stream_never_publishes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'remote';source.write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'Source stream hash'):
                copy_verified(source,root/'local',expected_sha256='0'*64,quiet=True)
            self.assertFalse((root/'local').exists())

    def test_new_index_restores_only_two_of_six_zips_and_final_bytes(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            root=Path(d);original,remote=history(root)
            before={p.name:digest(p) for p in remote.iterdir()}
            with patch('common.copy_verified',wraps=copy_verified) as copied:
                restore_checkpoint(remote,root/'restored')
            self.assertEqual(copied.call_count,2)
            self.assertEqual(load(root/'restored/manifest.json'),{'version':5})
            self.assertEqual(digest(root/'restored/image.png'),digest(original/'image.png'))
            self.assertEqual({p.name:digest(p) for p in remote.iterdir()},before)
            with patch('common.copy_verified',side_effect=AssertionError('Already restored')):
                restore_checkpoint(remote,root/'restored')

    def test_legacy_restore_never_overwrites_final_file_with_old_revision(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            root=Path(d);_,remote=history(root,legacy=True);selections=[];real=common.checked_extract
            def capture(*args,**kw):
                selections.extend(kw['selected_files']);return real(*args,**kw)
            with patch('common.checked_extract',side_effect=capture):restore_checkpoint(remote,root/'restored')
            self.assertEqual(selections.count('manifest.json'),1)
            self.assertEqual(load(root/'restored/manifest.json'),{'version':5})

    def test_restore_after_interruption_keeps_marker_and_resumes_verified_files(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            root=Path(d);_,remote=history(root);run=root/'restored';real=common.checked_extract
            def interrupted(*args,**kw):
                result=real(*args,**kw)
                raise RuntimeError('simulated reset after extracting manifest')
            with patch('common.checked_extract',side_effect=interrupted):
                with self.assertRaises(RuntimeError):restore_checkpoint(remote,run)
            self.assertTrue((run/'manifest.json').exists());self.assertTrue(restore_pending_path(remote,run).exists())
            with patch('common.copy_verified',wraps=copy_verified) as copied:restore_checkpoint(remote,run)
            self.assertEqual(copied.call_count,1)
            self.assertFalse(restore_pending_path(remote,run).exists())
            self.assertEqual(list((root/'_checkpoint_restore').iterdir()),[])

    def test_corrupt_cached_archive_is_refetched_and_corrupt_remote_rejected(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            root=Path(d);_,remote=history(root);a=load(remote/'index.json')['archives'][-1]
            cache=root/'_checkpoint_restore'/a['sha256'];cache.parent.mkdir();cache.write_bytes(b'bad cache')
            restore_checkpoint(remote,root/'good')
            (remote/a['name']).write_bytes(b'bad remote')
            with self.assertRaises(ValueError):restore_checkpoint(remote,root/'bad')
            self.assertTrue(restore_pending_path(remote,root/'bad').exists())

    def test_register_resumes_restore_even_when_manifest_was_already_extracted(self):
        from test_drive_queue import fixture,ENVS
        from sequential import SequentialCoordinator
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            root=Path(d);jobs,inputs=fixture(root,(2,))
            with patch.dict('os.environ',{'BKQUIZ_SHARED_CACHE':str(root/'cache')}):
                first=SequentialCoordinator(root/'base',root/'work',ENVS,batch_pages=2)
                first.register_one(inputs[0]);first.prepare();first.close()
                run=root/'new_work/runs'/jobs[0]['document_id'];run.mkdir(parents=True)
                original=root/'work/runs'/jobs[0]['document_id'];remote=root/'base/checkpoints'/jobs[0]['document_id']
                (run/'manifest.json').write_bytes((original/'manifest.json').read_bytes())
                atomic_json(restore_pending_path(remote,run),{'interrupted':True})
                second=SequentialCoordinator(root/'base',root/'new_work',ENVS,batch_pages=2)
                with patch('sequential.restore_checkpoint',wraps=restore_checkpoint) as restored:
                    second.register_one(inputs[0])
                self.assertTrue(restored.called);self.assertFalse(restore_pending_path(remote,run).exists())
                self.assertEqual(digest(run/'records.jsonl'),digest(original/'records.jsonl'));second.close()

    def test_live_status_survives_slow_drive_sync_and_tracks_outer_stage(self):
        import telemetry
        from telemetry import Monitor,span
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);blocked=threading.Event();release=threading.Event()
            def slow_sync():blocked.set();release.wait(3)
            monitor=Monitor(root/'work',root/'drive',interval=.03,sync_seconds=.05)
            with patch.object(monitor,'sync',side_effect=slow_sync),patch('telemetry.snapshot',return_value={'gpus':[]}):
                with span('not_recorded_before_monitor'):
                    pass
                with monitor:
                    self.assertTrue(blocked.wait(1))
                    with span('restore_outer'):
                        with span('inner_transfer'):pass
                        status=root/'work/telemetry/live_status.json';deadline=time.monotonic()+2
                        while time.monotonic()<deadline:
                            if status.exists():
                                value=load(status)
                                if any(s['stage']=='restore_outer' for s in value['active_stages']):break
                            time.sleep(.02)
                        else:self.fail('Resource sampler blocked by Drive sync')
                        self.assertNotIn('inner_transfer',[s['stage'] for s in value['active_stages']])
                    release.set()
            telemetry.configure(None)

    def test_same_vm_cannot_start_two_coordinators_for_same_base(self):
        from ownership import CoordinatorLock
        with tempfile.TemporaryDirectory() as d:
            with CoordinatorLock(d):
                with self.assertRaisesRegex(RuntimeError,'Another coordinator'):
                    with CoordinatorLock(d):pass
            with CoordinatorLock(d):pass

    def test_notebook_output_is_bounded_but_full_log_preserved(self):
        from client import Session
        with tempfile.TemporaryDirectory() as d:
            s=object.__new__(Session);s.log_path=Path(d)/'log';s.position=0
            original=''.join(f'{i}: '+('x'*200)+'\n' for i in range(200))
            s.log_path.write_text(original,encoding='utf-8');out=io.StringIO()
            with contextlib.redirect_stdout(out):s.drain();s.drain()
            self.assertLess(len(out.getvalue()),4000);self.assertIn('199:',out.getvalue())
            self.assertEqual(s.log_path.read_text(encoding='utf-8'),original)

    def test_notebook_omits_saved_output_and_pins_stability_revision(self):
        from build_notebook import build,REVISION
        nb=load(build());code='\n'.join(''.join(c['source']) for c in nb['cells'] if c['cell_type']=='code')
        self.assertTrue(nb['metadata']['colab']['private_outputs'])
        self.assertEqual(nb['metadata']['bkquiz_runtime']['revision'],REVISION)
        self.assertIn("getattr(SESSION,'runtime_revision',None)",code)
        self.assertTrue(all(not c.get('outputs') for c in nb['cells']))


if __name__=='__main__':unittest.main()
