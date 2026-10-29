from __future__ import annotations

import copy
import unittest

from build_release import assign_question_families, canonical, correct_signature
from extract_questions import add_marks, finish, page_lines, parse_moodle


def line(text,y,x=49,size=10):
    return {"text":text,"bbox":[x,y,x+len(text)*4,y+11],"spans":[{"text":text,"font":"Arial","size":size}],"page":1}


def document(lines):
    return {"source_id":"source_test","sha256":"0"*64,"path":"fixture.pdf","relative_path":"fixture.pdf","course":"test",
            "pages":[{"page":1,"height":800,"width":600,"lines":lines,"images":[]}]}


def question(identity,prompt,course="test"):
    return {"id":identity,"prompt":prompt,"course":course,"options":[{"text":"correct","correct":True},{"text":"wrong","correct":False}]}


class ExtractionRegressionTests(unittest.TestCase):
    def test_full_width_moodle_stem_left_of_question_number_is_retained(self):
        d=document([line("Question 1",100,42),line("Correct",120,42),line("Mark 1.00 out of 1.00",140,42),
                    line("Which package is the lowest unit of work?",170),line("Select one:",190),
                    line("a.",210,65),line("Work package",210,80),line("b.",230,65),line("Work",230,80),
                    line("The correct answer is: Work package",260),line("Jump to...",300)])
        rows=parse_moodle(d)
        self.assertEqual(rows[0]["status"],"candidate")
        self.assertEqual(rows[0]["prompt"],"Which package is the lowest unit of work?")
        self.assertEqual([o["correct"] for o in rows[0]["options"]],[True,False])
        self.assertEqual(rows[0]["answer_evidence"],"Work package")

    def test_substring_answer_does_not_mark_shorter_option_correct(self):
        d=document([line("Question 1",100),line("Which development model is appropriate?",120),line("Select one:",140),
                    line("a. Easy testing and fast delivery",160),line("b. Easy testing",180),
                    line("The correct answer is: Easy testing and fast delivery",210)])
        row=parse_moodle(d)[0]
        self.assertEqual(row["status"],"candidate")
        self.assertEqual([o["correct"] for o in row["options"]],[True,False])

    def test_true_false_key_without_colon(self):
        d=document([line("Question 1",100),line("Every program has exactly one thread.",120),line("Select one:",140),
                    line("True",160),line("False",180),line("The correct answer is 'False'.",210)])
        row=parse_moodle(d)[0]
        self.assertEqual(row["status"],"candidate")
        self.assertEqual([o["correct"] for o in row["options"]],[False,True])

    def test_radio_on_second_wrapped_line_marks_paragraph_start(self):
        lines=[line("First long choice starts here",100,89),line("and wraps onto this line",118,89),
               line("Second choice",155,89)]
        add_marks(lines,[{"bbox":[67,109,82,124],"selected":True,"fill":[.7,.7,.7]}],False)
        self.assertIn("radio",lines[0]);self.assertNotIn("radio",lines[1])

    def test_corrected_chapter_number_removed_but_small_numeric_option_preserved(self):
        page={"page":1,"width":800,"height":600,"lines":[line("2",80,size=14),line("2",100,size=9)]}
        self.assertEqual([l["bbox"][1] for l in page_lines(page,original=True)],[100])

    def test_missing_vector_figure_and_glyph_corruption_are_quarantined(self):
        for prompt,reason in [("Cho biết ký hiệu trong hình thể hiện điều gì?","visual_reference_requires_review"),
                              ("Một câu hỏi có aaaaaaaa trong nội dung","repeated_character_corruption")]:
            row=question("id",prompt);row.update(regions=[],parser="fixture")
            checked=finish(row,[],document([]))
            self.assertEqual(checked["status"],"quarantine");self.assertIn(reason,checked["reasons"])

    def test_option_order_is_ignored_but_conflicting_key_is_detectable(self):
        left=question("one","A complete question?")
        right=copy.deepcopy(left);right["options"].reverse()
        self.assertEqual(canonical(left),canonical(right))
        right["options"][0]["correct"]=True;right["options"][1]["correct"]=False
        self.assertNotEqual(correct_signature(left),correct_signature(right))

    def test_numeric_question_variants_never_split_across_holdouts(self):
        rows=[question("q"+str(i),f"A processor has {i} independent registers. Which answer is valid?") for i in range(8)]
        rows += [question("u"+str(i),f"Unique concept {chr(65+i)} with independent semantics and several words?") for i in range(12)]
        report=assign_question_families(rows)
        self.assertEqual(len({r["split_group"] for r in rows[:8]}),1)
        self.assertEqual(len({r["split"] for r in rows[:8]}),1)
        self.assertEqual(report["split_policy"],"question_family")


if __name__=="__main__":unittest.main()
