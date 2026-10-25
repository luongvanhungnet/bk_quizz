"""OCR evidence tests: confidence is observational; visible ink must not vanish."""
import unittest
from pathlib import Path
import tempfile
import json
from unittest.mock import patch
import numpy as np
from ocr_probe import DEFAULT_TESSERACT,WIRE_PREFIX,atomic_json,frame_payload,ocr_ink_metrics,parse_tsv,read_jsonl,run,summarize_journal,tesseract_tsv,worker


class OCRProbeTests(unittest.TestCase):
    def test_native_stdout_noise_cannot_be_parsed_as_worker_result(self):
        self.assertIsNone(frame_payload("MuPDF warning: font issue\n"))
        value=frame_payload("native diagnostic without newline"+WIRE_PREFIX+'{"status":"ok"}\n')
        self.assertEqual(json.loads(value),{"status":"ok"})

    def test_resumable_cache_retries_errors_and_preserves_full_metrics(self):
        calls=[]
        class FakePool:
            def __init__(self,*args):pass
            def close(self):pass
            def probe(self,page,config):
                calls.append(page["id"])
                if calls.count(page["id"])==1 and page["id"]=="p0":return {"status":"error","error":"transient engine failure"}
                return {"status":"ok","ocr":{"words":[{"text":"Câu","bbox":[1,1,2,2],"confidence":90}],"text":"Câu"}}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);workspace=root/"workspace";out=root/"out";models=root/"models"
            workspace.mkdir();models.mkdir()
            for lang in ["eng","vie"]:(models/(lang+".traineddata")).write_bytes(b"test model hash only")
            pages=[{"id":"p"+str(i),"identity":"i"+str(i),"source_id":"s","source_sha256":"a"*64,"page":i+1,"bbox":[0,0,100,100],"native_text_preview":""} for i in range(2)]
            (workspace/"pages.jsonl").write_text("".join(json.dumps(p)+"\n" for p in pages),encoding="utf-8")
            with patch("ocr_probe.StreamPool",FakePool):
                first=run(workspace,out,models,workers=1)
                second=run(workspace,out,models,workers=1)
            self.assertEqual(first["counts"],{"error":1,"ok":1})
            self.assertEqual(second["counts"],{"ok":2})
            self.assertEqual(calls.count("p0"),2)
            self.assertEqual(calls.count("p1"),1)
            full=read_jsonl(out/"ocr_metrics.jsonl")
            self.assertTrue(all(row["ocr"]["words"][0]["text"]=="Câu" for row in full))
            self.assertEqual(len(list((out/"ocr_versions"/"p0").glob("*.json"))),2)
            summary=summarize_journal(out)
            self.assertEqual(summary["status_counts"],{"ok":2})
            self.assertFalse(summary["error_types"])

    def test_atomic_write_retries_transient_windows_sharing(self):
        original=Path.replace;calls=[]
        def flaky(source,target):
            calls.append(1)
            if len(calls)<3:raise PermissionError("Transient reader")
            return original(source,target)
        with tempfile.TemporaryDirectory() as temporary:
            target=Path(temporary)/"progress.json"
            with patch.object(Path,"replace",flaky),patch("ocr_probe.time.sleep"):
                atomic_json(target,{"complete":1})
            self.assertIn('"complete":1',target.read_text(encoding="utf-8"))
            self.assertEqual(len(calls),3)
            self.assertEqual(len(list(Path(temporary).iterdir())),1)

    def test_ocr_engine_error_retains_render_quality(self):
        from PIL import Image,ImageDraw
        def render(page,destination,max_edge):
            image=Image.new("L",(200,200),255)
            ImageDraw.Draw(image).rectangle((20,20,80,40),fill=0)
            image.save(destination)
        with tempfile.TemporaryDirectory() as temporary:
            with patch("ocr_probe.render_preview",render),patch("ocr_probe.tesseract_tsv",side_effect=RuntimeError("engine crashed")):
                result=worker({"page":{"native_text_preview":""},"config":{"max_edge":1600,"tesseract":"unused","tessdata":"unused","ocr_timeout":1},"temp_root":temporary})
        self.assertEqual(result["status"],"error")
        self.assertEqual(result["error_phase"],"ocr")
        self.assertGreater(result["image_metrics"]["ink_fraction"],0)
        self.assertEqual(len(result["preview_sha256"]),64)

    def test_plaintext_must_never_be_treated_as_empty_ocr(self):
        with self.assertRaisesRegex(ValueError,"TSV header"):
            parse_tsv("Câu 1: Chọn đáp án đúng\n",100,100)

    def test_models_only_directory_produces_real_tsv(self):
        models=Path(__file__).resolve().parents[1]/"review_workspaces"/"exams_20261024"/"auto_triage_20261025"/"tessdata"
        font=Path(r"C:\Windows\Fonts\arial.ttf")
        if not all(p.is_file() for p in [DEFAULT_TESSERACT,font,models/"eng.traineddata",models/"vie.traineddata"]):
            self.skipTest("Local Tesseract and pinned language assets unavailable")
        self.assertFalse((models/"configs"/"tsv").exists())
        from PIL import Image,ImageDraw,ImageFont
        image=Image.new("L",(1100,160),255)
        ImageDraw.Draw(image).text((20,50),"Question 1: Choose the correct answer.",font=ImageFont.truetype(str(font),45),fill=0)
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"printed_question.png";image.save(path)
            parsed=parse_tsv(tesseract_tsv(path,DEFAULT_TESSERACT,models,3,20),1100,160)
        self.assertGreaterEqual(parsed["word_count"],6)
        self.assertIn("Question",parsed["text"])

    def test_ink_outside_word_boxes_remains_visible(self):
        image=np.full((40,80),255,dtype=np.uint8)
        image[10:20,10:20]=0
        image[10:20,50:60]=0
        metrics=ocr_ink_metrics(image,[{"bbox":[10,10,10,10]}],padding=0)
        self.assertEqual(metrics["ocr_ink_coverage"],.5)
        self.assertEqual(metrics["uncovered_ink_pixels"],100)
        self.assertEqual(metrics["uncovered_ink_fraction"],.03125)

    def test_overlapping_boxes_are_not_double_counted(self):
        image=np.zeros((10,10),dtype=np.uint8)
        metrics=ocr_ink_metrics(image,[{"bbox":[-5,-5,15,15]},{"bbox":[0,0,10,10]}])
        self.assertEqual(metrics["ocr_ink_coverage"],1.)
        self.assertEqual(metrics["uncovered_ink_pixels"],0)

    def test_blank_has_no_uncovered_ink(self):
        metrics=ocr_ink_metrics(np.full((10,10),255,dtype=np.uint8),[])
        self.assertEqual(metrics["ocr_ink_coverage"],1.)
        self.assertEqual(metrics["uncovered_ink_fraction"],0.)

    def test_word_confidence_and_lines_preserved(self):
        tsv=("level\tpage_num\tblock_num\tpar_num\tline_num\tleft\ttop\twidth\theight\tconf\ttext\n"
             "5\t1\t1\t1\t1\t0\t0\t10\t5\t90\tCâu\n"
             "5\t1\t1\t1\t1\t15\t0\t10\t5\t60\t1\n"
             "5\t1\t1\t1\t2\t0\t10\t20\t5\t-1\tignored\n"
             "5\t1\t1\t1\t2\t0\t10\t20\t5\t80\tĐáp\n")
        value=parse_tsv(tsv,100,100)
        self.assertEqual(value["text"],"Câu 1\nĐáp")
        self.assertEqual(value["word_count"],3)
        self.assertAlmostEqual(value["weighted_confidence"],81.429,places=3)


if __name__=="__main__":unittest.main()
