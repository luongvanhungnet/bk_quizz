import ast
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

from build_comparison import OUTPUT, RELEASE, make_notebook, sha

RUNTIME = OUTPUT/"input/runtime"
sys.path.insert(0, str(RUNTIME))
from scoring import score_mcq, score_quiz, strict_json, wilson
from evaluate_four_way import adapter_for, report
from sft_contract import save, digest


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.task = json.loads((OUTPUT/"input/tasks.json").read_text(encoding="utf-8"))[0]
        self.context = self.task["grounded_messages"][-1]["content"]
        self.reference = self.task["reference_question"]

    def test_source_target_passes(self):
        score = score_quiz(json.dumps({"questions": [self.reference]}), self.reference, self.context)
        self.assertTrue(score["schema_and_citations_valid"])
        self.assertTrue(score["source_answer_exact_match"])

    def test_malformed_mcq_counted_wrong(self):
        for text in ('```json\n{"correct_labels":["A"]}\n```', '{"correct_labels":["A","A"]}',
                     '{"correct_labels":["Z"]}', '{"correct_labels":"A"}', '{"correct_labels":[]}',
                     '{"correct_labels":["A"],"extra":true}', 'null'):
            with self.subTest(text=text):
                self.assertFalse(score_mcq(text, ["A"], ["A", "B"])["source_key_exact_match"])

    def test_multiselect_exact_set(self):
        self.assertTrue(score_mcq('{"correct_labels":["C","A"]}', ["A", "C"], ["A", "B", "C"])["source_key_exact_match"])
        self.assertFalse(score_mcq('{"correct_labels":["A"]}', ["A", "C"], ["A", "B", "C"])["source_key_exact_match"])

    def test_no_duplicate_keys_or_nonfinite_json(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}'):
            with self.assertRaises(ValueError):
                strict_json(text)

    def test_empty_quiz_and_fabricated_citation_fail(self):
        for text in ('{"questions":[]}', '{"questions":null}', '{"questions":3}', '{"questions":"bad"}', 'null', '[]'):
            self.assertFalse(score_quiz(text, self.reference, self.context)["schema_and_citations_valid"])
        q = json.loads(json.dumps(self.reference))
        q["answerCitations"][0]["evidenceQuote"] = "fabricated unsupported claim"
        self.assertFalse(score_quiz(json.dumps({"questions": [q]}), self.reference, self.context)["schema_and_citations_valid"])

    def test_paraphrase_is_unassessable_not_automatic_wrong(self):
        q = dict(self.reference, prompt=self.reference["prompt"]+" (diễn đạt lại)")
        score = score_quiz(json.dumps({"questions": [q]}), self.reference, self.context)
        self.assertTrue(score["schema_and_citations_valid"])
        self.assertFalse(score["reference_alignment_assessable"])
        self.assertIsNone(score["source_answer_exact_match"])

    def test_wrong_answer_flags_detected_with_aligned_texts(self):
        q = json.loads(json.dumps(self.reference))
        for o in q["options"]:
            o["correct"] = False
        old_gold = next(i for i, o in enumerate(self.reference["options"]) if o["correct"])
        q["options"][(old_gold+1) % len(q["options"])]["correct"] = True
        if q["type"] == "SINGLE_CHOICE":
            score = score_quiz(json.dumps({"questions": [q]}), self.reference, self.context)
            self.assertTrue(score["reference_alignment_assessable"])
            self.assertFalse(score["source_answer_exact_match"])

    def test_small_sample_uncertainty_not_zero(self):
        low, high = wilson(40, 40)
        self.assertLess(low, .95)
        self.assertAlmostEqual(high, 1)


