import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
ENGINE=ROOT.parent.parent/'Qwen_cpt_version/region_preprocessing_v5_official'
sys.path.insert(0,str(ENGINE));sys.path.insert(0,str(ROOT))
from common import VERSION,atomic_json,checked_extract,checkpoint,digest,load,rows,write_archive
from build_balanced import balance,size_stats
from sequential import SequentialCoordinator,assert_next
from warm_worker import Engines,LazyObserver,select_tasks


class SequenceTests(unittest.TestCase):
    def test_cannot_upload_next_before_download_acknowledgement(self):
        state={'last_acknowledged_index':0}
        good={'schema':VERSION,'sequence_required':True,'bundle_index':1}
        assert_next(state,good)
        with self.assertRaises(ValueError):assert_next(state,{**good,'bundle_index':2})
        state['last_acknowledged_index']=1;assert_next(state,{**good,'bundle_index':2})

    def test_ack_requires_finished_export_and_matching_hash(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c=SequentialCoordinator(root/'base',root/'work',{})
            with self.assertRaises(ValueError):c.acknowledge(1,'bad')
            archive=root/'output.zip';archive.write_bytes(b'valid output')
            c.state['finished_inputs']['1']={'archive':str(archive),'archive_sha256':digest(archive)}
            with self.assertRaises(ValueError):c.acknowledge(1,'bad')
            c.acknowledge(1,digest(archive));self.assertEqual(c.state['last_acknowledged_index'],1)
            self.assertTrue(c.state['finished_inputs']['1']['download_confirmed'])
            with self.assertRaises(ValueError):c.acknowledge(1,digest(archive))

    def test_balancing_reduces_variance_and_places_shared_source_first(self):
        units=[{'id':str(i),'weight':x,'shared_source':i==0} for i,x in enumerate([17,100,50,40,30,30,30,25,20,20,18,17,16,15,14,13,12,11,10])]
        bins=balance(units,5)
        self.assertTrue(any(u.get('shared_source') for u in bins[0]['units']))
        self.assertEqual(sorted(u['id'] for b in bins for u in b['units']),sorted(u['id'] for u in units))
        self.assertLess(size_stats([b['weight'] for b in bins])['population_variance_bytes2'],size_stats([300,100,50,50,48])['population_variance_bytes2'])

    def test_seed_fragments_append_without_overwriting_processed_candidates(self):
        import corpus
        import pymupdf
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);docs=root/'docs';docs.mkdir();pdf=pymupdf.open()
            for i in range(2):pdf.new_page().insert_text((50,50),'page '+str(i))
            pdf.save(docs/'A-test.pdf');pdf.close()
            cfg={'source_root':str(docs),'work_root':str(root/'origin'),'pages_per_packet':1,'maximum_packet_bytes':536870912,
                 'upstream_manifest':str(root/'none'),'upstream_page_map':str(root/'none'),'reuse_runs':[]}
            with contextlib.redirect_stdout(io.StringIO()):
                corpus.inventory(cfg,root/'catalog');jobs=corpus.plan(cfg,root/'catalog',root/'plan');corpus.prepare_documents(cfg,jobs)
            source=Path(jobs[0]['run']);allrows=rows(source/'records.jsonl');allpages=rows(source/'document_pages.jsonl')
            c=SequentialCoordinator(root/'base',root/'work',{});incoming=c.work/'incoming';assetroot=incoming/'seed_assets'/jobs[0]['document_id']
            shutil.copytree(source/'assets',assetroot/'assets')
            fragments=[]
            for i in range(2):
                prefix=f'fragments/{i}';p=incoming/prefix;p.mkdir(parents=True)
                for name in ['manifest.json','prepare_summary.json','classification.json','duplicate_candidates.json']:
                    if (source/name).exists():shutil.copy2(source/name,p/name)
                (p/'records.jsonl').write_text(json.dumps(allrows[i])+'\n',encoding='utf-8')
                (p/'document_pages.jsonl').write_text(json.dumps(allpages[i])+'\n',encoding='utf-8')
                fragments.append({'document_id':jobs[0]['document_id'],'prefix':prefix,'records_sha256':digest(p/'records.jsonl'),
                                  'source_sha256':jobs[0]['source_sha256'],'pages':[i+1]})
            c._fragment(fragments[0]);run=c.work/'runs'/jobs[0]['document_id']
            current=rows(run/'records.jsonl');current[0]['candidates'].append({'engine':'paddle_ocr','text':'processed text','status':'ok','evidence':{}})
            (run/'records.jsonl').write_text(json.dumps(current[0])+'\n',encoding='utf-8')
            c._fragment(fragments[1]);c._fragment(fragments[0])
            result=rows(run/'records.jsonl')
            self.assertEqual(len(result),2);self.assertTrue(any(x['text']=='processed text' for x in result[0]['candidates']))
            self.assertEqual(load(run/'manifest.json')['seed_pages_present'],[1,2])

    def test_model_is_moved_cpu_cuda_without_another_load(self):
        moves=[]
        class Model:
            def to(self,device):moves.append(device)
        class CUDA:
            def synchronize(self):pass
            def empty_cache(self):pass
        class Observer:
            def __init__(self):self.model=Model();self.torch=type('Torch',(),{'cuda':CUDA()})()
            def memory(self):return {'allocated':0}
        e=Engines('vlm');e.model=LazyObserver({},lambda cfg:Observer());e.model.observer=Observer();e.model.initializations=1
        e.move_vlm('cpu');self.assertTrue(e.parked)
        e.move_vlm('cuda:0');self.assertFalse(e.parked)
        self.assertEqual(moves,['cpu','cuda:0']);self.assertEqual(e.model.initializations,1)

    def test_vlm_worker_survives_two_bundle_boundaries(self):
        events=[]
        class Fake:
            def __init__(self,*args):events.append('load')
            def call(self,*args,**kwargs):events.append(kwargs.get('action','infer'));return {'completed':True,'result':{'status':'ok'}}
            def close(self):events.append('close')
        with tempfile.TemporaryDirectory() as d:
            r=Path(d);c=SequentialCoordinator(r/'base',r/'work',{'vlm':'python'});c.engine=ENGINE
            def execute(worker,job,phase):c.state['stages'][job['job_id']+':'+phase+':vlm']={};events.append('infer')
            with patch('sequential.Worker',Fake),patch.object(c,'execute_stage',execute):
                c.group_stage('vlm',[({'job_id':'a'},'inference')]);c.group_stage('vlm',[({'job_id':'b'},'inference')]);c.close()
            self.assertEqual(events.count('load'),1);self.assertEqual(events.count('park'),2);self.assertEqual(events.count('close'),1)


