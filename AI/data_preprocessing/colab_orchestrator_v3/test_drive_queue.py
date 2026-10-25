import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parent
ENGINE=ROOT.parent.parent/'Qwen_cpt_version/region_preprocessing_v5_official'
sys.path.insert(0,str(ENGINE));sys.path.insert(0,str(ROOT))
# Pin modules with __file__-relative resources before temporary engine paths exist.
import package_cloud
from common import VERSION,INPUT_VERSION,atomic_json,checked_extract,copy_verified,digest,load,rows,write_archive,write_compact_archive,restore_checkpoint
from drive_inputs import discover
from native_batches import prepare_native
from page_batches import split_packet,normalized_files
from sequential import SequentialCoordinator
from warm_worker import select_tasks


def pdf(path,pages=3):
    import pymupdf
    d=pymupdf.open()
    for i in range(pages):d.new_page(width=600,height=400).insert_text((50,50),f'graph academic text {i}: x + y = 12 (a <= b)')
    d.save(path);d.close()


def fixture(root,counts=(3,4)):
    import corpus
    docs=root/'docs';docs.mkdir()
    for i,count in enumerate(counts):pdf(docs/f'IT{i+1}-test.pdf',count)
    cfg={'source_root':str(docs),'work_root':str(root/'local'),'pages_per_packet':100,'maximum_packet_bytes':536870912,
         'vlm_target_fraction':.05,'vlm_maximum_fraction':.08,'upstream_manifest':str(root/'none'),
         'upstream_page_map':str(root/'none'),'reuse_runs':[]}
    corpus.inventory(cfg,root/'catalog');jobs=corpus.plan(cfg,root/'catalog',root/'plan')
    plan={'jobs':jobs,'config':cfg,'bundle_count':len(jobs),'jobs_sha256':digest(root/'plan/jobs.jsonl'),
          'release_manifest_sha256':digest(ENGINE/'RELEASE.json')}
    atomic_json(root/'plan.json',plan)
    enginefiles={f'engine/{n}':ENGINE/n for n in [*load(ENGINE/'RELEASE.json')['files'],'RELEASE.json']}
    inputs=[];folder=root/'drive_inputs';folder.mkdir()
    for i,j in enumerate(jobs,1):
        p=folder/f'input{i}.zip'
        write_archive(p,{**enginefiles,'plan.json':root/'plan.json',f'sources/{j["source_sha256"]}.pdf':Path(j['source_path'])},
            {'schema':INPUT_VERSION,'bundle_id':f'upload_{i:02d}','bundle_index':i,'bundle_count':len(jobs),'sequence_required':True,
             'jobs':[j['job_id']],'plan_sha256':digest(root/'plan.json'),'seed_fragments':[],'completed_jobs':[]},'bundle.json')
        inputs.append(p)
    atomic_json(root/'index.json',{'plan_sha256':digest(root/'plan.json')})
    return jobs,inputs


class FakeWorker:
    calls=[]
    def __init__(self,python,role,engine,logs,*args,**kw):
        self.role=role;self.log_path=Path(logs)/f'{role}.log';self.log_path.parent.mkdir(parents=True,exist_ok=True)
        self.log_path.touch(exist_ok=True)
    def close(self):pass
    def call(self,packet,out,control,visual_only=False,action='process'):
        if action=='park':return {'completed':True,'result':{'status':'ok'}}
        import vlm_worker
        m=load(packet/'manifest.json');out.mkdir(parents=True,exist_ok=True)
        self.calls.append((self.role,tuple(m['page_map'].values())))
        if self.role=='vlm':
            class Toy:
                telemetry={'possibly_truncated':False}
                def infer(self,*args):return 'Academic diagram, partial observation.'
            vlm_worker.run(packet,out,scope='all',model=Toy())
        elif self.role=='docling':
            atomic_json(out/'docling_raw.json',{'original':'untouched'})
            atomic_json(out/'parser_candidates_docling.json',{'engine':'docling','status':'ok',
                'original_source_sha256':m['document']['sha256'],'parser_input_sha256':m['parser_input_sha256'],
                'packet_manifest_sha256':digest(packet/'manifest.json'),'parser_candidates':[], 'semantic_verified':False})
        else:
            for q in select_tasks(m,self.role,visual_only):
                kind='diagram' if self.role=='structure' else 'text'
                record={'id':q['id'],'page':q['page'],'mode':self.role,'status':'ok','input_file_sha256':q['crop_sha256'],
                        'candidates':[{'page':q['page'],'bbox':[100,100,800,800] if kind=='diagram' else q['bbox'],'kind':kind,
                        'text':'graph academic text','engine':'paddle_structure' if kind=='diagram' else 'paddle_ocr','status':'ok',
                        'evidence':{'source_sha256':q['source_sha256'],'region_id':q['id']}}]}
                atomic_json(out/'records'/(q['id'].replace(':','_')+'.json'),record)
        return {'completed':True,'result':{'status':'ok'},'seconds':.1,'role':self.role}


