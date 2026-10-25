import copy
import json
import unittest
from build_suite import CASES,independent_gold
from evaluate import objective,parse,question_schema


class EvaluationTests(unittest.TestCase):
    def good_question(self):
        return {'slot_id':'linear_absent','difficulty':'MEDIUM','question':'Tìm 3 trong mảng [2,4,6,8,10,12,14,16] bằng tìm kiếm tuyến tính cần xét bao nhiêu phần tử?',
                'options':[{'id':i,'text':str(v)} for i,v in zip('ABCD',[7,8,4,0])],
                'answer':'B','explanation':'Không có 3, phải xét đủ 8 phần tử.',
                'source_id':'S01','evidence_quote':'Mảng A=[2,4,6,8,10,12,14,16], cần tìm x=3.'}

    def test_independent_reference_answers(self):
        self.assertEqual(independent_gold()['facts'],{'linear_absent':8,'binary_iterations':5,'recursive_sum':15,
            'triangular_loop':10,'shortest_path':4,'mst_weight':6,'knapsack_value':7,'lcs_length':4,
            'integer_width':64,'negative_edges':'Bellman-Ford','table_case2':41,'unsupported_runtime':None})

    def test_markdown_recovery_does_not_pass_json_metric(self):
        value,strict,mode=parse('```json\n{"questions":[],"rejected":[]}\n```')
        self.assertEqual(value['questions'],[]);self.assertFalse(strict);self.assertEqual(mode,'recovered_object')

    def test_duplicate_options_fail_schema(self):
        q=self.good_question();self.assertEqual(question_schema(q,CASES[0]),[])
        q['options'][3]['text']='8'
        self.assertIn('duplicate_option_text',question_schema(q,CASES[0]))

    def test_quote_exactness_is_not_factual_correctness(self):
        q=self.good_question();q['evidence_quote']='Tìm tuyến tính xét 8 phần tử.'
        record={'content':json.dumps({'questions':[q],'rejected':[]})}
        result=objective(record,CASES[0])
        self.assertTrue(result['strict_json']);self.assertEqual(result['exact_evidence_count'],0)
        self.assertFalse(result['count_and_slots_ok']) # missing second required slot

    def test_runtime_refusal_fails_if_also_hallucinated(self):
        record={'content':json.dumps({'questions':[], 'rejected':[{'slot_id':'unsupported_runtime','reason':'INSUFFICIENT_CONTEXT'}]})}
        self.assertTrue(objective(record,CASES[5])['rejection_ok'])
        q=self.good_question();q['slot_id']='unsupported_runtime'
        data=json.loads(record['content']);data['questions']=[q];record['content']=json.dumps(data)
        self.assertFalse(objective(record,CASES[5])['rejection_ok'])

    def test_missing_response_is_not_treated_as_valid_empty_quiz(self):
        result=objective({'status':'error','content':''},CASES[0])
        self.assertFalse(result['strict_json']);self.assertFalse(result['strict_schema']);self.assertEqual(result['question_count'],0)

    def test_malformed_list_fields_are_errors_not_a_grader_crash(self):
        q=self.good_question();q['difficulty']=['MEDIUM'];q['slot_id']=['linear_absent']
        r=objective({'content':json.dumps({'questions':[q],'rejected':[{'slot_id':[],'reason':'bad'}]})},CASES[0])
        self.assertFalse(r['strict_schema']);self.assertFalse(r['count_and_slots_ok'])

    def test_different_string_options_are_invalid_schema_but_not_duplicates(self):
        q=self.good_question();q['options']=['1','2','3','4']
        errors=question_schema(q,CASES[0])
        self.assertIn('option_schema',errors);self.assertNotIn('duplicate_option_text',errors)

    def test_nonstandard_nan_is_not_strict_json(self):
        value,strict,mode=parse('{"questions": [], "rejected": [], "extra": NaN}')
        self.assertFalse(strict)


if __name__=='__main__':unittest.main()
