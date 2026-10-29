"""CPU-only fixtures; no weights are downloaded, loaded or trained."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sft_contract import (SCHEMA,MODEL_ID,MODEL_REVISION,CPT_HASHES,EOS_ID,SPLITS,canonical,digest,sha,load,save,
                         encode_chat,validate_messages,validate_tokens,verify_adapter,verify_dataset,
                         padded_batch,native_bf16,complete_checkpoint,latest_checkpoint,inside)
from train_sft import check_config,finalize_artifact


class FixtureTokenizer:
    eos_token="<|im_end|>";eos_token_id=EOS_ID
    def apply_chat_template(self,messages,tokenize=False,add_generation_prompt=False,enable_thinking=True):
        if enable_thinking:raise AssertionError("Thinking must be disabled")
        result=""
        for m in messages:
            prefix=m['role']+":"
            if m['role']=='assistant':prefix+="<think>\n\n</think>\n\n"
            result+=prefix+m['content']+self.eos_token+"\n"
        if add_generation_prompt:result+="assistant:<think>\n\n</think>\n\n"
        return result
    def __call__(self,text,**kwargs):
        parts=text.split(self.eos_token);result=[]
        for index,part in enumerate(parts):
            if index:result.append(EOS_ID)
            result.extend(ord(char)+2 for char in part)
        return {"input_ids":result}
    def decode(self,tokens,skip_special_tokens=False):
        return ''.join(self.eos_token if token==EOS_ID else chr(token-2) for token in tokens)


def chat(label):return {"messages":[{"role":"system","content":"Biên soạn JSON quiz từ nguồn."},
                         {"role":"user","content":"Tài liệu của câu hỏi "+label},
                         {"role":"assistant","content":json.dumps({"questions":[{"prompt":label}]},ensure_ascii=False)}]}


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.tokenizer=FixtureTokenizer()
        save(self.root/"MODEL_PROVENANCE.json",{"base_model":MODEL_ID,"base_revision":MODEL_REVISION,"current_cpt_adapter_sha256":CPT_HASHES})
        save(self.root/"selection_policy.json",{"source_policy":"completed_native_pages_only","all_origin_pages_must_be_complete":True,
             "no_teacher_outputs_used":True,"no_pending_stage2_questions_used":True,"excluded_review_items":0,"excluded_physical_pages":0})
        (self.root/"excluded_pages.jsonl").write_bytes(b'');originals=[]
        for name in ("tokenizer.json","tokenizer_config.json","chat_template.jinja"):save(self.root/"tokenizer"/name,{"test_fixture":True})
        for split in SPLITS:
            row=chat(split);identity="fixture_"+split
            self.write(split+".messages.jsonl",row)
            sources=[{"source_id":"source_"+split,"pages":[1]}]
            self.write(split+".metadata.jsonl",{"id":identity,"split":split,"split_group":"family_"+split,"sources":sources,
                        "completion_origin":"frozen_native_release","requires_additional_llm":False,"requires_vlm":False,
                        "requires_manual_completion":False,"source_pages_complete":True})
            originals.append({"id":identity,"origins":sources})
            self.write("tokenized/"+split+".jsonl",encode_chat(self.tokenizer,row,identity))
        (self.root/"source_questions.jsonl").write_bytes(b''.join(canonical(row)+b'\n'for row in originals));self.refresh()
    def tearDown(self):self.temp.cleanup()
    def write(self,name,value):
        target=self.root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(canonical(value)+b'\n')
    def refresh(self):
        save(self.root/"manifest.json",{"schema":SCHEMA,"source_policy":"completed_native_pages_only","counts":{s:1 for s in SPLITS},
                "max_length":4096,"tokenizer_eos_token_id":EOS_ID,"source_policy_sha256":sha(self.root/'selection_policy.json'),
                "files_sha256":{p.relative_to(self.root).as_posix():sha(p) for p in self.root.rglob('*')if p.is_file()and p.name!='manifest.json'}})
    def verify(self):return verify_dataset(self.root,self.tokenizer,verify_cpt=False)
    def mutate(self,name,fn):
        value=json.loads((self.root/name).read_text());fn(value);self.write(name,value);self.refresh()
    def test_valid_bundle_retokenizes_all_splits(self):
        manifest,provenance,rows,report=self.verify();self.assertTrue(report['chat_mask_retokenized']);self.assertEqual(report['counts'],{s:1 for s in SPLITS})
    def test_hash_mutation_rejected(self):
        self.write('train.messages.jsonl',chat('tampered'))
        with self.assertRaisesRegex(ValueError,'hash mismatch'):self.verify()
    def test_counts_mismatch(self):
        manifest=load(self.root/'manifest.json');manifest['counts']['train']=2;save(self.root/'manifest.json',manifest)
        with self.assertRaisesRegex(ValueError,'count mismatch'):self.verify()
    def test_wrong_student_revision_rejected(self):
        self.mutate('MODEL_PROVENANCE.json',lambda v:v.update(base_revision='wrong'))
        with self.assertRaisesRegex(ValueError,'provenance'):self.verify()
    def test_source_policy_cannot_include_pending_pages(self):
        manifest=load(self.root/'manifest.json');manifest['source_policy']='all_pages';save(self.root/'manifest.json',manifest)
        with self.assertRaisesRegex(ValueError,'completed-native'):self.verify()
    def test_pending_completion_flag_rejected_even_if_policy_claims_complete(self):
        self.mutate('train.metadata.jsonl',lambda v:v.update(requires_vlm=True))
        with self.assertRaisesRegex(ValueError,'requires completion'):self.verify()
    def test_missing_completion_flag_fails_closed(self):
        self.mutate('train.metadata.jsonl',lambda v:v.pop('requires_manual_completion'))
        with self.assertRaisesRegex(ValueError,'requires completion'):self.verify()
    def test_forged_complete_metadata_cannot_use_excluded_page(self):
        self.write('excluded_pages.jsonl',{'source_id':'source_train','page':1})
        policy=load(self.root/'selection_policy.json');policy.update(excluded_review_items=1,excluded_physical_pages=1);save(self.root/'selection_policy.json',policy);self.refresh()
        with self.assertRaisesRegex(ValueError,'touches excluded'):self.verify()
    def test_omitted_original_dependency_fails_closed(self):
        rows=[json.loads(line)for line in(self.root/'source_questions.jsonl').read_text().split('\n')if line]
        rows[0]['origins'].append({'source_id':'omitted_original','pages':[99]})
        (self.root/'source_questions.jsonl').write_bytes(b''.join(canonical(row)+b'\n'for row in rows));self.refresh()
        with self.assertRaisesRegex(ValueError,'all-origin page provenance'):self.verify()
    def test_every_origin_page_checked_not_only_first(self):
        meta=load(self.root/'train.metadata.jsonl');meta['sources'][0]['pages']=[1,2];self.write('train.metadata.jsonl',meta)
        rows=[json.loads(line)for line in(self.root/'source_questions.jsonl').read_text().split('\n')if line]
        rows[0]['origins'][0]['pages']=[1,2]
        (self.root/'source_questions.jsonl').write_bytes(b''.join(canonical(row)+b'\n'for row in rows))
        self.write('excluded_pages.jsonl',{'source_id':'source_train','page':2})
        policy=load(self.root/'selection_policy.json');policy.update(excluded_review_items=1,excluded_physical_pages=1);save(self.root/'selection_policy.json',policy);self.refresh()
        with self.assertRaisesRegex(ValueError,'touches excluded'):self.verify()
    def test_selection_policy_requires_all_origins_complete(self):
        self.mutate('selection_policy.json',lambda v:v.update(all_origin_pages_must_be_complete=False))
        with self.assertRaisesRegex(ValueError,'Selection policy'):self.verify()
    def test_question_family_leak_rejected(self):
        self.mutate('test.metadata.jsonl',lambda v:v.update(split_group='family_train'))
        with self.assertRaisesRegex(ValueError,'family crosses'):self.verify()
    def test_sample_split_mismatch_rejected(self):
        self.mutate('test.metadata.jsonl',lambda v:v.update(split='train'))
        with self.assertRaisesRegex(ValueError,'split mismatch'):self.verify()
    def test_mismatched_tokenization_rejected(self):
        self.mutate('train.messages.jsonl',lambda v:v['messages'][1].update(content='Changed input with same stored labels'))
        with self.assertRaisesRegex(ValueError,'token mask differs'):self.verify()
    def test_no_reserved_think_markers_in_content(self):
        row=chat('fixture');row['messages'][1]['content']='<think>forbidden'
        with self.assertRaisesRegex(ValueError,'Reserved'):validate_messages(row)
    def test_mask_supervises_only_assistant_plus_eos(self):
        row=chat('sample');encoded=encode_chat(self.tokenizer,row,'id');targets=[v for v in encoded['labels']if v!=-100]
        self.assertEqual(self.tokenizer.decode(targets),row['messages'][-1]['content']+self.tokenizer.eos_token)
        self.assertNotIn('<think>',self.tokenizer.decode(targets))
        self.assertEqual(encoded['labels'][0],-100)
    def test_noncontiguous_targets_rejected(self):
        value=encode_chat(self.tokenizer,chat('x'),'id');first=next(i for i,v in enumerate(value['labels'])if v!=-100);value['labels'][first+1]=-100
        with self.assertRaisesRegex(ValueError,'contiguous'):validate_tokens(value)
    def test_label_token_mismatch_rejected(self):
        value=encode_chat(self.tokenizer,chat('x'),'id');first=next(i for i,v in enumerate(value['labels'])if v!=-100);value['labels'][first]+=1
        with self.assertRaisesRegex(ValueError,'equal its input'):validate_tokens(value)
    def test_missing_eos_rejected(self):
        value=encode_chat(self.tokenizer,chat('x'),'id');position=value['labels'].index(EOS_ID);value['labels'][position]=-100
        with self.assertRaisesRegex(ValueError,'supervised im_end'):validate_tokens(value)
    def test_overlength_is_not_truncated(self):
        value=encode_chat(self.tokenizer,chat('x'),'id')
        with self.assertRaisesRegex(ValueError,'overlength'):validate_tokens(value,10)
    def test_padding_preserves_prompt_and_eos_masks(self):
        value={'input_ids':[11,22,EOS_ID,33],'attention_mask':[1,1,1,1],'labels':[-100,22,EOS_ID,-100]}
        batch=padded_batch([value],EOS_ID)
        self.assertEqual(batch['labels'][0],[-100,22,EOS_ID,-100,-100,-100,-100,-100])
        self.assertEqual(batch['attention_mask'][0],[1,1,1,1,0,0,0,0])
    def test_adapter_wrong_hash_fails_closed(self):
        adapter=self.root/'assets/cpt_adapter';adapter.mkdir(parents=True);(adapter/'adapter_config.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'Wrong CPT27'):verify_adapter(self.root)
    def test_path_traversal_rejected(self):
        for value in ('../outside','/absolute','D:/outside','a\\outside'):
            with self.assertRaises(ValueError):inside(self.root,value)
    def test_native_bf16_t4_forces_false_even_emulation_true(self):
        cuda=SimpleNamespace(get_device_properties=lambda index:SimpleNamespace(major=7),is_bf16_supported=lambda **kwargs:True)
        self.assertFalse(native_bf16(SimpleNamespace(cuda=cuda)))
    def test_native_bf16_excludes_emulation(self):
        flags=[]
        def supported(**kwargs):flags.append(kwargs);return True
        cuda=SimpleNamespace(get_device_properties=lambda index:SimpleNamespace(major=8),is_bf16_supported=supported)
        self.assertTrue(native_bf16(SimpleNamespace(cuda=cuda)));self.assertEqual(flags,[{'including_emulation':False}])
    def checkpoint(self,step,complete=True):
        path=self.root/f'checkpoint-{step}';path.mkdir()
        for name in ('adapter_config.json','adapter_model.safetensors','optimizer.pt','scheduler.pt','rng_state.pth'):(path/name).write_text('fixture')
        if complete:save(path/'trainer_state.json',{'global_step':step})
        return path
    def test_resume_chooses_latest_complete_checkpoint(self):
        good=self.checkpoint(5);self.checkpoint(10,False)
        self.assertEqual(latest_checkpoint(self.root),good)
    def test_fp16_checkpoint_requires_scaler(self):
        path=self.checkpoint(5)
        self.assertFalse(complete_checkpoint(path,require_scaler=True));(path/'scaler.pt').write_text('fixture')
        self.assertTrue(complete_checkpoint(path,require_scaler=True))
    def test_config_rejects_other_student(self):
        cfg=load(Path(__file__).with_name('config.json'));cfg['model_id']='wrong'
        with self.assertRaises(ValueError):check_config(cfg)
    def test_completion_marker_published_after_zip_and_recoverable(self):
        (self.root/'trained_fixture.txt').write_text('CPU test fixture, not real weights')
        report={'bundle_name':'result.zip','outputs_sha256':{'trained_fixture.txt':sha(self.root/'trained_fixture.txt')}}
        with patch('train_sft.export_zip',side_effect=OSError('simulated interrupted packaging')):
            with self.assertRaises(OSError):finalize_artifact(self.root,report)
        self.assertFalse((self.root/'completed.json').exists());self.assertTrue((self.root/'packaging_report.json').exists())
        bundle=finalize_artifact(self.root,load(self.root/'packaging_report.json'))
        self.assertEqual(load(self.root/'completed.json'),report);self.assertEqual(sha(bundle),load(self.root/'RESULT_BUNDLE.json')['sha256'])


class PinnedTokenizerTest(unittest.TestCase):
    def test_runtime_encoding_matches_established_qwen3_preparation(self):
        import sys
        base=Path(__file__).resolve().parents[2]
        sys.path.insert(0,str(base/'data_preparation'))
        from prepare_sft import encode_example
        from transformers import AutoTokenizer
        path=base.parent/'data_preprocessing/training_releases/cpt_27courses_20261023/tokenizer_pinned'
        tokenizer=AutoTokenizer.from_pretrained(str(path),trust_remote_code=False,local_files_only=True)
        row=chat('Nội dung kiểm thử CPU độc lập')
        self.assertEqual(encode_chat(tokenizer,row,'fixture'),encode_example(tokenizer,row,'fixture'))


if __name__=='__main__':unittest.main()
