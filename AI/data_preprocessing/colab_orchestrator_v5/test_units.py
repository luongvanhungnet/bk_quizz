import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
ENGINE=ROOT.parent.parent/'Qwen_cpt_version/region_preprocessing_v5_0_1'
sys.path.insert(0,str(ENGINE));sys.path.insert(0,str(ROOT))
# Pin modules with __file__-relative assets before temporary engine paths exist.
import package_cloud,corpus,batch_layout
from common import atomic_json,copy_verified,digest,load,rows,write_archive,write_compact_archive
from build_inputs import partition
from unit_store import INPUT_SCHEMA,RESULT_SCHEMA,UnitStore,inspect_result,read_index
from unit_queue import UnitRunner
from warm_worker import select_tasks

ENVS={role:sys.executable for role in ['controller','paddle','docling','vlm']}


def fixture(root,counts=(70,140)):
    import pymupdf
    jobs=[];root=Path(root);folder=root/'inputs';folder.mkdir()
    for i,count in enumerate(counts):
        p=root/f'IT{i}.pdf';doc=pymupdf.open()
        for number in range(1,count+1):
            page=doc.new_page(width=600,height=400)
            page.insert_text((50,50),f'Graph algorithm source {i}, page {number}: x + y = {number}; (a <= b)')
        doc.save(p);doc.close();sha=digest(p);did=f'it{i}_{sha[:12]}'
        for first in range(1,count+1,100):
            last=min(count,first+99)
            jobs.append({'job_id':f'{did}_p{first:05d}-{last:05d}','document_id':did,'course':f'IT{i}',
                'source_path':str(p),'source_sha256':sha,'source_pages':count,'first_page':first,'last_page':last,
                'layout_required':True,'split_policy':'train'})
    units=partition(jobs);alljobs=[j for u in units for j in u['jobs']]
    cfg={'work_root':str(root/'local'),'minimum_free_disk_bytes':0,'maximum_packet_bytes':536870912,
         'vlm_target_fraction':.05,'vlm_maximum_fraction':.08}
    plan={'jobs':alljobs,'config':cfg,'jobs_sha256':'1'*64,'release_manifest_sha256':digest(ENGINE/'RELEASE.json')}
    atomic_json(root/'plan.json',plan);entries=[]
    for u in units:
        files={f'engine/{n}':ENGINE/n for n in [*load(ENGINE/'RELEASE.json')['files'],'RELEASE.json']}
        files['plan.json']=root/'plan.json'
        for j in u['jobs']:files[f'sources/{j["source_sha256"]}.pdf']=Path(j['source_path'])
        path=folder/(u['unit_id']+'.zip')
        write_archive(path,files,{'schema':INPUT_SCHEMA,'unit_id':u['unit_id'],'bundle_index':u['bundle_index'],
            'pages':u['pages'],'jobs':[j['job_id'] for j in u['jobs']],'seed_fragments':[],
            'plan_sha256':digest(root/'plan.json')},'bundle.json')
        entries.append({'unit_id':u['unit_id'],'bundle_index':u['bundle_index'],'filename':path.name,'path':str(path),
            'sha256':digest(path),'bytes':path.stat().st_size,'pages':u['pages'],
            'source_ranges':[{'document_id':j['document_id'],'source_sha256':j['source_sha256'],
                             'first_page':j['first_page'],'last_page':j['last_page']} for j in u['jobs']]})
    index={'schema':INPUT_SCHEMA,'bundle_count':len(units),'pages':sum(counts),'plan_sha256':digest(root/'plan.json'),'bundles':entries}
    atomic_json(folder/'UPLOAD_INDEX.json',index)
    return index,units


