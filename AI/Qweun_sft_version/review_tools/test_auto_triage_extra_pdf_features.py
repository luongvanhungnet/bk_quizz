from pathlib import Path
import tempfile
import unittest

import pymupdf

from auto_triage_extra_pdf_features import emphasis_features,read_source_metadata,sha


class ExtraPdfFeatureTests(unittest.TestCase):
    def test_cached_span_flags_and_font_names_both_preserve_emphasis(self):
        page={"lines":[{"spans":[{"text":"Plain","font":"Times-Roman","flags":0,"bbox":[0,0,20,10]},
                               {"text":"Bold","font":"OtherFont","flags":pymupdf.TEXT_FONT_BOLD,"bbox":[0,10,20,20]},
                               {"text":"Italic","font":"Times-Italic","bbox":[0,20,20,30]}]}]}
        result=emphasis_features({"bbox":[0,0,100,100]},page,pymupdf.TEXT_FONT_BOLD,pymupdf.TEXT_FONT_ITALIC)
        self.assertEqual(result["emphasis_status"],"ok")
        self.assertEqual(result["emphasized_chars"],10)
        self.assertAlmostEqual(result["native_emphasis_ratio"],10/15)

    def test_missing_cached_page_is_unknown_not_zero(self):
        result=emphasis_features({"bbox":[0,0,100,100]},None,16,2)
        self.assertEqual(result["emphasis_status"],"unknown")
        self.assertIsNone(result["native_emphasis_ratio"])

    def test_cached_text_without_span_evidence_is_unknown_not_zero(self):
        result=emphasis_features({"bbox":[0,0,100,100]}, {"text":"Source text exists but font information is unavailable.","lines":[]},16,2)
        self.assertEqual(result["emphasis_status"],"unknown")
        self.assertIsNone(result["native_emphasis_ratio"])

    def test_tiled_source_only_counts_intersecting_emphasized_spans(self):
        page={"lines":[{"spans":[{"text":"Plain","font":"Times-Roman","flags":0,"bbox":[0,0,20,10]},
                               {"text":"Bold","font":"Times-Bold","flags":16,"bbox":[0,120,20,130]}]}]}
        result=emphasis_features({"bbox":[0,0,100,100],"tile_count":2},page,16,2)
        self.assertEqual(result["native_emphasis_ratio"],0)

    def test_pdf_annotations_and_widgets_are_counted_in_catalog_clip(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/"fixture.pdf"
            with pymupdf.open() as document:
                page=document.new_page(width=300,height=400)
                page.add_rect_annot(pymupdf.Rect(20,20,70,50))
                page.add_rect_annot(pymupdf.Rect(220,20,270,50))
                widget=pymupdf.Widget();widget.field_name="answer";widget.field_type=pymupdf.PDF_WIDGET_TYPE_TEXT
                widget.rect=pymupdf.Rect(20,200,120,230);page.add_widget(widget)
                document.save(source)
            digest=sha(source)
            rows=[{"id":"left","identity":"left-identity","source_path":str(source),"source_sha256":digest,"page":1,"bbox":[0,0,150,400]},
                  {"id":"right","identity":"right-identity","source_path":str(source),"source_sha256":digest,"page":1,"bbox":[150,0,300,400]}]
            result=read_source_metadata(rows);left,right=result["rows"]
            self.assertEqual(left["annotation_count"],1);self.assertEqual(left["widget_count"],1)
            self.assertEqual(right["annotation_count"],1);self.assertEqual(right["widget_count"],0)
            self.assertEqual(result["source_sha256_before"],digest)
            self.assertEqual(result["source_sha256_after"],digest)
            self.assertEqual(sha(source),digest)

    def test_changed_source_is_rejected_before_metadata_read(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/"fixture.pdf";source.write_bytes(b"changed source")
            rows=[{"id":"p","identity":"i","source_path":str(source),"source_sha256":"a"*64,"page":1,"bbox":[0,0,100,100]}]
            with self.assertRaisesRegex(ValueError,"before metadata"):read_source_metadata(rows)


if __name__=="__main__":unittest.main()
