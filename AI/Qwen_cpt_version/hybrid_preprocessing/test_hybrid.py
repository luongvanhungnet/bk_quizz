import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch
import zipfile
from local_pipeline import dedup,merge,digest


def row(page,text,image):
    return {'id':f'p{page}','page':page,'text':text,'source':{'render_sha256':image}}


class HybridChecks(unittest.TestCase):
    def test_same_labels_different_diagrams_are_not_removed(self):
        rows=[row(1,'A B C','diagram-1'),row(2,'A B C','diagram-2'),row(3,'A B C','diagram-1')]
        result=dedup(rows)
        self.assertIsNone(rows[1]['duplicate_of'])
        self.assertEqual(rows[2]['duplicate_of'],'p1')
        self.assertEqual(len(result['exact_duplicates']),1)

    def test_near_duplicate_with_different_numeric_limit_survives(self):
        text='Tìm kiếm nhị phân xét chỉ số giữa rồi thu hẹp khoảng tìm kiếm. '*10
        rows=[row(1,text+'n=16','one'),row(2,text+'n=32','two')]
        result=dedup(rows)
        self.assertTrue(result['near_pairs'])
        self.assertTrue(all(r['duplicate_of'] is None for r in rows))
        self.assertIn('32',rows[1]['text'])

    def test_simhash_candidates_do_not_depend_on_minhash_query(self):
        text='Quy hoạch động giữ lời giải các bài toán con để tính bài toán lớn. '*4
        with patch('local_pipeline.MinHashLSH.query',return_value=[]):
            result=dedup([row(1,text,'one'),row(2,text,'two')])
        self.assertTrue(result['near_pairs'][0]['simhash_match'])
        self.assertFalse(result['near_pairs'][0]['minhash_candidate'])

    def test_cloud_zip_from_other_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'request_manifest.json').write_text('{"requests":[]}')
            zpath=root/'result.zip'
            with zipfile.ZipFile(zpath,'w') as z:z.writestr('results.json',json.dumps({'manifest_sha256':'wrong','pages':[]}))
            with self.assertRaisesRegex(ValueError,'different input manifest'):
                merge(Namespace(run=root,results=zpath,reviews=None))

    def test_unreviewed_cloud_predictions_never_export_training_text(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);request={'page':1,'document_sha256':'doc','render_sha256':'render'}
            (root/'request_manifest.json').write_text(json.dumps({'requests':[request]}))
            manifest_hash=digest((root/'request_manifest.json').read_bytes())
            result={'manifest_sha256':manifest_hash,'pages':[{**request,'paddle':{'status':'not_run'},'vlm':{**request,'manifest_sha256':manifest_hash,'status':'ok','prediction':{'transcript':'unverified'}}}]}
            zpath=root/'result.zip'
            with zipfile.ZipFile(zpath,'w') as z:z.writestr('results.json',json.dumps(result))
            merge(Namespace(run=root,results=zpath,reviews=None))
            self.assertTrue((root/'cloud_review_queue.jsonl').is_file())
            self.assertFalse((root/'reviewed_cpt/train.jsonl').exists())


if __name__=='__main__':unittest.main()