def minimal_result(root,entry,plan_sha,name='result.zip',**overrides):
    root=Path(root);data=root/('data_'+name);data.mkdir()
    files={}
    for scope in entry['source_ranges']:
        prefix='runs/'+scope['document_id']+'/'
        manifest=data/(scope['document_id']+'_manifest.json')
        atomic_json(manifest,{'document':{'sha256':scope['source_sha256']}});files[prefix+'manifest.json']=manifest
        records=[];pages=[]
        for page in range(scope['first_page'],scope['last_page']+1):
            asset=data/f'{scope["document_id"]}_{page}.png';asset.write_bytes(f'test asset {page}'.encode())
            assetname=f'assets/slides/page_{page:04d}.png';files[prefix+assetname]=asset
            r={'id':f'p{page}','page':page,'source_sha256':scope['source_sha256']}
            for field in ['crop','context','render']:r[field+'_path']=assetname;r[field+'_sha256']=digest(asset)
            records.append(r);pages.append({'page':page})
        for n,values in [('records.jsonl',records),('document_pages.jsonl',pages)]:
            p=data/(scope['document_id']+'_'+n);p.write_text(''.join(json.dumps(v)+'\n' for v in values),encoding='utf-8');files[prefix+n]=p
    path=root/name
    write_compact_archive(path,files,{'schema':RESULT_SCHEMA,'unit_id':entry['unit_id'],'pages':entry['pages'],
        'input_sha256':entry['sha256'],'plan_sha256':plan_sha,'source_ranges':entry['source_ranges'],
        'processing_complete':True,'training_exported':False,'runs':[s['document_id'] for s in entry['source_ranges']],
        'summary':{'all_jobs_executed':True},**overrides})
    return path


class FakeWorker:
    calls=[];created=[]
    def __init__(self,python,role,engine,logs,*args,**kw):
        self.role=role;self.log_path=Path(logs)/(role+'.log');self.log_path.parent.mkdir(parents=True,exist_ok=True)
        self.log_path.touch(exist_ok=True);self.created.append(role)
    def close(self):pass
    def call(self,packet,out,control,visual_only=False,action='process'):
        if action=='park':return {'completed':True,'result':{'status':'ok'}}
        m=load(packet/'manifest.json');out.mkdir(parents=True,exist_ok=True)
        self.calls.append((self.role,tuple(m['page_map'].values())))
        if self.role=='vlm':
            import vlm_worker
            class Toy:
                telemetry={'possibly_truncated':False}
                def infer(self,*args):return 'A diagram is visible; this is an unverified test observation.'
            vlm_worker.run(packet,out,scope='all',model=Toy())
        elif self.role=='docling':
            atomic_json(out/'parser_candidates_docling.json',{'engine':'docling','status':'ok','parser_candidates':[],
                'original_source_sha256':m['document']['sha256'],'parser_input_sha256':m['parser_input_sha256'],
                'packet_manifest_sha256':digest(packet/'manifest.json'),'semantic_verified':False})
        else:
            for q in select_tasks(m,self.role,visual_only):
                kind='diagram' if self.role=='structure' else q['kind']
                record={'id':q['id'],'page':q['page'],'mode':self.role,'status':'ok','input_file_sha256':q['crop_sha256'],
                    'candidates':[{'page':q['page'],'bbox':[100,100,800,800] if kind=='diagram' else q['bbox'],
                        'kind':kind,'text':'graph algorithm test','engine':'paddle_structure' if self.role=='structure' else 'paddle_ocr',
                        'status':'ok','evidence':{'source_sha256':q['source_sha256'],'region_id':q['id']}}]}
                atomic_json(out/'records'/(q['id'].replace(':','_')+'.json'),record)
        return {'completed':True,'result':{'status':'ok'},'seconds':.01}