class IntegrationTests(unittest.TestCase):
    def test_incremental_snapshots_same_document_import_latest_in_either_order(self):
        import corpus,pymupdf,import_returns
        with tempfile.TemporaryDirectory() as d:
            r=Path(d);(r/'docs').mkdir();pdf=pymupdf.open()
            for i in range(2):pdf.new_page().insert_text((50,50),'academic page '+str(i))
            pdf.save(r/'docs/A-test.pdf');pdf.close()
            cfg={'source_root':str(r/'docs'),'work_root':str(r/'origin'),'pages_per_packet':1,'maximum_packet_bytes':536870912,
                 'upstream_manifest':str(r/'none'),'upstream_page_map':str(r/'none'),'reuse_runs':[]}
            with contextlib.redirect_stdout(io.StringIO()):
                corpus.inventory(cfg,r/'catalog');jobs=corpus.plan(cfg,r/'catalog',r/'plan');corpus.prepare_documents(cfg,jobs)
            seed=Path(jobs[0]['run']);did=jobs[0]['document_id'];allrows=rows(seed/'records.jsonl')
            for j in jobs:j['run']=str(r/'imported'/did)
            (r/'plan/jobs.jsonl').write_text(''.join(json.dumps(j)+'\n' for j in jobs),encoding='utf-8')
            archives=[]
            for i in [1,2]:
                snap=r/f'snapshot{i}';shutil.copytree(seed,snap)
                (snap/'records.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in allrows[:i]),encoding='utf-8')
                atomic_json(snap/'sequential_export.json',{'sequence_index':i})
                files={f'runs/{did}/{p.relative_to(snap).as_posix()}':p for p in snap.rglob('*') if p.is_file()}
                archive=r/f'return{i}.zip'
                write_archive(archive,files,{'schema':VERSION,'plan_sha256':'test','original_jobs_sha256':digest(r/'plan/jobs.jsonl'),
                             'runs':[did],'phase_results':[],'sequence_index':i,'bundle_id':f'upload_{i:02d}'},'return.json')
                archives.append(archive)
            atomic_json(r/'index.json',{'plan_sha256':'test'})
            with contextlib.redirect_stdout(io.StringIO()):
                first=import_returns.import_returns(r/'plan',r/'index.json',archives)
                checked=import_returns.import_returns(r/'plan',r/'index.json',list(reversed(archives)),check_only=True)
            self.assertEqual(first['new_local_runs'],1);self.assertEqual(len(rows(Path(jobs[0]['run'])/'records.jsonl')),2)
            self.assertEqual(checked['final_runs_validated'],1)

    def test_two_inputs_process_export_ack_then_resume_and_import(self):
        import corpus,pymupdf,vlm_worker
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);docs=root/'docs';docs.mkdir()
            for name in ['A-one.pdf','B-two.pdf']:
                pdf=pymupdf.open();pdf.new_page(width=600,height=400).insert_text((50,50),'graph academic text');pdf.save(docs/name);pdf.close()
            cfg={'source_root':str(docs),'work_root':str(root/'local'),'pages_per_packet':1,'maximum_packet_bytes':536870912,
                 'vlm_target_fraction':.05,'vlm_maximum_fraction':.08,'upstream_manifest':str(root/'none'),'upstream_page_map':str(root/'none'),'reuse_runs':[]}
            with contextlib.redirect_stdout(io.StringIO()):corpus.inventory(cfg,root/'catalog');jobs=corpus.plan(cfg,root/'catalog',root/'plan')
            plan={'jobs':jobs,'config':cfg,'bundle_count':2,'jobs_sha256':digest(root/'plan/jobs.jsonl'),'release_manifest_sha256':digest(ENGINE/'RELEASE.json')}
            atomic_json(root/'plan.json',plan)
            enginefiles={f'engine/{n}':ENGINE/n for n in [*load(ENGINE/'RELEASE.json')['files'],'RELEASE.json']}
            inputs=[]
            for i,j in enumerate(jobs,1):
                p=root/f'input{i}.zip';write_archive(p,{**enginefiles,'plan.json':root/'plan.json',f'sources/{j["source_sha256"]}.pdf':Path(j['source_path'])},
                    {'schema':VERSION,'bundle_id':f'upload_{i:02d}','bundle_index':i,'bundle_count':2,'sequence_required':True,'jobs':[j['job_id']],
                     'plan_sha256':digest(root/'plan.json'),'seed_fragments':[],'completed_jobs':[]},'bundle.json');inputs.append(p)
            class Toy:
                telemetry={'possibly_truncated':False}
                def infer(self,*args):return 'Academic diagram'
            class Fake:
                def __init__(self,python,role,*args,**kw):self.role=role
                def close(self):pass
                def call(self,packet,out,control,visual_only=False,action='process'):
                    if action=='park':return {'completed':True,'result':{'status':'ok'}}
                    m=load(packet/'manifest.json');out.mkdir(parents=True,exist_ok=True)
                    if self.role=='vlm':vlm_worker.run(packet,out,scope='all',model=Toy())
                    elif self.role!='docling':
                        rs=[]
                        for q in select_tasks(m,self.role,visual_only):
                            kind='diagram' if self.role=='structure' else 'text'
                            record={'id':q['id'],'page':q['page'],'mode':self.role,'status':'ok','input_file_sha256':q['crop_sha256'],
                                    'candidates':[{'page':q['page'],'bbox':[100,100,800,800] if kind=='diagram' else q['bbox'],'kind':kind,
                                    'text':'graph academic text','engine':'paddle_structure' if kind=='diagram' else 'paddle_ocr','status':'ok',
                                    'evidence':{'source_sha256':q['source_sha256'],'region_id':q['id']}}]}
                            rs.append(record);atomic_json(out/'records'/(q['id'].replace(':','_')+'.json'),record)
                        atomic_json(out/'results_fake.json',{'mode':self.role,'records':rs})
                    return {'completed':True,'result':{'status':'ok'}}
            envs={'controller':sys.executable,'paddle':sys.executable,'docling':sys.executable,'vlm':sys.executable}
            with patch('orchestrator.Worker',Fake),patch('sequential.Worker',Fake),patch.dict('os.environ',{'BKQUIZ_SHARED_CACHE':str(root/'cache')}),contextlib.redirect_stdout(io.StringIO()):
                c=SequentialCoordinator(root/'base',root/'work',envs)
                first=c.process(inputs[0]);self.assertTrue(Path(first['archive']).exists())
                with self.assertRaises(ValueError):c.process(inputs[1])
                c.acknowledge(1,first['archive_sha256']);c.close()
                # New controller/work directory emulates loss of runtime RAM/disk.
                c=SequentialCoordinator(root/'base',root/'new_work',envs)
                second=c.process(inputs[1]);c.acknowledge(2,second['archive_sha256']);c.close()
            self.assertEqual(c.state['last_acknowledged_index'],2)
            for archive in [first['archive'],second['archive']]:checked_extract(archive,root/Path(archive).stem,'return.json')
            import import_returns
            atomic_json(root/'index.json',{'plan_sha256':digest(root/'plan.json')})
            with contextlib.redirect_stdout(io.StringIO()):
                result=import_returns.import_returns(root/'plan',root/'index.json',[first['archive'],second['archive']])
            self.assertEqual(result['new_local_runs'],2);self.assertEqual(result['human_decisions_auto_created'],0)

    def test_notebook_one_upload_download_ack_order_and_separate_drive(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('nb_v2',ROOT/'build_notebook.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        nb=load(module.build());code=[''.join(c['source']) for c in nb['cells'] if c['cell_type']=='code']
        for s in code:compile(s,'notebook','exec')
        drive=next(s for s in code if 'drive.mount(' in s);upload=next(s for s in code if 'def upload_one(' in s)
        loop=next(s for s in code if 'while True:' in s)
        self.assertNotIn('files.upload(',drive);self.assertNotIn('drive.mount(',upload);self.assertIn('len(uploaded)==1',upload)
        self.assertLess(loop.index('files.download('),loop.index('SESSION.acknowledge('))
        self.assertLess(loop.index('SESSION.acknowledge('),loop.index('INPUT=upload_one()'))
        self.assertNotIn('setup(BASE)',loop)


if __name__=='__main__':unittest.main()
