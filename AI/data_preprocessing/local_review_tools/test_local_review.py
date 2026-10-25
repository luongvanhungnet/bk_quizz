import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile
from contextlib import closing

ROOT = Path(__file__).resolve().parent


class LocalReviewTests(unittest.TestCase):
    def test_progress_endpoint_returns_live_counts_without_browser_caching(self):
        from serve import HubHandler
        from http.server import ThreadingHTTPServer
        from types import SimpleNamespace
        import threading
        from urllib.request import urlopen
        counts={'doc':{'remaining':3,'total':6}}
        server=ThreadingHTTPServer(('127.0.0.1',0),HubHandler)
        server.hub=SimpleNamespace(vlm_progress=lambda:counts)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            url=f'http://127.0.0.1:{server.server_port}/api/progress'
            with urlopen(url) as response:
                self.assertEqual(json.load(response),counts)
                self.assertEqual(response.headers['Cache-Control'],'no-store')
            counts['doc']['remaining']=2
            with urlopen(url) as response:self.assertEqual(json.load(response)['doc']['remaining'],2)
        finally:server.shutdown();server.server_close();worker.join()

    def test_hub_vlm_remaining_uses_latest_current_reviews_and_refreshes(self):
        from serve import ReviewHub, ReviewStore
        import sqlite3
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            root=Path(folder);run=root/'runs/doc';run.mkdir(parents=True)
            records=[{'id':str(i),'machine_revision':'current','proposed_text':'description',
                      'candidates':[{'engine':'vlm','status':'ok','text':'description'}]} for i in range(6)]
            records.append({'id':'ocr','proposed_text':'OCR only','candidates':[]})
            (run/'records.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records),encoding='utf-8')
            (root/'review_catalog.json').write_text(json.dumps({'documents':[
                {'document_id':'doc','run':str(run),'course':'TEST','vlm_records':6}]}),encoding='utf-8')
            hub=ReviewHub(root,base_port=0)
            self.assertIn('>6/6</td>',hub.page().decode())
            database=run/'human_reviews.sqlite3'
            self.assertFalse(database.exists(), 'Reading progress must not create a review database')
            with closing(sqlite3.connect(database)) as connection:
                connection.execute('CREATE TABLE reviews(sequence INTEGER PRIMARY KEY,record_id,payload)')
                def append(record,decision,stale=False):
                    identity=ReviewStore._identity(record)
                    if stale:identity['machine_revision']='old'
                    payload={'record_id':record['id'],'decision':decision,'identity':identity}
                    connection.execute('INSERT INTO reviews(record_id,payload) VALUES(?,?)',
                                       (record['id'],json.dumps(payload)))
                    connection.commit()
                for record,decision in zip(records[:3],['approve','correct','reject']):append(record,decision)
                append(records[3],'approve',stale=True)
                append(records[4],'approve');append(records[4],'defer')
                append(records[-1],'approve')
                self.assertIn('>3/6</td>',hub.page().decode())
                append(records[5],'approve')
                self.assertIn('>2/6</td>',hub.page().decode())
                changed=[dict(record,machine_revision='new') for record in records]
                (run/'records.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in changed),encoding='utf-8')
                self.assertIn('>6/6</td>',hub.page().decode())
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM reviews').fetchone()[0],8)

    def test_switching_courses_keeps_only_one_record_cache_and_isolates_same_ids(self):
        from serve import CachedReviewStore
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            stores=[]
            for title in ['A','B']:
                run=Path(folder)/title;run.mkdir()
                (run/'manifest.json').write_text('{}',encoding='utf-8')
                (run/'records.jsonl').write_text(json.dumps({'id':'same','proposed_text':title})+'\n',encoding='utf-8')
                stores.append(CachedReviewStore(run))
            self.assertLessEqual(sum(s._record_cache is not None for s in stores),1)
            self.assertEqual(stores[0].get_record('same')['proposed_text'],'A')
            self.assertEqual(stores[1].get_record('same')['proposed_text'],'B')
            self.assertEqual(stores[0].get_record('same')['proposed_text'],'A')

    def test_restored_history_remains_stale_when_machine_identity_changed(self):
        from restore_reviews import copy_history
        import hashlib
        import sqlite3
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            root=Path(folder);run=root/'run';run.mkdir();source=root/'old.sqlite3'
            (run/'manifest.json').write_text(json.dumps({'document':{'sha256':'0'*64}}),encoding='utf-8')
            (run/'records.jsonl').write_text(json.dumps({'id':'r','machine_revision':'new','source_sha256':'0'*64,'proposed_text':'new'})+'\n',encoding='utf-8')
            payload={'record_id':'r','source_sha256':'0'*64,'review_id':'original','decision':'approve','identity':{'machine_revision':'old'},'accepted_text':'old'}
            with closing(sqlite3.connect(source)) as c:
                c.execute('CREATE TABLE reviews(record_id,created_ns,review_id,payload)')
                c.execute('INSERT INTO reviews VALUES(?,?,?,?)',('r',123,'original',json.dumps(payload)))
                c.commit()
            original=source.read_bytes()
            self.assertEqual(copy_history(source,run,'0'*64),1)
            self.assertEqual(copy_history(source,run,'0'*64),0)
            from serve import CachedReviewStore
            store=CachedReviewStore(run)
            self.assertEqual(len(store.history('r')),1)
            self.assertEqual(store.get_record('r')['review_decision'],'pending')
            self.assertTrue(store.get_record('r')['review_stale'])
            self.assertEqual(source.read_bytes(),original)

    def test_final_assembly_never_overwrites_a_conflicting_region(self):
        from assemble import merge_records
        record={'id':'a','page':2,'proposed_text':'original'}
        self.assertEqual(merge_records([[record],[record]]),[record])
        with self.assertRaises(ValueError):merge_records([[record],[{**record,'proposed_text':'changed'}]])

    def test_publishing_preserves_machine_predictions_and_revisions_exactly(self):
        from ingest import publish_preserved
        record={'id':'one','page':1,'kind':'text','bbox':[0,0,1000,1000],
                'render_path':'page.png','source_sha256':'0'*64,'render_sha256':'1'*64,
                'group_id':'course:TEST','machine_revision':'2'*64,'machine_bucket':'critical',
                'proposed_text':'x\u2028y','reasons':['original_machine_reason'],'candidates':[]}
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            root=Path(folder);receipt={'unit_id':'unit_0001','archive_sha256':'3'*64}
            publish_preserved(root,[record],receipt)
            actual=json.loads((root/'records.jsonl').read_text(encoding='utf-8'))
            self.assertEqual(actual,record)
            publish_preserved(root,[record],receipt)
            self.assertEqual(len(list((root/'import_receipts').glob('*.json'))),1)
            self.assertFalse((root/'human_reviews.sqlite3').exists())

    def test_validation_cache_reuses_only_identical_record_contents(self):
        from ingest import cached_cross_validation
        calls=[]
        def validate(r):
            calls.append(r['text']);return {**r,'derived':'checked'}
        wrapped=cached_cross_validation(validate)
        first={'source_sha256':'source','text':'a'}
        result=wrapped(first)
        self.assertEqual(wrapped(result),result)
        self.assertEqual(wrapped(first),result)
        self.assertEqual(calls,['a'])
        self.assertEqual(wrapped({**first,'text':'b'})['text'],'b')
        self.assertEqual(calls,['a','b'])

    def test_catalog_rejects_incomplete_source_page_coverage(self):
        from verify import check_pages
        with self.assertRaises(ValueError):check_pages([{'page':1},{'page':3}],3)
        with self.assertRaises(ValueError):check_pages([{'page':1},{'page':1}],2)
        self.assertEqual(check_pages([{'page':2},{'page':1}],2),2)

    def test_course_hub_reuses_the_original_ui_and_keeps_reviews_pending(self):
        from serve import ReviewHub
        import hashlib
        from urllib.request import urlopen
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            root=Path(folder);run=root/'runs/doc';run.mkdir(parents=True)
            blob=b'\x89PNG\r\n\x1a\nfixture';sha=hashlib.sha256(blob).hexdigest()
            (run/'page.png').write_bytes(blob)
            (run/'manifest.json').write_text(json.dumps({'document':{'sha256':'0'*64,'pages':1},'asset_root':str(run)}),encoding='utf-8')
            record={'id':'record','page':1,'proposed_text':'description','machine_revision':'revision',
                    'source_sha256':'0'*64,'render_path':'page.png','render_sha256':sha,
                    'candidates':[{'engine':'vlm','status':'ok','text':'description'}]}
            (run/'records.jsonl').write_text(json.dumps(record)+'\n',encoding='utf-8')
            (root/'review_catalog.json').write_text(json.dumps({'documents':[{'document_id':'doc','run':str(run),'course':'TEST'}]}),encoding='utf-8')
            hub=ReviewHub(root,base_port=0)
            try:
                url=hub.open_course('doc','vlm')
                with urlopen(url+'api/bootstrap') as response:boot=json.load(response)
                self.assertEqual(boot['scope'],'vlm')
                with urlopen(url+'api/stats') as response:stats=json.load(response)
                self.assertEqual(stats['pending'],1);self.assertEqual(stats['reviewed'],0)
                with urlopen(url+'api/record/record/image/render') as response:self.assertEqual(response.read(),blob)
                with urlopen(url) as response:self.assertIn('keyboard.js',response.read().decode())
                self.assertEqual(hub.open_course('doc','vlm'),url)
                with self.assertRaises(ValueError):hub.open_course('../doc','vlm')
            finally:hub.close()

    def test_review_store_reads_unicode_separators_without_splitting_records(self):
        from serve import CachedReviewStore
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            root=Path(folder)
            (root/'manifest.json').write_text('{"document":{"pages":1}}',encoding='utf-8')
            record={'id':'record','proposed_text':'x\u2028y\u0085z\u2029','machine_revision':'revision'}
            (root/'records.jsonl').write_text(json.dumps(record,ensure_ascii=False)+'\n',encoding='utf-8')
            store=CachedReviewStore(root)
            self.assertEqual(store.get_record('record')['proposed_text'],record['proposed_text'])
            self.assertEqual(store.stats()['pending'],1)
            self.assertEqual(store.stats()['reviewed'],0)

    def test_review_materialization_keeps_assets_but_never_links_source_records(self):
        from ingest import materialize_review
        import hashlib
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            root=Path(folder); archive=root/'return.zip'; target=root/'expanded'
            record={'id':'a','page':1,'render_path':'assets/page.png','crop_path':'assets/page.png','context_path':'assets/page.png'}
            files={'runs/doc/records.jsonl':(json.dumps(record)+'\n').encode(),
                   'runs/doc/document_pages.jsonl':b'{"page":1}\n',
                   'runs/doc/manifest.json':b'{"document":{"pages":1}}',
                   'runs/doc/assets/page.png':b'image-bytes', 'raw_results/log.json':b'{"raw":true}'}
            logical={n:hashlib.sha256(b).hexdigest() for n,b in files.items()}
            manifest={'runs':['doc'],'logical_files':logical,'files':{'objects/'+h:h for h in logical.values()}}
            with zipfile.ZipFile(archive,'w') as z:
                for n,b in files.items():z.writestr('objects/'+logical[n],b)
                z.writestr('return.json',json.dumps(manifest))
            materialize_review(archive,target,'return.json')
            self.assertEqual((target/'runs/doc/assets/page.png').read_bytes(),b'image-bytes')
            self.assertTrue(os.path.samefile(target/'runs/doc/assets/page.png',target/'objects'/logical['runs/doc/assets/page.png']))
            self.assertFalse(os.path.samefile(target/'runs/doc/records.jsonl',target/'objects'/logical['runs/doc/records.jsonl']))
            self.assertFalse((target/'raw_results/log.json').exists())

    def test_immutable_copies_share_storage_without_replacing_existing_files(self):
        from ingest import link_copy
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            root = Path(folder); source = root/'source'; target = root/'target'
            source.write_bytes(b'immutable-image')
            link_copy(source, target)
            self.assertTrue(os.path.samefile(source, target))
            with self.assertRaises(FileExistsError):
                link_copy(source, target)
            self.assertEqual(source.read_bytes(), b'immutable-image')

    def test_download_member_must_be_a_unit_zip_inside_results(self):
        from ingest import download_member
        self.assertEqual(download_member('results/unit_0001/result.zip'), 'unit_0001')
        for name in ['../results/unit_0001/result.zip', 'results/unit_0001/../../evil.zip',
                     'results/unit_0000/result.zip', 'results/unit_0135/result.zip',
                     'results/unit_0001/result.txt', 'C:/results/unit_0001/result.zip']:
            with self.assertRaises(ValueError, msg=name):
                download_member(name)


if __name__ == '__main__':
    unittest.main()