class UnitTests(unittest.TestCase):
    def test_partition_exact_134_all_pages_once_and_global_budget(self):
        source=load(ROOT.parent/'colab_orchestrator_v5/fixtures/corpus_plan/plan.json')
        units=partition(source['jobs'])
        self.assertEqual(len(units),134);self.assertEqual([u['pages'] for u in units],[100]*133+[14])
        points=[(j['source_sha256'],p) for u in units for j in u['jobs'] for p in range(j['first_page'],j['last_page']+1)]
        self.assertEqual(len(points),len(set(points)));self.assertEqual(len(points),13314)
        for u in units:self.assertEqual(sum(j['vlm_page_budget'] for j in u['jobs']),u['vlm_page_budget'])

    def test_partition_rejects_missing_source_pages(self):
        with tempfile.TemporaryDirectory() as d:
            _,units=fixture(Path(d),(101,));jobs=[j for u in units for j in u['jobs']]
            jobs[0]['first_page']=2
            with self.assertRaises(ValueError):partition(jobs)

    def test_completed_holes_are_skipped_without_using_last_counter(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            root=Path(d);index,_=fixture(root);store=UnitStore(root/'drive',index)
            e=index['bundles'][1];archive=minimal_result(root,e,index['plan_sha256'])
            store.publish(archive,e)
            atomic_json(root/'drive/queue_state.json',{'completed_units':999,'next_unit':None})
            restarted=UnitStore(root/'drive',index);state=restarted.scan()
            self.assertEqual(state['completed_units'],1);self.assertEqual(state['next_unit'],'unit_0001')
            self.assertNotIn('unit_0002',state['pending_units'])

    def test_final_zip_survives_crash_before_receipt(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            root=Path(d);index,_=fixture(root,(2,));store=UnitStore(root/'drive',index);e=index['bundles'][0]
            archive=minimal_result(root,e,index['plan_sha256'])
            target=root/'drive/results'/e['unit_id']/'orphan.zip';copy_verified(archive,target,quiet=True)
            state=store.scan();self.assertEqual(state['completed_units'],1)
            self.assertTrue(load(store.receipt_path(e['unit_id']))['recovered_orphan_zip'])

    def test_partial_diagnostic_wrong_plan_and_wrong_input_do_not_complete(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            root=Path(d);index,_=fixture(root,(2,));e=index['bundles'][0];store=UnitStore(root/'drive',index)
            folder=root/'drive/results'/e['unit_id'];folder.mkdir(parents=True)
            for n,changes in [('diagnostic',{'diagnostic_only':True}),('input',{'input_sha256':'0'*64}),
                              ('plan',{'plan_sha256':'0'*64}),('missing_runs',{'runs':[]}),('human',{'human_verified':True})]:
                a=minimal_result(root,e,index['plan_sha256'],n+'.zip',**changes);shutil.copyfile(a,folder/a.name)
            (folder/'x.zip.partial').write_bytes(b'not complete');(folder/'x.zip.next').write_bytes(b'not complete')
            self.assertEqual(store.scan()['completed_units'],0)

    def test_missing_and_corrupt_completed_archive_become_pending(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            root=Path(d);index,_=fixture(root,(101,));store=UnitStore(root/'drive',index)
            for i,e in enumerate(index['bundles']):store.publish(minimal_result(root,e,index['plan_sha256'],f'r{i}.zip'),e)
            first=Path(store.completed['unit_0001']['archive']);second=Path(store.completed['unit_0002']['archive'])
            first.unlink();second.write_bytes(b'corrupt')
            self.assertEqual(UnitStore(root/'drive',index).scan()['completed_units'],0)

    def test_publish_copy_failure_does_not_write_complete_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);index,_=fixture(root,(2,));store=UnitStore(root/'drive',index);e=index['bundles'][0]
            archive=minimal_result(root,e,index['plan_sha256'])
            with patch('unit_store.copy_verified',side_effect=OSError('Drive unavailable')):
                with self.assertRaises(OSError):store.publish(archive,e)
            self.assertFalse(store.receipt_path(e['unit_id']).exists())

    def test_native_scope_preserves_original_page_numbers_and_pdf_identity(self):
        from native_batches import prepare_native
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            root=Path(d);_,units=fixture(root,(105,));j={**units[1]['jobs'][0],'run':str(root/'run')}
            prepare_native(j,None,20)
            self.assertEqual([p['page'] for p in rows(root/'run/document_pages.jsonl')],[101,102,103,104,105])
            m=load(root/'run/manifest.json');self.assertEqual(m['document']['pages'],105)
            self.assertEqual(m['document']['sha256'],j['source_sha256'])
            self.assertEqual(len(list((root/'run/assets/slides').glob('*.png'))),5)

    def test_precompleted_seed_is_adopted_without_loading_or_running_models(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            root=Path(d);index,_=fixture(root,(2,));e=index['bundles'][0]
            archive=minimal_result(root,e,index['plan_sha256']);folder=root/'seed';folder.mkdir()
            shutil.copyfile(archive,folder/archive.name)
            atomic_json(folder/'PRECOMPLETED_INDEX.json',{'schema':'v5-unit-precompleted-v1','plan_sha256':index['plan_sha256'],
                'units':[{'unit_id':e['unit_id'],'filename':archive.name,'sha256':digest(archive)}]})
            runner=UnitRunner(root/'drive',root/'work',index,{},folder)
            with patch('unit_queue.UnitCoordinator',side_effect=AssertionError('No model execution')):
                self.assertEqual(runner.scan()['completed_units'],1)
                self.assertTrue(runner.process(e['unit_id'])['reused'])
            runner.close()

    def test_restart_discards_owned_incomplete_local_attempt(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            root=Path(d);index,_=fixture(root,(2,));attempt=root/'work/attempts/unit_0001_old'
            atomic_json(attempt/'ATTEMPT.json',{'unit_id':'unit_0001','plan_sha256':index['plan_sha256']})
            (attempt/'partial_model_output').write_text('unfinished')
            runner=UnitRunner(root/'drive',root/'work',index,{})
            self.assertEqual(runner.scan()['completed_units'],0)
            self.assertFalse(attempt.exists());runner.close()

    def test_whole_queue_restarts_after_failed_unit_without_repeating_saved_unit(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            root=Path(d);index,_=fixture(root,(5,101));FakeWorker.calls=[];FakeWorker.created=[]
            with patch('orchestrator.Worker',FakeWorker),patch('unit_queue.Worker',FakeWorker),patch.dict('os.environ',{'BKQUIZ_SHARED_CACHE':str(root/'cache')}):
                runner=UnitRunner(root/'drive',root/'work',index,ENVS);runner.scan()
                saved=runner.process('unit_0001');calls=list(FakeWorker.calls)
                with patch('unit_queue.UnitCoordinator.run',side_effect=RuntimeError('simulated unit crash')):
                    with self.assertRaises(RuntimeError):runner.process('unit_0002')
                self.assertFalse((root/'drive/receipts/unit_0002.json').exists());runner.close()
                restarted=UnitRunner(root/'drive',root/'fresh_work',index,ENVS);state=restarted.scan()
                self.assertEqual(state['next_unit'],'unit_0002')
                same=restarted.process('unit_0001');self.assertTrue(same['reused']);self.assertEqual(FakeWorker.calls,calls)
                result=restarted.process('unit_0002');restarted.close()
            self.assertEqual(saved['archive_sha256'],same['archive_sha256'])
            self.assertEqual(restarted.store.summary()['completed_units'],2)
            self.assertEqual(list((root/'fresh_work/attempts').iterdir()),[])
            # 100-page unit contains 5 + 95 pages, remaining unit preserves original 96..101.
            self.assertTrue(all(len(pages)<=20 for _,pages in FakeWorker.calls))
            inspect_result(result['archive'],index['bundles'][1],index['plan_sha256'])

    def test_resident_models_reused_across_units_and_engine_survives_cleanup(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            root=Path(d);index,_=fixture(root,(101,));FakeWorker.calls=[];FakeWorker.created=[]
            with patch('orchestrator.Worker',FakeWorker),patch('unit_queue.Worker',FakeWorker),patch.dict('os.environ',{'BKQUIZ_SHARED_CACHE':str(root/'cache')}):
                runner=UnitRunner(root/'drive',root/'work',index,ENVS);runner.scan()
                one=runner.process('unit_0001');two=runner.process('unit_0002');runner.close()
            self.assertEqual(FakeWorker.created.count('vlm'),1);self.assertEqual(FakeWorker.created.count('docling'),1)
            self.assertTrue((root/'work/engine/RELEASE.json').exists())
            # Import in reverse order and preserve an existing human database.
            from import_units import import_units
            import sqlite3
            plan_dir=root/'inputs/plan';plan_dir.mkdir();shutil.copyfile(root/'plan.json',plan_dir/'plan.json')
            plan=load(root/'plan.json');target=root/'local/runs'/plan['jobs'][0]['document_id'];target.mkdir(parents=True)
            db=target/'human_reviews.sqlite3'
            with contextlib.closing(sqlite3.connect(db)) as con:
                con.execute('CREATE TABLE decisions (value TEXT)');con.execute("INSERT INTO decisions VALUES ('keep')");con.commit()
            before=digest(db)
            result=import_units(root/'inputs/UPLOAD_INDEX.json',[two['archive'],one['archive']])
            self.assertEqual(result['units_validated'],2);self.assertEqual(digest(db),before)
            self.assertEqual(len(rows(target/'document_pages.jsonl')),101)
            self.assertTrue(load(target/'manifest.json')['full_document_page_coverage'])
            self.assertTrue(all(not r.get('semantic_verified') for r in rows(target/'records.jsonl')))

    def test_seed_cache_exact_match_reuses_text_without_generation_or_verification(self):
        from native_batches import prepare_native
        from package_cloud import package
        from seed_cache import seed_vlm_cache
        from io_utils import canonical,sha
        from vlm_worker import PROMPT,run
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            root=Path(d);_,units=fixture(root,(1,));job={**units[0]['jobs'][0],'run':str(root/'run')}
            prepare_native(job,None,20);package(root/'run',root/'packet',scope='all')
            m=load(root/'packet/manifest.json');q=m['requests'][0];q.update(use_vlm=True,kind='diagram')
            atomic_json(root/'packet/manifest.json',m)
            prompt=PROMPT+'\nNgữ cảnh nguồn tham khảo (có thể chưa đầy đủ): '+q['context_text'][:240]
            key=sha(canonical({'image':q['vlm_image_sha256'],'target_crop':q['crop_sha256'],'target_bbox':q['bbox'],
                              'kind':q['kind'],'prompt':prompt,'config':m['vlm_config'],'source':q['source_sha256']}))
            record=rows(root/'run/records.jsonl')[0]
            record['candidates'].append({'engine':'vlm','status':'ok','text':'Unchanged cached observation.',
                'evidence':{'cache_key':key,'source_sha256':q['source_sha256'],'crop_sha256':q['crop_sha256'],
                            'input_image_sha256':q['vlm_image_sha256']}})
            (root/'run/records.jsonl').write_text(json.dumps(record)+'\n',encoding='utf-8')
            self.assertEqual(seed_vlm_cache(root/'run',root/'packet',root/'cache'),1)
            class NoGeneration:
                def infer(self,*args):raise AssertionError('Must reuse cached text')
            with patch.dict('os.environ',{'V5_VLM_CACHE':str(root/'cache')}):result=run(root/'packet',root/'out',scope='all',model=NoGeneration())
            observation=result['observations'][0]
            self.assertTrue(observation['cache_hit']);self.assertEqual(observation['text'],'Unchanged cached observation.')
            self.assertFalse(observation['semantic_verified'])

    def test_notebook_pins_independent_queue_and_omits_output(self):
        from build_notebook import build
        nb=load(build());code='\n'.join(''.join(c['source']) for c in nb['cells'] if c['cell_type']=='code')
        for c in nb['cells']:
            if c['cell_type']=='code':compile(''.join(c['source']),'notebook','exec')
        self.assertTrue(nb['metadata']['colab']['private_outputs'])
        for forbidden in ['files.upload(','files.download(','DA_TAI','restore_checkpoint(','SESSION.commit(']:
            self.assertNotIn(forbidden,code)
        self.assertIn('SESSION.scan()',code);self.assertIn('SESSION.process_unit(unit_id)',code)
        self.assertIn("MAX_UNITS=None",code)

    def test_actual_it3170_seed_is_scoped_without_changing_source_or_verification(self):
        from common import checked_extract
        from unit_queue import UnitCoordinator,ModelPool
        index=load(ROOT.parent/'uploads_134_unit100_20261022/UPLOAD_INDEX.json')
        entry=next(e for e in index['bundles'] if len(e['source_ranges'])==1 and e['source_ranges'][0]['course']=='IT3170')
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            attempt=Path(d)/'work/attempts'/entry['unit_id']
            header=checked_extract(entry['path'],attempt/'incoming','bundle.json')
            with patch.dict('os.environ',{'BKQUIZ_SHARED_CACHE':str(Path(d)/'cache')}):
                c=UnitCoordinator(attempt,entry,header,ENVS,ModelPool());c.prepare()
            run=Path(c.jobs[0]['run']);m=load(run/'manifest.json')
            self.assertEqual(m['document']['pages'],1060);self.assertEqual(m['processing_scope']['pages'],100)
            self.assertEqual(load(run/'prepare_summary.json')['full_source_renders'],100)
            self.assertEqual(m['initial_records_sha256'],digest(run/'machine_snapshots/initial.jsonl'))
            expected=set(range(c.jobs[0]['first_page'],c.jobs[0]['last_page']+1))
            self.assertEqual({r['page'] for r in rows(run/'records.jsonl')},expected)
            self.assertTrue(all(not r.get('human_verified') and not r.get('semantic_verified') for r in rows(run/'records.jsonl')))


if __name__=='__main__':unittest.main()
