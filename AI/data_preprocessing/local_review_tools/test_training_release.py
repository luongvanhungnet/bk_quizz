import json
from pathlib import Path
import tempfile
import unittest


class TrainingReleaseTests(unittest.TestCase):
    def test_exact_dedup_preserves_case_and_code_indentation(self):
        from release_training import text_key
        self.assertNotEqual(text_key('X = 1'),text_key('x = 1'))
        self.assertNotEqual(text_key('if x:\n    f()\ng()'),text_key('if x:\n    f()\n    g()'))
        self.assertEqual(text_key('  chữ\n'),text_key('chữ'))

    def test_final_export_quarantines_audit_failures_and_deduplicates_with_protected_splits(self):
        from release_training import finalize_release,write_json,emit,jsonl
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'audit').mkdir();run=root/'run';run.mkdir()
            rows=[]
            # Exact means identical inner whitespace; code indentation is meaningful.
            for i,text in enumerate(['same content','same content','protected knowledge','bad formula','retained extra']):
                rows.append({'id':str(i),'record_id':str(i),'document_id':'doc','course':'TEST','page':i+1,
                    'run':str(run),'source_sha256':'source','text':text,'acceptance':'owner_default_pass',
                    'human_verified':False,'record':{'kind':'text','render_path':None,'image_quality':{},'bbox':[0,0,1000,1000]}})
            rows[1].update(acceptance='review_approve',human_verified=True,review_id='real')
            with (root/'selection.jsonl').open('w',encoding='utf-8') as f:
                for row in rows:emit(f,row)
            with (root/'protected.jsonl').open('w',encoding='utf-8') as f:emit(f,{**rows[2],'id':'holdout','record':{'image_quality':{}},'text':'protected knowledge'})
            write_json(root/'audit/findings.json',{'findings':[{'id':'3','training_action':'exclude'}]})
            write_json(root/'policy.json',{'default_pass_never_reviewed':True})
            result=finalize_release(root)
            sources=list(jsonl(root/'colab/data/sources.jsonl'));texts=list(jsonl(root/'colab/data/train.jsonl'))
            self.assertEqual({s['id'] for s in sources},{'1','4'})
            self.assertEqual({r['text'] for r in texts},{'same content','retained extra'})
            self.assertEqual(result['counts']['audit_quarantine'],1)
            self.assertEqual(result['counts']['protected_exact_text'],1)
            self.assertEqual(result['counts']['exact_duplicate'],1)
            self.assertTrue(next(s for s in sources if s['id']=='1')['human_verified'])

    def test_staging_snapshots_reviews_and_keeps_rejects_and_protected_data_out(self):
        import sqlite3
        from contextlib import closing
        from release_training import stage_release,record_identity
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);workspace=root/'workspace';run=workspace/'runs/doc';run.mkdir(parents=True)
            records=[{'id':str(i),'split':'train','page':i+1,'kind':'text','source_sha256':'source',
                      'proposed_text':'text\u2028'+str(i),'render_path':'page.png'} for i in range(4)]
            records[-1]['split']='holdout'
            (run/'records.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
            (run/'manifest.json').write_text(json.dumps({'document':{'sha256':'source'}}),encoding='utf-8')
            (workspace/'review_catalog.json').write_text(json.dumps({'documents':[
                {'document_id':'doc','course':'TEST','run':str(run),'source_sha256':'source'}]}),encoding='utf-8')
            database=run/'human_reviews.sqlite3'
            with closing(sqlite3.connect(database)) as c:
                c.execute('CREATE TABLE reviews(sequence INTEGER PRIMARY KEY,record_id,payload)')
                for record,decision in zip(records,['approve','reject']):
                    review={'record_id':record['id'],'decision':decision,'identity':record_identity(record),
                            'accepted_text':'saved approval','review_id':record['id']}
                    c.execute('INSERT INTO reviews(record_id,payload) VALUES(?,?)',(record['id'],json.dumps(review)))
                c.commit()
            original=database.read_bytes();source_records=(run/'records.jsonl').read_bytes()
            out=root/'release'
            result=stage_release(workspace,out,default_pass=True)
            with (out/'selection.jsonl').open(encoding='utf-8') as source:selected=[json.loads(line) for line in source]
            self.assertEqual({r['id'] for r in selected},{'doc:0','doc:2'})
            self.assertEqual(result['counts']['excluded_review_reject'],1)
            self.assertEqual(result['counts']['excluded_protected_holdout'],1)
            self.assertEqual(database.read_bytes(),original)
            self.assertEqual((run/'records.jsonl').read_bytes(),source_records)
            self.assertTrue((out/'snapshots/doc.sqlite3').is_file())
            with self.assertRaises(FileExistsError):stage_release(workspace,out,default_pass=True)

    def test_owner_default_applies_only_to_never_reviewed_train_records(self):
        from release_training import resolve_record, record_identity
        record={'id':'same','split':'train','proposed_text':'machine text','machine_revision':'new'}
        accepted=resolve_record(record,None,default_pass=True)
        self.assertEqual(accepted['text'],'machine text')
        self.assertEqual(accepted['acceptance'],'owner_default_pass')
        self.assertFalse(accepted['human_verified'])
        self.assertEqual(resolve_record(record,None,default_pass=False)['excluded'],'not_reviewed')
        for decision in ['approve','correct']:
            review={'identity':record_identity(record),'decision':decision,'accepted_text':'saved text','review_id':'event'}
            row=resolve_record(record,review,default_pass=True)
            self.assertEqual(row['text'],'saved text');self.assertTrue(row['human_verified'])
        for decision in ['reject','defer']:
            review={'identity':record_identity(record),'decision':decision}
            self.assertEqual(resolve_record(record,review,default_pass=True)['excluded'],'review_'+decision)
        stale={'identity':{'machine_revision':'old'},'decision':'approve','accepted_text':'old'}
        self.assertEqual(resolve_record(record,stale,default_pass=True)['excluded'],'stale_review')
        for split in ['development','holdout']:
            self.assertEqual(resolve_record({**record,'split':split},None,default_pass=True)['excluded'],'protected_'+split)
        self.assertEqual(resolve_record({**record,'proposed_text':'  '},None,default_pass=True)['excluded'],'empty_text')


if __name__=='__main__':unittest.main()
