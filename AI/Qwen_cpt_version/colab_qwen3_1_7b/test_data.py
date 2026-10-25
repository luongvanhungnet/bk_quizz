import hashlib
import tempfile
import unittest
from pathlib import Path
from data_utils import pack,padded_batch,save,write_jsonl,verify_bundle,sha,latest_checkpoint


class DataTests(unittest.TestCase):
    def test_packing_preserves_tokens_eos_and_unshifted_labels(self):
        rows=[{'text':'ab'},{'text':'cd'}];sources=[{'id':'x','page':1},{'id':'y','page':2}]
        batches=pack(rows,sources,lambda s:[ord(c) for c in s],999,4)
        self.assertEqual([t for r in batches for t in r['input_ids']],[97,98,999,99,100,999])
        self.assertTrue(all(r['labels']==r['input_ids'] for r in batches))
        self.assertEqual(batches[0]['source_spans'][-1]['source_token_end'],1)
        self.assertEqual(batches[1]['source_spans'][0]['source_token_start'],1)

    def test_single_token_tail_borrows_without_loss(self):
        batches=pack([{'text':'abcd'}],[{'id':'x','page':1}],lambda _: [1,2,3,4],99,4)
        self.assertEqual([r['input_ids'] for r in batches],[[1,2,3],[4,99]])
        self.assertEqual(batches[1]['source_spans'][0]['source_token_start'],3)

    def test_real_eos_not_masked_when_used_as_padding(self):
        result=padded_batch([{'input_ids':[10,99]},{'input_ids':[20,21,99]}],99)
        self.assertEqual(result['labels'][0][:3],[10,99,-100])
        self.assertEqual(result['attention_mask'][0][:3],[1,1,0])
        self.assertEqual(result['input_ids'][0][2],99)

    def test_bundle_checksum_detects_changed_training_text(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);text='Thuật toán 2^10 = 1024'
            write_jsonl(root/'data/train.jsonl',[{'text':text}])
            write_jsonl(root/'data/sources.jsonl',[{'text_sha256':hashlib.sha256(text.encode()).hexdigest()}])
            save(root/'data/manifest.json',{'samples':1,'files_sha256':{n:sha(root/n) for n in ['data/train.jsonl','data/sources.jsonl']}})
            self.assertEqual(verify_bundle(root)[0][0]['text'],text)
            write_jsonl(root/'data/train.jsonl',[{'text':'changed'}])
            with self.assertRaises(ValueError):verify_bundle(root)

    def test_resume_skips_incomplete_last_checkpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);good=root/'checkpoint-2';good.mkdir();(root/'checkpoint-3').mkdir()
            for name in ['trainer_state.json','adapter_config.json','adapter_model.safetensors','optimizer.pt','scheduler.pt','rng_state.pth']:
                (good/name).write_text('state')
            save(good/'trainer_state.json',{'global_step':2});save(good/'adapter_config.json',{'r':8})
            for path in good.iterdir():
                (root/'checkpoint-3'/path.name).write_bytes(path.read_bytes())
            (root/'checkpoint-3/trainer_state.json').write_text('{')
            self.assertEqual(latest_checkpoint(root),good)


if __name__=='__main__':unittest.main()
