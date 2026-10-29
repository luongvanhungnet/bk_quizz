"""Selection and immutable-source regressions; all mutations use temp fixtures."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import build_completed_release as builder

SFT=Path(__file__).resolve().parents[2]
TOKENIZER=SFT.parent/"data_preprocessing/training_releases/cpt_27courses_20261023/tokenizer_pinned"


def write_rows(path,rows):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in rows),encoding='utf-8')


def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


@unittest.skipUnless(TOKENIZER.is_dir(),"Pinned local Qwen3 tokenizer unavailable")
class CompletedReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from transformers import AutoTokenizer
        cls.tokenizer=AutoTokenizer.from_pretrained(str(TOKENIZER),local_files_only=True)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source=self.root/'source';self.review=self.root/'review';self.out=self.root/'out'
        self.chats={};self.metas={};self.tokens={};self.originals=[];self.pdf=self.root/'native_fixture.pdf';self.pdf.write_bytes(b'CPU fixture only; not a production PDF')
        for split in builder.SPLITS:
            identity='q_fixture_'+split;source_id='exam_fixture_'+split;context_id=source_id+':'+identity
            prompt='Which source fact is printed for '+split+'?';fact='TCP is connection-oriented.'
            citations=[{'sourceId':context_id,'evidenceQuote':fact}]
            output={'questions':[{'type':'SINGLE_CHOICE','prompt':prompt,'explanation':'Theo tài liệu: '+fact,
                                 'options':[{'text':fact,'correct':True},{'text':'TCP never establishes a connection.','correct':False}],
                                 'acceptedAnswers':[],'questionCitations':citations,'answerCitations':citations,'explanationCitations':citations}]}
            chat={'messages':[{'role':'system','content':'Create one quiz from the provided source.'},
                              {'role':'user','content':'['+context_id+']\n'+prompt+'\n'+fact},
                              {'role':'assistant','content':json.dumps(output,ensure_ascii=False,separators=(',',':'))}]}
            origin={'id':identity,'source_id':source_id,'path':str(self.pdf),'sha256':builder.file_sha(self.pdf),'pages':[1]}
            metadata={'id':identity,'split':split,'split_group':'family_'+identity,'content_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                      'parser':'native_answer_letter','course':'ISOLATED_FIXTURE','sources':[copy.deepcopy(origin)],
                      'human_verified':False,'expert_semantically_verified':False,'rationale_origin':'source_answer_attribution',
                      'chat_sha256':hashlib.sha256(json.dumps(chat,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()}
            self.chats[split]=[chat];self.metas[split]=[metadata];self.tokens[split]=[builder.encode_example(self.tokenizer,chat,identity)]
            self.originals.append({'id':identity,'origins':[copy.deepcopy(origin)]})
        self.adapter=self.root/'cpt_adapter';self.adapter.mkdir()
        (self.adapter/'adapter_config.json').write_text('{}',encoding='utf-8');(self.adapter/'adapter_model.safetensors').write_bytes(b'not model weights: isolated hash fixture')
        self.provenance={'base_model':'Qwen/Qwen3-1.7B','base_revision':'70d244cc86ccca08cf5af4e1e306ecf908b1ad5e',
                         'current_cpt_adapter_path':str(self.adapter),'current_cpt_adapter_sha256':{n:builder.file_sha(self.adapter/n) for n in ('adapter_config.json','adapter_model.safetensors')}}
        self.token_report={'tokenizer':str(TOKENIZER),'tokenizer_sha256':{n:builder.file_sha(TOKENIZER/n) for n in builder.TOKENIZER_FILES if (TOKENIZER/n).is_file()},'outputs_sha256':{}}
        self.review_pages=[{'id':'rp_pending_fixture','identity':'a'*64,'source_id':'exam_pending','source_sha256':'b'*64,'page':9}]
        self.sync()

    def tearDown(self):self.temp.cleanup()

    def sync(self):
        self.source.mkdir(exist_ok=True)
        for split in builder.SPLITS:
            write_rows(self.source/(split+'.messages.jsonl'),self.chats[split]);write_rows(self.source/(split+'.metadata.jsonl'),self.metas[split])
            write_rows(self.source/'tokenized'/(split+'.jsonl'),self.tokens[split])
            self.token_report['outputs_sha256']['tokenized/'+split+'.jsonl']=builder.file_sha(self.source/'tokenized'/(split+'.jsonl'))
        write_rows(self.source/'questions_selected.jsonl',self.originals);write_json(self.source/'MODEL_PROVENANCE.json',self.provenance)
        write_json(self.source/'tokenization_report.json',self.token_report)
        names=[s+suffix for s in builder.SPLITS for suffix in ('.messages.jsonl','.metadata.jsonl')]+['questions_selected.jsonl','MODEL_PROVENANCE.json','tokenization_report.json']
        write_json(self.source/'release_manifest.json',{'files_sha256':{n:builder.file_sha(self.source/n) for n in names}})
        write_rows(self.review/'pages.jsonl',self.review_pages)
        write_json(self.review/'manifest.json',{'catalog_sha256':builder.file_sha(self.review/'pages.jsonl')})

    def select(self):return builder.select_records(self.source,self.review)

    def test_preserves_original_split_messages_tokens_and_verification_flags(self):
        selected,excluded,*_=self.select();self.assertFalse(excluded)
        for split,records in selected.items():
            self.assertEqual(len(records),1);chat,meta,tokens,_=records[0]
            self.assertEqual(chat,self.chats[split][0]);self.assertEqual(tokens,self.tokens[split][0])
            self.assertEqual(meta['split'],split);self.assertFalse(meta['human_verified']);self.assertFalse(meta['expert_semantically_verified'])
            self.assertFalse(meta['requires_additional_llm']);self.assertFalse(meta['requires_vlm']);self.assertFalse(meta['requires_manual_completion'])

    def test_secondary_origin_excludes_question_even_when_primary_is_complete(self):
        extra={'source_id':'exam_pending','pages':[9],'path':str(self.pdf),'sha256':builder.file_sha(self.pdf)}
        self.metas['train'][0]['sources'].append(extra);self.originals[0]['origins'].append(extra);self.sync()
        selected,excluded,*_=self.select();self.assertEqual(selected['train'],[])
        self.assertEqual(excluded[0]['dependencies'],[{'source_id':'exam_pending','page':9}])

    def test_later_page_in_same_origin_also_excludes(self):
        self.review_pages[0]['source_id']='exam_fixture_train';self.metas['train'][0]['sources'][0]['pages']=[1,9]
        self.originals[0]['origins'][0]['pages']=[1,9];self.sync()
        selected,excluded,*_=self.select();self.assertFalse(selected['train']);self.assertEqual(len(excluded),1)

    def test_page_provenance_disagreement_fails_closed(self):
        self.metas['train'][0]['sources'][0]['pages']=[7];self.sync()
        with self.assertRaisesRegex(ValueError,'source pages disagree'):self.select()

    def test_unknown_pending_or_teacher_id_cannot_be_added(self):
        self.metas['train'][0]['id']='teacher_pending';self.tokens['train'][0]['id']='teacher_pending';self.sync()
        with self.assertRaisesRegex(ValueError,'unknown native'):self.select()

    def test_vlm_parser_cannot_be_relabelled_completed(self):
        self.metas['train'][0]['parser']='qwen_vlm';self.sync()
        with self.assertRaisesRegex(ValueError,'nonnative'):self.select()

    def test_duplicate_identity_across_splits_fails_closed(self):
        identity=self.metas['train'][0]['id'];self.metas['validation'][0]['id']=identity;self.tokens['validation'][0]['id']=identity;self.sync()
        with self.assertRaisesRegex(ValueError,'Duplicate'):self.select()

    def test_family_cannot_cross_split(self):
        self.metas['validation'][0]['split_group']=self.metas['train'][0]['split_group'];self.sync()
        with self.assertRaisesRegex(ValueError,'family crosses split'):self.select()

    def test_split_cannot_be_reassigned(self):
        self.metas['validation'][0]['split']='train';self.sync()
        with self.assertRaisesRegex(ValueError,'Incomplete or nonnative'):self.select()

    def test_frozen_messages_hash_tamper_rejected(self):
        with (self.source/'train.messages.jsonl').open('ab') as f:f.write(b'\n')
        with self.assertRaisesRegex(ValueError,'Frozen release changed'):self.select()

    def test_frozen_token_file_hash_tamper_rejected(self):
        with (self.source/'tokenized/train.jsonl').open('ab') as f:f.write(b'\n')
        with self.assertRaisesRegex(ValueError,'Frozen token data changed'):self.select()

    def test_review_catalog_hash_tamper_rejected(self):
        with (self.review/'pages.jsonl').open('ab') as f:f.write(b'\n')
        with self.assertRaisesRegex(ValueError,'Review page catalog changed'):self.select()

    def test_misaligned_token_identity_rejected(self):
        self.tokens['train'][0]['id']='other_id';self.sync()
        with self.assertRaisesRegex(ValueError,'unknown native'):self.select()

    def test_prompt_loss_mask_change_rejected_even_with_updated_file_hashes(self):
        self.tokens['train'][0]['labels'][0]=self.tokens['train'][0]['input_ids'][0];self.sync()
        with self.assertRaisesRegex(ValueError,'Assistant-only token mask differs'):builder.build_data(self.source,self.review,self.out)

    def test_pinned_tokenizer_hash_mismatch_rejected(self):
        fake=self.root/'wrong_tokenizer';fake.mkdir();(fake/'tokenizer_config.json').write_text('{}',encoding='utf-8')
        self.token_report['tokenizer']=str(fake);self.token_report['tokenizer_sha256']={'tokenizer_config.json':'a'*64};self.sync()
        with self.assertRaisesRegex(ValueError,'Pinned tokenizer changed'):builder.build_data(self.source,self.review,self.out)

    def test_wrong_cpt_adapter_hash_rejected(self):
        (self.adapter/'adapter_model.safetensors').write_bytes(b'tampered fixture weights')
        with self.assertRaisesRegex(ValueError,'Wrong CPT27 adapter'):builder.build_data(self.source,self.review,self.out)

    def test_changed_native_pdf_rejected(self):
        self.pdf.write_bytes(b'tampered original source')
        with self.assertRaisesRegex(ValueError,'Native PDF changed'):builder.build_data(self.source,self.review,self.out)

    def test_overlong_chat_is_rejected_without_truncation(self):
        self.chats['train'][0]['messages'][1]['content']+=' sourceword'*5000
        self.metas['train'][0]['chat_sha256']=hashlib.sha256(json.dumps(self.chats['train'][0],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        self.tokens['train'][0]=builder.encode_example(self.tokenizer,self.chats['train'][0],self.metas['train'][0]['id']);self.sync()
        with self.assertRaisesRegex(ValueError,'Overlong example'):builder.build_data(self.source,self.review,self.out)

    def test_frozen_output_cannot_be_built_over(self):
        write_json(self.out/'payload/manifest.json',{'schema':builder.SCHEMA})
        with self.assertRaisesRegex(ValueError,'already frozen'):builder.build_data(self.source,self.review,self.out)

    def test_fixture_build_preserves_all_masks_and_excludes_pending_page(self):
        report=builder.build_data(self.source,self.review,self.out)
        self.assertEqual(report['total'],3);self.assertEqual(report['counts'],{'train':1,'validation':1,'test':1})
        for split in builder.SPLITS:
            rows=list(builder.read_jsonl(self.out/'payload/tokenized'/(split+'.jsonl')))
            self.assertEqual(rows,self.tokens[split])
        self.assertEqual(report['human_reviews_created'],0);self.assertFalse(report['model_weights_loaded_or_training_executed_locally'])


class BundlePathTests(unittest.TestCase):
    def test_bundle_members_relative_and_bound_by_manifest_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);out=root/'release';payload=out/'payload';tools=root/'fake_tools'
            write_json(payload/'build_report.json',{'counts':{'train':1,'validation':1,'test':1}})
            write_json(payload/'selection_policy.json',{'all_origin_pages_must_be_complete':True})
            for name in ('train_sft.py','sft_contract.py','config.json','requirements.txt'):
                path=tools/'runtime'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('isolated fixture',encoding='utf-8')
            with patch.object(builder,'__file__',str(tools/'build_completed_release.py')):receipt=builder.freeze_bundle(out)
            self.assertEqual(builder.file_sha(receipt['archive']),receipt['sha256'])
            with zipfile.ZipFile(receipt['archive']) as archive:
                manifest=json.loads(archive.read('manifest.json'));names=archive.namelist()
                self.assertEqual(set(names),set(manifest['files_sha256'])|{'manifest.json'})
                self.assertTrue(all(not Path(n).is_absolute() and '\\' not in n and '..' not in Path(n).parts for n in names))
                for name,wanted in manifest['files_sha256'].items():self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),wanted)


if __name__=='__main__':unittest.main()