class ProtocolTests(unittest.TestCase):
    def test_full_report_and_result_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)/"evaluation"
            tasks = json.loads((OUTPUT/"input/tasks.json").read_text(encoding="utf-8"))
            for variant in ("base", "cpt", "sft", "cpt_sft"):
                folder = out/variant
                ident = {k: "same" for k in ("input_manifest_sha256", "model", "revision", "packages", "dtype", "gpu", "protocol", "generation_count")}
                save(folder/"identity.json", ident)
                summary = {"assistant_mean_example_nll": 1.0, "assistant_mean_example_ppl": 2.718,
                           "source_key_matches": 20, "n_test": 40, "grounded_valid": 12,
                           "n_grounded": 12, "generation_tokens_per_second": 10}
                save(folder/"summary.json", summary)
                for index, task in enumerate(tasks):
                    row = {"id": task["id"], "closed_book": {"score": {"source_key_exact_match": index < 20}}}
                    if index < 12:
                        row["grounded_quiz"] = {"text": '{"fixture":true}'}
                    save(folder/"samples"/(task["id"]+".json"), {"record": row})
                files = [p for p in folder.rglob("*") if p.is_file()]
                save(folder/"completed.json", {"identity_sha256": digest(ident), "outputs_sha256": {p.relative_to(folder).as_posix(): sha(p) for p in files}})
            sft = Path(directory)/"sft_only_training"
            save(sft/"adapter/adapter_config.json", {"fixture": True})
            (sft/"adapter/adapter_model.safetensors").write_bytes(b"fixture, not actual model weights")
            with contextlib.redirect_stdout(io.StringIO()):
                report(SimpleNamespace(root=OUTPUT/"input", output=out, sft_run=sft))
            result = json.loads((out/"comparison.json").read_text(encoding="utf-8"))
            self.assertEqual(len(result["summaries"]), 4)
            self.assertEqual(len(result["paired_source_key_outcomes"]), 6)
            self.assertEqual(len(json.loads((out/"blind_review.json").read_text(encoding="utf-8"))), 12)
            import zipfile
            with zipfile.ZipFile(out/"four_way_results.zip") as z:
                self.assertIn("sft_only_training/adapter/adapter_model.safetensors", z.namelist())
                self.assertIn("COMPARISON.md", z.namelist())

    def test_sft_only_has_no_cpt_loader(self):
        source = (RUNTIME/"train_sft.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        self.assertNotIn("PeftModel", source)
        self.assertNotIn("load_file(", source)
        cfg = next(n for n in calls if isinstance(n.func, ast.Name) and n.func.id == "LoraConfig")
        kwargs = {k.arg: ast.literal_eval(k.value) for k in cfg.keywords}
        self.assertEqual((kwargs["r"], kwargs["lora_alpha"], kwargs["lora_dropout"]), (8, 16, .05))
        self.assertTrue(kwargs["init_lora_weights"])

    def test_training_schedule_is_identical(self):
        def settings(path):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            return next(ast.dump(n) for n in ast.walk(tree) if isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Name) and n.func.id == "TrainingArguments")
        self.assertEqual(settings(RELEASE/"runtime/train_sft.py"), settings(RUNTIME/"train_sft.py"))
        self.assertEqual(sha(RELEASE/"runtime/config.json"), sha(RUNTIME/"config.json"))

    def test_closed_book_prompt_contains_only_original_question_and_options(self):
        originals = {q["id"]: q for q in map(json.loads, (RELEASE/"source_questions.jsonl").read_text(encoding="utf-8").splitlines())}
        tasks = json.loads((OUTPUT/"input/tasks.json").read_text(encoding="utf-8"))
        for t in tasks:
            q = originals[t["id"]]
            expected = "Học phần: " + t["course"] + "\n" + q["prompt"] + "\n" + "\n".join(
                chr(65+i)+". "+o["text"] for i, o in enumerate(q["options"]))
            self.assertEqual(t["closed_book_messages"][-1]["content"], expected)
            self.assertEqual(len(t["closed_book_messages"]), 2)
            self.assertEqual(t["gold_labels"], [chr(65+i) for i, o in enumerate(q["options"]) if o["correct"]])

    def test_notebook_all_code_compiles(self):
        for cell in make_notebook("0"*64)["cells"]:
            if cell["cell_type"] == "code":
                ast.parse("".join(cell["source"]))

    def test_sft_identity_rejects_combined_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            save(run/"completed.json", {"status": "completed", "mode": "train"})
            save(run/"MODEL_PROVENANCE.json", {"variant": "cpt_sft", "cpt_weights_loaded": True})
            with self.assertRaises(ValueError):
                adapter_for(OUTPUT/"input", "sft", run)

    def test_report_refuses_mixed_environments(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            tasks = json.loads((OUTPUT/"input/tasks.json").read_text(encoding="utf-8"))
            for variant in ("base", "cpt", "sft", "cpt_sft"):
                folder = out/variant
                ident = {"packages": {"torch": "wrong" if variant == "sft" else "same"}}
                save(folder/"identity.json", ident)
                save(folder/"summary.json", {})
                for task in tasks:
                    save(folder/"samples"/(task["id"]+".json"), {"record": {"id": task["id"]}})
                files = [p for p in folder.rglob("*") if p.is_file()]
                save(folder/"completed.json", {"identity_sha256": digest(ident), "outputs_sha256": {p.relative_to(folder).as_posix(): sha(p) for p in files}})
            # Fill common fields, but retain package mismatch.
            for variant in ("base", "cpt", "sft", "cpt_sft"):
                folder = out/variant
                ident = json.loads((folder/"identity.json").read_text())
                ident.update({k: None for k in ("input_manifest_sha256", "model", "revision", "dtype", "gpu", "protocol", "generation_count")})
                save(folder/"identity.json", ident)
                done = json.loads((folder/"completed.json").read_text())
                done["identity_sha256"] = digest(ident)
                done["outputs_sha256"]["identity.json"] = sha(folder/"identity.json")
                save(folder/"completed.json", done)
            with self.assertRaisesRegex(ValueError, "same protocol/environment"):
                report(SimpleNamespace(root=OUTPUT/"input", output=out, sft_run=None))


if __name__ == "__main__":
    unittest.main()
