from __future__ import annotations
import ast
import copy
import json
from pathlib import Path
import sqlite3
import sys
import unittest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'_deps'))
from common import canonical, encode, load, norm, read_rows, sha, verify_files
from prepare_theory import WORK,CPT,OLD
from quality import compact_schema,compact_score,hydrate,legacy_strict_score,mcq_schema
from quality import selection_quality
from build_release import RELEASE,notebook


class QualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.row=read_rows(WORK/'validation.samples.jsonl')[0]
    def sample(self):return copy.deepcopy(self.row),copy.deepcopy(self.row['reference'])
    def score(self,q,row=None):return compact_score(canonical(q).decode(),row or self.row)

    def test_all400_references_pass_source_contract(self):
        n=0
        for split in ('train','validation','test'):
            for s in read_rows(WORK/(split+'.samples.jsonl')):
                self.assertTrue(self.score(s['reference'],s)['usable_proxy'],s['id']);n+=1
        self.assertEqual(n,400)

    def test_malformed_and_scalar_json_never_crash(self):
        for text in ('null','[]','true','0','{"prompt":null}','{"options":[null],"prompt":1}','```json\n{}\n```','{"x":1,"x":2}'):
            with self.subTest(text=text):self.assertFalse(compact_score(text,self.row)['usable_proxy'])
    def test_generation_quality_beats_lower_loss_in_checkpoint_selection(self):
        good={'usable_proxy':True,'reference_answer_preserved':True,'structural_valid':True}
        bad={'usable_proxy':False,'reference_answer_preserved':False,'structural_valid':False}
        self.assertGreater(selection_quality([good,bad,bad,bad],5)['eval_generation_quality'],selection_quality([bad]*4,.01)['eval_generation_quality'])
        self.assertGreater(selection_quality([good]*4,.2)['eval_generation_quality'],selection_quality([good]*4,.8)['eval_generation_quality'])
        with self.assertRaises(ValueError):selection_quality([good],float('nan'))

    def test_boolean_string_rejected(self):
        r,q=self.sample();q['options'][0]['correct']='true';self.assertIn('invalid_option',self.score(q,r)['errors'])
    def test_duplicate_options_rejected(self):
        r,q=self.sample();q['options'][1]['text']=q['options'][0]['text'];self.assertIn('duplicate_options',self.score(q,r)['errors'])
    def test_single_choice_cardinality(self):
        r,q=self.sample();q['type']='SINGLE_CHOICE'
        for o in q['options']:o['correct']=True
        self.assertIn('single_choice_cardinality',self.score(q,r)['errors'])
    def test_unknown_evidence_rejected(self):
        r,q=self.sample();q['evidence_ids']=['E999'];self.assertIn('unknown_evidence_id',self.score(q,r)['errors'])
    def test_valid_but_wrong_source_rejected(self):
        r,q=self.sample();q['evidence_ids']=[next(e['id'] for e in r['evidence'] if e['id'] not in q['evidence_ids'])]
        self.assertIn('answer_evidence_does_not_match_target_source',self.score(q,r)['errors'])
    def test_each_distractor_requires_its_own_source_and_reason(self):
        r,q=self.sample();q['distractor_explanations']=[]
        self.assertIn('each_wrong_option_requires_one_explanation',self.score(q,r)['errors'])
        r,q=self.sample();q['distractor_explanations'][0]['evidence_ids']=q['evidence_ids']
        self.assertIn('wrong_source_for_distractor_explanation',self.score(q,r)['errors'])
    def test_prompt_lost_information_rejected(self):
        r,q=self.sample();q['prompt']='Câu nào đúng?'
        self.assertFalse(self.score(q,r)['usable_proxy'])
    def test_numeric_boundary_not_substring(self):
        r,q=self.sample();r['required_prompt_fragments']=['10'];q['prompt']='100 '+q['prompt']
        self.assertIn('essential_prompt_information_missing',self.score(q,r)['errors'])
    def test_hydration_uses_exact_registered_bytes(self):
        r,q=self.sample();result=hydrate(q,r['evidence'])['questions'][0];ev={e['id']:e for e in r['evidence']}
        self.assertEqual(result['answerCitations'],[{'sourceId':ev[i]['source_id'],'evidenceQuote':ev[i]['text']} for i in q['evidence_ids']])
        self.assertEqual(result['options'],q['options'])
        q['evidence_ids']=['unknown']
        with self.assertRaises(ValueError):hydrate(q,r['evidence'])
    def test_exact_context_id_guard_fixes_legacy_substring_bug(self):
        sys.path.insert(0,str(RELEASE/'training_input/runtime'))
        old=load(HERE.parent/'model_comparisons/four_way_20261025/input/tasks.json')
        identity='q_efd89bb157dfb59c16cf';task=next(t for t in old if t['id']==identity)
        q=copy.deepcopy(task['reference_question'])
        for field in ('questionCitations','answerCitations','explanationCitations'):
            for c in q[field]:c['sourceId']=c['sourceId'].split(':')[0]
        score=legacy_strict_score(json.dumps({'questions':[q]}),task)
        self.assertTrue(score['schema_and_citations_valid']);self.assertFalse(score['structural_valid_v2'])


class DataAndPackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from transformers import AutoTokenizer
        cls.tok=AutoTokenizer.from_pretrained(str(OLD/'tokenizer'),local_files_only=True,trust_remote_code=False)
    def test_all_masks_reencode_and_split_source_ids_hold(self):
        from preflight import check
        report=check(WORK,self.tok)
        self.assertEqual(report['counts'],{'train':270,'validation':30,'test':100})
        self.assertTrue(report['masks_reencoded'])
    def test_no_vlm_and_verbatim_source_spans(self):
        rows={r['id']:r for r in read_rows(CPT/'final_selection.jsonl')}
        for f in read_rows(WORK/'facts.jsonl'):
            r=rows[f['record_id']];begin,end=f['source_span']
            self.assertFalse(r['vlm']);self.assertEqual(r['record']['kind'],'text')
            self.assertEqual(r['text'][begin:end],f['quote'])
    def test_distractor_sources_stay_in_same_course_and_split(self):
        facts={f['id']:f for f in read_rows(WORK/'facts.jsonl')}
        for split in ('train','validation','test'):
            for row in read_rows(WORK/(split+'.samples.jsonl')):
                self.assertTrue(all(facts[i]['course']==row['course'] and facts[i]['split']==split for i in row['context_fact_ids']))
    def test_heldout_documents_not_in_training_sources(self):
        policy=load(WORK/'PREPARATION_REPORT.json')['split_report']
        self.assertEqual(len(policy['heldout_courses']),2)
        for f in read_rows(WORK/'facts.jsonl'):
            if f['course'] in policy['heldout_courses']:self.assertEqual(f['split'],'test')
    def test_train_package_contains_no_test_and_no_test_retrieval_rows(self):
        root=RELEASE/'training_input';verify_files(root);verify_files(root/'data')
        self.assertFalse(any((root/'data').glob('test.*')))
        facts=read_rows(root/'data/facts.jsonl');self.assertTrue(all(f['split']!='test' for f in facts))
        with sqlite3.connect(root/'data/retrieval.sqlite3') as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM facts WHERE split='test'").fetchone()[0],0)
    def test_test_package_binds_training_input_and_exact_counts(self):
        m=verify_files(RELEASE/'test_input')
        self.assertEqual(m['expected_training_input_sha256'],sha(RELEASE/'training_input/manifest.json'))
        self.assertEqual(load(RELEASE/'test_input/data/manifest.json')['counts'],{'test':100})
    def test_rehearsal_and_validation_isolation(self):
        from collections import Counter
        train=read_rows(WORK/'train.samples.jsonl');val=read_rows(WORK/'validation.samples.jsonl')
        self.assertEqual(Counter(s['training_task'] for s in train),{'theory_to_quiz':243,'source_grounded_qa':14,'closed_book_mcq_format':13})
        self.assertTrue(all(s['training_task']=='theory_to_quiz' for s in val))
        chosen=load(RELEASE/'training_input/validation_generation_ids.json')
        self.assertEqual(len(chosen),4);self.assertTrue(set(chosen)<={s['id'] for s in val})
    def test_no_human_or_expert_approval_manufactured(self):
        for split in ('train','validation','test'):
            for r in read_rows(WORK/(split+'.samples.jsonl')):
                self.assertFalse(r['human_verified']);self.assertFalse(r['expert_semantically_verified'])
    def test_training_is_fresh_lora_and_generation_selected(self):
        text=(HERE/'train_v2.py').read_text(encoding='utf-8');tree=ast.parse(text)
        self.assertNotIn('PeftModel.from_pretrained',text);self.assertNotIn('data/test',text)
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
        args=next(n for n in calls if n.func.id=='TrainingArguments')
        kv={k.arg:k.value for k in args.keywords}
        self.assertEqual(ast.literal_eval(kv['metric_for_best_model']),'eval_generation_quality')
        self.assertTrue(any(n.func.id=='get_peft_model' for n in calls))
    def test_notebook_cells_and_child_code_parse(self):
        for kind in ('diagnostics','train','test'):
            _,nb=notebook(kind,'test.zip','0'*64)
            for c in nb['cells']:
                if c['cell_type']!='code':continue
                tree=ast.parse(''.join(c['source']))
                for node in ast.walk(tree):
                    if isinstance(node,ast.Constant) and isinstance(node.value,str) and node.value.startswith('import torch;'):ast.parse(node.value)
    def test_rag_never_retrieves_test_default(self):
        from retrieval import retrieve
        result=retrieve(RELEASE/'training_input/data/retrieval.sqlite3','bộ nhớ')
        self.assertTrue(result);self.assertTrue(all(f['split']=='train' for f in result))
    def test_rag_can_plan_with_registered_sources(self):
        sys.path.insert(0,str(RELEASE/'training_input/runtime'))
        from rag_quiz import plan
        s=plan(RELEASE/'training_input','tiến trình','IT3070')
        self.assertEqual(len(s['evidence']),4);self.assertTrue(all('source_id' in e for e in s['evidence']))
    def test_cluster_interval_respects_shared_source_families(self):
        from evaluate_v2 import cluster_interval
        rows=[{'split_group':'a','mcq':{'score':{'source_key_match':True}}} for _ in range(10)]
        rows +=[{'split_group':'b','mcq':{'score':{'source_key_match':False}}} for _ in range(10)]
        self.assertEqual(cluster_interval(rows),[0,1])


class RealTokenizerGrammarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from transformers import AutoTokenizer
        from constrained import tokenizer_data
        cls.tok=AutoTokenizer.from_pretrained(str(OLD/'tokenizer'),local_files_only=True,trust_remote_code=False)
        cls.data=tokenizer_data(cls.tok)
    def assert_allowed(self,text,schema):
        from collections import deque
        from constrained import Prefix
        p=Prefix(self.data,schema);sent=[151644,872,198];queue=deque(self.tok(text,add_special_tokens=False)['input_ids']);steps=0
        while queue:
            identity=queue.popleft();steps+=1
            self.assertLess(steps,6000)
            allowed=p.enforcer.get_allowed_tokens(sent).allowed_tokens
            if identity not in allowed:
                # LMFE's freetext shortcut excludes some compound tokens that cross
                # string/key boundaries. The same JSON must remain reachable via
                # smaller tokens; do not weaken semantic or decoded-text checks.
                piece=self.tok.decode(sent[3:]+[identity])[len(self.tok.decode(sent[3:])):]
                split=[i for ch in piece for i in self.tok(ch,add_special_tokens=False)['input_ids']]
                self.assertTrue(split and split!=[identity],f'No legal decomposition: {identity} {piece!r}')
                queue.extendleft(reversed(split));continue
            sent.append(identity)
        self.assertEqual(self.tok.decode(sent[3:]),text)
        self.assertIn(self.tok.eos_token_id,p.enforcer.get_allowed_tokens(sent).allowed_tokens)
    def test_real_qwen_mcq_path_allows_valid_json_and_eos(self):self.assert_allowed('{"correct_labels":["A"]}',mcq_schema(list('ABCD')))
    def test_real_qwen_multiselect(self):self.assert_allowed('{"correct_labels":["A","C"]}',mcq_schema(list('ABCD'),True))
    def test_real_vietnamese_compact_output_path(self):
        row=read_rows(WORK/'validation.samples.jsonl')[0]
        self.assert_allowed(canonical(row['reference']).decode(),compact_schema([e['id'] for e in row['evidence']]))
    def test_schema_disallows_prompt_echo_after_json(self):
        from constrained import Prefix
        p=Prefix(self.data,mcq_schema(list('ABCD')));sent=[151644,872,198]
        for identity in self.tok('{"correct_labels":["A"]}',add_special_tokens=False)['input_ids']:
            p.enforcer.get_allowed_tokens(sent);sent.append(identity)
        allowed=p.enforcer.get_allowed_tokens(sent).allowed_tokens
        echoed=self.tok('dùng nhãn',add_special_tokens=False)['input_ids'][0]
        self.assertNotIn(echoed,allowed)


if __name__=='__main__':unittest.main()