ENVS={k:sys.executable for k in ['controller','paddle','docling','vlm']}


class DriveQueueTests(unittest.TestCase):
    def test_compact_roundtrip_deduplicates_and_rejects_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d);a=r/'same';a.write_bytes(b'large image bytes'*100)
            archive=r/'out.zip';m=write_compact_archive(archive,{'run/a.png':a,'packet/a.png':a},{'schema':VERSION})
            self.assertEqual(len(m['files']),1);self.assertEqual(m['duplicate_bytes_avoided'],a.stat().st_size)
            checked_extract(archive,r/'expanded','return.json')
            self.assertEqual(digest(r/'expanded/run/a.png'),digest(a))
            with self.assertRaises(ValueError):checked_extract(archive,r/'limited','return.json',maximum_bytes=a.stat().st_size+1)
            with zipfile.ZipFile(archive) as z:payload={n:z.read(n) for n in z.namelist()}
            name=next(n for n in payload if n.startswith('objects/'));payload[name]=b'tampered'
            bad=r/'bad.zip'
            with zipfile.ZipFile(bad,'w') as z:
                for n,b in payload.items():z.writestr(n,b)
            with self.assertRaises(ValueError):checked_extract(bad,r/'bad','return.json')

    def test_copy_mismatch_never_publishes_final_and_progress_has_bytes(self):
        import common,telemetry
        with tempfile.TemporaryDirectory() as d:
            r=Path(d);telemetry.configure(r/'events.jsonl');source=r/'source';source.write_bytes(b'x'*1024)
            real=common.digest
            with patch('common.digest',side_effect=lambda p:'bad' if str(p).endswith('.partial') else real(p)):
                with self.assertRaises(ValueError):copy_verified(source,r/'drive/result.zip')
            self.assertFalse((r/'drive/result.zip').exists());self.assertTrue((r/'drive/result.zip.partial').exists())
            copy_verified(source,r/'drive/result.zip')
            events=rows(r/'events.jsonl');self.assertEqual(events[-1]['event'],'transfer_complete');self.assertEqual(events[-1]['bytes'],1024)
            telemetry.configure(None)

    def test_drive_discovery_orders_and_rejects_missing_duplicate_or_mixed_plan(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            r=Path(d);jobs,inputs=fixture(r)
            self.assertEqual([v['manifest']['bundle_index'] for v in discover(r/'drive_inputs')],[1,2])
            shutil.copyfile(inputs[0],inputs[0].with_name('duplicate.zip'))
            with self.assertRaises(ValueError):discover(r/'drive_inputs')
            inputs[0].with_name('duplicate.zip').unlink();inputs[1].rename(r/'moved.zip')
            with self.assertRaises(ValueError):discover(r/'drive_inputs')

    def test_native_matches_frozen_text_symbols_assets_and_bounds_batches(self):
        import corpus
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            r=Path(d);jobs,_=fixture(r,(5,));j=jobs[0]
            corpus.prepare_documents(load(r/'plan/config_snapshot.json'),jobs)
            baseline=rows(Path(j['run'])/'records.jsonl')
            new={**j,'run':str(r/'batched')};prepare_native(new,r/'cp',2)
            actual=rows(r/'batched/records.jsonl')
            self.assertEqual(len(actual),len(baseline))
            for old,new_record in zip(baseline,actual):
                for k in ['id','page','native_text','render_sha256','crop_sha256','context_sha256','group_id','split']:
                    self.assertEqual(old[k],new_record[k],k)
            self.assertEqual([b['last']-b['first']+1 for b in load(r/'batched/native_progress.json')['batches']],[2,2,1])
            self.assertTrue(all('x + y = 12' in x['native_text'] for x in actual))

    def test_native_resume_restores_completed_groups_without_rerender(self):
        import native_batches
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            r=Path(d);jobs,_=fixture(r,(5,));j={**jobs[0],'run':str(r/'native')};real=native_batches.checkpoint;calls=0
            def fail_second(*a,**kw):
                nonlocal calls
                calls+=1
                if calls==2:raise RuntimeError('simulated lost VM')
                return real(*a,**kw)
            with patch('native_batches.checkpoint',side_effect=fail_second):
                with self.assertRaises(RuntimeError):prepare_native(j,r/'remote',2)
            j2={**j,'run':str(r/'new_native')};restore_checkpoint(r/'remote',r/'new_native')
            old=digest(r/'new_native/assets/slides/page_0001.png')
            with patch('native_batches.event') as events:prepare_native(j2,r/'remote',2)
            self.assertEqual(digest(r/'new_native/assets/slides/page_0001.png'),old)
            self.assertEqual(len(rows(r/'new_native/records.jsonl')),5)
            self.assertEqual(len(load(r/'new_native/native_progress.json')['batches']),3)

    def test_native_embedded_images_keep_original_crop_context_and_text_hashes(self):
        import corpus,pymupdf
        from PIL import Image,ImageDraw
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            r=Path(d);docs=r/'docs';docs.mkdir();image=Image.new('RGB',(240,140),'white');draw=ImageDraw.Draw(image)
            draw.line((10,20,220,120),fill='black',width=3);image.save(r/'figure.png')
            doc=pymupdf.open();page=doc.new_page(width=600,height=400);page.insert_text((50,50),'x = y + 1; graph figure')
            page.insert_image(pymupdf.Rect(71,103,331,253),filename=str(r/'figure.png'));doc.save(docs/'IT-image.pdf');doc.close()
            cfg={'source_root':str(docs),'work_root':str(r/'local'),'pages_per_packet':100,'maximum_packet_bytes':536870912,
                 'upstream_manifest':str(r/'none'),'upstream_page_map':str(r/'none'),'reuse_runs':[]}
            corpus.inventory(cfg,r/'catalog');jobs=corpus.plan(cfg,r/'catalog',r/'plan');corpus.prepare_documents(cfg,jobs)
            prepare_native({**jobs[0],'run':str(r/'batched')},r/'cp',1)
            before=rows(Path(jobs[0]['run'])/'records.jsonl');after=rows(r/'batched/records.jsonl')
            self.assertEqual(len(before),len(after));self.assertGreater(len(after),1)
            for old,new in zip(before,after):
                for k in ['id','native_text','render_sha256','crop_sha256','context_sha256']:
                    self.assertEqual(old[k],new[k],k)

    def test_noncontiguous_child_parser_mapping_and_vlm_parent_envelope(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d);p=r/'parent';p.mkdir();pdf(p/'parser_input.pdf',4)
            atomic_json(p/'manifest.json',{'page_map':{'1':101,'2':102,'3':203,'4':204},'requests':[],
                'parser_input':'parser_input.pdf','parser_input_sha256':digest(p/'parser_input.pdf'),'code_sha256':{},'document':{'sha256':'a'*64}})
            children=list(split_packet(p,r/'children',2));self.assertEqual([len(load(x/'manifest.json')['page_map']) for x in children],[2,2])
            child=children[1];cm=load(child/'manifest.json');out=r/'out';out.mkdir()
            atomic_json(out/'parser_candidates_docling.json',{'packet_manifest_sha256':digest(child/'manifest.json'),
                'parser_input_sha256':cm['parser_input_sha256'],'parser_candidates':[{'page':1,'kind':'text','text':'source page 203'}]})
            files=normalized_files(p,child,out,'docling');n=load(next(iter(files.values())))
            self.assertEqual(n['parser_candidates'][0]['page'],3)
            self.assertEqual(n['packet_manifest_sha256'],digest(p/'manifest.json'))
            self.assertEqual(load(out/'parser_candidates_docling.json')['parser_candidates'][0]['page'],1)
            atomic_json(out/'vlm_results_test.json',{'packet_manifest_sha256':digest(child/'manifest.json'),'observations':[]})
            v=load(next(iter(normalized_files(p,child,out,'vlm').values())))
            self.assertEqual(v['packet_manifest_sha256'],digest(p/'manifest.json'))

    def test_partial_docling_child_does_not_certify_full_job_layout_coverage(self):
        import batch_layout
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            r=Path(d);_,inputs=fixture(r,(4,))
            with patch.dict('os.environ',{'BKQUIZ_SHARED_CACHE':str(r/'cache')}):
                c=SequentialCoordinator(r/'base',r/'work',ENVS,batch_pages=2);c.register_one(inputs[0]);c.prepare()
                job=c.jobs[0];packet=c.packet(job,'discovery');pm=load(packet/'manifest.json')
                archive=r/'partial.zip'
                envelope={'status':'ok','original_source_sha256':job['source_sha256'],
                          'packet_manifest_sha256':digest(packet/'manifest.json'),'parser_input_sha256':pm['parser_input_sha256'],
                          'parser_candidates':[],'covered_source_pages':[1,2]}
                with zipfile.ZipFile(archive,'w') as z:z.writestr('docling/parser_candidates_docling.json',json.dumps(envelope))
                result=batch_layout.materialize(job['run'],archive,packet)
                m=load(Path(job['run'])/'manifest.json')
                self.assertEqual(m['layout_pages_processed'],[1,2]);self.assertEqual(result['layout_inventory_status'],'partial_layout')

    def test_two_inputs_drive_commit_resume_export_and_actual_import(self):
        import import_returns
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            r=Path(d);jobs,inputs=fixture(r);FakeWorker.calls=[]
            with patch('orchestrator.Worker',FakeWorker),patch('sequential.Worker',FakeWorker),patch.dict('os.environ',{'BKQUIZ_SHARED_CACHE':str(r/'cache')}):
                c=SequentialCoordinator(r/'base',r/'work',ENVS,batch_pages=2)
                atomic_json(r/'base/hardware_profile.json',{'profile':'fixture_no_actual_gpu'})
                atomic_json(r/'base/preflight_runs/fixture/summary.json',{'all_passed':True,'scope':'test_fixture'})
                first=c.process(inputs[0])
                with self.assertRaises(ValueError):c.process(inputs[1])
                with self.assertRaises(ValueError):c.acknowledge(1,'bad')
                c.acknowledge(1,first['archive_sha256']);c.close()
                self.assertFalse(first['download_confirmed']);self.assertTrue(first['drive_saved_verified'])
                self.assertFalse((r/'work/runs'/jobs[0]['document_id']).exists())
                c=SequentialCoordinator(r/'base',r/'new_work',ENVS,batch_pages=2)
                second=c.process(inputs[1]);c.acknowledge(2,second['archive_sha256']);c.close()
            self.assertTrue(all(len(pages)<=2 for role,pages in FakeWorker.calls))
            self.assertEqual(c.state['last_acknowledged_index'],2)
            for a in [first['archive'],second['archive']]:
                m=checked_extract(a,r/Path(a).stem,'return.json')
                self.assertEqual(m['schema'],VERSION);self.assertGreater(m['duplicate_bytes_avoided'],0)
                self.assertIn('hardware_profile.json',m['logical_files']);self.assertIn('preflight_runs/fixture/summary.json',m['logical_files'])
                self.assertFalse(any(n.endswith('.sqlite3') for n in m['logical_files']))
            result=import_returns.import_returns(r/'plan',r/'index.json',[first['archive'],second['archive']])
            self.assertEqual(result['new_local_runs'],2);self.assertEqual(result['human_decisions_auto_created'],0)
            self.assertFalse(result['training_exported'])
            import sqlite3
            reviews=Path(jobs[0]['run'])/'human_reviews.sqlite3'
            with sqlite3.connect(reviews) as db:
                db.execute('CREATE TABLE existing_review (decision TEXT)');db.execute('INSERT INTO existing_review VALUES (?)',('human decision retained',))
            db.close()
            wanted=digest(reviews)
            import_returns.import_returns(r/'plan',r/'index.json',[first['archive'],second['archive']])
            self.assertEqual(digest(reviews),wanted)

    def test_interrupted_model_batch_is_resumed_from_drive_in_new_work(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            r=Path(d);_,inputs=fixture(r,(4,));FakeWorker.calls=[]
            class Crash(FakeWorker):
                def call(self,*args,**kw):
                    if self.role=='ocr' and len([x for x in self.calls if x[0]=='ocr'])==1:raise RuntimeError('simulated kernel loss')
                    return super().call(*args,**kw)
            with patch('orchestrator.Worker',Crash),patch('sequential.Worker',Crash),patch.dict('os.environ',{'BKQUIZ_SHARED_CACHE':str(r/'cache')}):
                c=SequentialCoordinator(r/'base',r/'work',ENVS,batch_pages=2)
                with self.assertRaises(RuntimeError):c.process(inputs[0])
                c.close()
            old_calls=len(FakeWorker.calls)
            with patch('orchestrator.Worker',FakeWorker),patch('sequential.Worker',FakeWorker),patch.dict('os.environ',{'BKQUIZ_SHARED_CACHE':str(r/'cache')}):
                c=SequentialCoordinator(r/'base',r/'new_work',ENVS,batch_pages=2)
                result=c.process(inputs[0]);c.acknowledge(1,result['archive_sha256']);c.close()
            # Discovery OCR for first group was checkpointed before interruption.
            first_ocr=[(role,pages) for role,pages in FakeWorker.calls if role=='ocr' and pages==(1,2)]
            self.assertEqual(len(first_ocr),2)  # One discovery + one inference, not discovery twice.
            self.assertGreater(len(FakeWorker.calls),old_calls)

    def test_completed_stages_before_merge_restore_without_running_models_again(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            r=Path(d);jobs,inputs=fixture(r,(4,));FakeWorker.calls=[]
            with patch('orchestrator.Worker',FakeWorker),patch('sequential.Worker',FakeWorker),patch.dict('os.environ',{'BKQUIZ_SHARED_CACHE':str(r/'cache')}):
                c=SequentialCoordinator(r/'base',r/'work',ENVS,batch_pages=2);c.register_one(inputs[0]);c.prepare()
                pairs=[(c.jobs[0],'discovery')]
                for role in ['ocr','structure','docling']:c.group_stage(role,pairs)
                old=list(FakeWorker.calls);c.close()
                c=SequentialCoordinator(r/'base',r/'new_work',ENVS,batch_pages=2);c.register_one(inputs[0]);c.prepare()
                for role in ['ocr','structure','docling']:c.group_stage(role,[(c.jobs[0],'discovery')])
                self.assertEqual(FakeWorker.calls,old)
                c.merge(c.jobs[0],'discovery')
                self.assertEqual(load(Path(c.jobs[0]['run'])/'manifest.json')['layout_inventory_status'],'ready');c.close()

    def test_seed_fragment_cache_and_processed_candidate_are_preserved(self):
        import corpus
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            r=Path(d);jobs,_=fixture(r,(2,));corpus.prepare_documents(load(r/'plan/config_snapshot.json'),jobs)
            source=Path(jobs[0]['run']);records=rows(source/'records.jsonl');pages=rows(source/'document_pages.jsonl')
            c=SequentialCoordinator(r/'base',r/'work',ENVS,batch_pages=2);incoming=c.work/'incoming';did=jobs[0]['document_id']
            shutil.copytree(source/'assets',incoming/'seed_assets'/did/'assets')
            for i in range(2):
                dest=incoming/f'fragments/{i}';dest.mkdir(parents=True)
                for name in ['manifest.json','prepare_summary.json','classification.json','duplicate_candidates.json']:shutil.copyfile(source/name,dest/name)
                (dest/'records.jsonl').write_text(json.dumps(records[i])+'\n',encoding='utf-8')
                (dest/'document_pages.jsonl').write_text(json.dumps(pages[i])+'\n',encoding='utf-8')
                fragment={'document_id':did,'prefix':f'fragments/{i}','records_sha256':digest(dest/'records.jsonl'),
                          'source_sha256':jobs[0]['source_sha256'],'pages':[i+1]}
                c._fragment(fragment)
                if i==0:
                    processed=rows(c.work/'runs'/did/'records.jsonl');processed[0]['candidates'].append({'engine':'paddle_ocr','text':'already processed','status':'ok'})
                    (c.work/'runs'/did/'records.jsonl').write_text(json.dumps(processed[0])+'\n',encoding='utf-8')
            actual=rows(c.work/'runs'/did/'records.jsonl')
            self.assertEqual(len(actual),2);self.assertTrue(any(x['text']=='already processed' for x in actual[0]['candidates']))

    def test_telemetry_reports_nested_spans_and_resource_samples_without_fabricating(self):
        from summarize_telemetry import summarize
        from telemetry import snapshot
        with tempfile.TemporaryDirectory() as d:
            r=Path(d);events=[{'event':'stage_end','unix':1,'pid':2,'stage':'export_zip','seconds':7,'status':'ok'},
                             {'event':'resources','unix':2,'pid':2,'available_ram_bytes':1024,'process_tree_rss_bytes':512,
                              'processes':[{'pid':8,'name':'worker','rss_bytes':512}],'gpus':[{'memory.used':'4096'}]}]
            (r/'events.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in events),encoding='utf-8')
            result=summarize([r/'events.jsonl',r/'events.jsonl'])
            self.assertEqual(result['stages']['export_zip']['calls'],1)
            self.assertEqual(result['minimum_available_ram_bytes'],1024);self.assertEqual(result['peak_vram_mib'],4096)
            self.assertIn('disk_free_bytes',snapshot(r))

    def test_log_cursor_never_replays_previous_calls(self):
        from client import Session
        with tempfile.TemporaryDirectory() as d:
            s=object.__new__(Session);s.log_path=Path(d)/'log';s.position=0;s.log_path.write_text('one\n',encoding='utf-8')
            buf=io.StringIO()
            with contextlib.redirect_stdout(buf):
                s.drain();s.drain()
                with s.log_path.open('a',encoding='utf-8') as f:f.write('two\n')
                s.drain()
            self.assertEqual(buf.getvalue(),'one\ntwo\n')

    def test_finished_result_survives_reset_before_commit_without_inference(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            r=Path(d);_,inputs=fixture(r,(2,));FakeWorker.calls=[]
            with patch('orchestrator.Worker',FakeWorker),patch('sequential.Worker',FakeWorker),patch.dict('os.environ',{'BKQUIZ_SHARED_CACHE':str(r/'cache')}):
                c=SequentialCoordinator(r/'base',r/'work',ENVS,batch_pages=2);result=c.process(inputs[0]);old=list(FakeWorker.calls);c.close()
                c=SequentialCoordinator(r/'base',r/'new_work',ENVS,batch_pages=2);again=c.process(inputs[0]);c.acknowledge(1,again['archive_sha256']);c.close()
            self.assertEqual(again['archive_sha256'],result['archive_sha256']);self.assertEqual(FakeWorker.calls,old)

    def test_readonly_v2_migration_reuses_old_unmerged_ocr_and_checkpoint(self):
        from migrate_previous import migrate
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            r=Path(d);jobs,inputs=fixture(r,(4,));FakeWorker.calls=[]
            with patch.dict('os.environ',{'BKQUIZ_SHARED_CACHE':str(r/'cache')}):
                old=SequentialCoordinator(r/'old',r/'old_work',ENVS,batch_pages=2);old.register_one(inputs[0]);old.prepare()
                j=old.jobs[0];packet=old.packet(j,'discovery');folder=r/'old/raw_results'/j['job_id']/'discovery/paddle_ocr'
                w=FakeWorker(sys.executable,'ocr',ENGINE,r/'logs');response=w.call(packet,folder,r/'ipc')
                response['packet_manifest_sha256']=digest(packet/'manifest.json')
                old.state['stages'][j['job_id']+':discovery:ocr']=response
                old.state['schema']=INPUT_VERSION;old.save();before=digest(old.state_path)
                migrate(r/'old',r/'new',discover(r/'drive_inputs'),2)
                self.assertEqual(digest(old.state_path),before)
                with patch('orchestrator.Worker',FakeWorker),patch('sequential.Worker',FakeWorker):
                    c=SequentialCoordinator(r/'new',r/'new_work',ENVS,batch_pages=2)
                    result=c.process(inputs[0]);c.acknowledge(1,result['archive_sha256']);c.close()
            # Full old discovery OCR was reused; only inference invokes new small groups.
            self.assertEqual(len([x for x in FakeWorker.calls if x==('ocr',(1,2,3,4))]),1)
            self.assertEqual(c.state['migration']['old_files_modified'],False)

    def test_notebook_pins_runtime_and_contains_no_browser_upload_download_ack(self):
        import build_notebook
        nb=load(build_notebook.build());sources=[''.join(c['source']) for c in nb['cells'] if c['cell_type']=='code'];allcode='\n'.join(sources)
        for s in sources:compile(s,'notebook','exec')
        for forbidden in ['files.upload(','files.download(','DA_TAI']:self.assertNotIn(forbidden,allcode)
        import ast
        self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='input' for n in ast.walk(ast.parse(allcode))))
        self.assertIn("MyDrive/BKQuiz_cpt_data",allcode);self.assertIn('SESSION.commit(RESULT)',allcode)
        self.assertIn('PINNED_RUNTIME',allcode);self.assertEqual(allcode.count('setup(BASE)'),1)


if __name__=='__main__':unittest.main()
