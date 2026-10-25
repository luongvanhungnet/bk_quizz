import copy
import unittest

from native_footer_evidence import identify_footer


class NativeFooterEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.page={"id":"rp_fixture","identity":"1"*64,"source_id":"exam_fixture","source_sha256":"2"*64,
                   "page":49,"bbox":[0.,0.,600.,800.],"tile_count":1,"tile_index":0}
        self.native={"image_count":0}
        self.extracted={"width":600.,"height":800.,"lines":[
            {"text":"Câu 1: Chọn giá trị trong nguồn?","bbox":[40.,50.,440.,70.]},
            {"text":"A. 49","bbox":[40.,100.,90.,120.]},
            {"text":"B. 50","bbox":[40.,130.,90.,150.]},
            {"text":"49","bbox":[290.,745.,310.,760.]}]}
        self.text="Câu 1: Chọn giá trị trong nguồn?\nA. 49\nB. 50\n       49\n"

    def test_full_page_unique_bottom_footer_is_bound_to_source_geometry(self):
        proof,reason=identify_footer(self.page,self.native,self.extracted,self.text)
        self.assertIsNone(reason)
        self.assertEqual(proof["footer_text"],"49")
        self.assertEqual(proof["footer_bbox"],[290.,745.,310.,760.])
        self.assertEqual(proof["vertical_gap_points"],595.)
        self.assertEqual(proof["source_sha256"],self.page["source_sha256"])
        self.assertFalse(proof["human_verified"])
        self.assertTrue(all(proof["checks"].values()))
        self.assertEqual(proof["position_evidence"]["kind"],"central_footer")

    def test_page_number_in_body_is_not_a_footer(self):
        changed=copy.deepcopy(self.extracted);changed["lines"][-1]["bbox"]=[520.,200.,540.,215.]
        proof,reason=identify_footer(self.page,self.native,changed,self.text)
        self.assertIsNone(proof);self.assertEqual(reason,"footer_not_narrow_bottom_line")

    def test_clipped_tile_and_raster_page_do_not_receive_proof(self):
        for changes in [{"tile_count":2},{"bbox":[0.,100.,600.,800.]},{"tile_index":1}]:
            with self.subTest(changes=changes):
                self.assertIsNone(identify_footer(dict(self.page,**changes),self.native,self.extracted,self.text)[0])
        self.assertIsNone(identify_footer(self.page,{"image_count":1},self.extracted,self.text)[0])

    def test_another_physical_line_below_or_touching_footer_blocks_removal(self):
        for box in [[40.,770.,300.,785.],[40.,740.,300.,755.],[40.,730.,300.,743.]]:
            with self.subTest(box=box):
                changed=copy.deepcopy(self.extracted)
                changed["lines"].append({"text":"Nội dung cần giữ","bbox":box})
                self.assertIsNone(identify_footer(self.page,self.native,changed,self.text)[0])

    def test_duplicate_nonfinal_or_wrong_number_is_not_proven(self):
        for text in [self.text+"Còn dữ kiện\n",self.text.replace("A. 49","49"),self.text.rstrip()[:-2]+"50\n"]:
            with self.subTest(text=text):
                self.assertIsNone(identify_footer(self.page,self.native,self.extracted,text)[0])
        changed=copy.deepcopy(self.extracted);changed["lines"][-1]["text"]="50"
        self.assertIsNone(identify_footer(self.page,self.native,changed,self.text)[0])

    def test_invalid_geometry_and_unknown_dimensions_are_not_proven(self):
        for box in [[520.,745.,float("nan"),760.],[520.,745.,540.,810.]]:
            changed=copy.deepcopy(self.extracted);changed["lines"][-1]["bbox"]=box
            self.assertIsNone(identify_footer(self.page,self.native,changed,self.text)[0])
        self.assertIsNone(identify_footer(self.page,self.native,{"lines":[]},self.text)[0])

    def test_bottom_numeric_option_with_four_point_gap_is_preserved(self):
        changed=copy.deepcopy(self.extracted)
        changed["lines"][-2]["bbox"]=[40.,720.,90.,741.]
        proof,reason=identify_footer(self.page,self.native,changed,self.text)
        self.assertIsNone(proof)
        self.assertEqual(reason,"footer_not_separated_from_source_content")

    def test_offcenter_number_requires_repeated_same_source_template(self):
        changed=copy.deepcopy(self.extracted);changed["lines"][-1]["bbox"]=[520.,745.,540.,760.]
        proof,reason=identify_footer(self.page,self.native,changed,self.text)
        self.assertIsNone(proof)
        self.assertEqual(reason,"offcenter_footer_without_consistent_source_template")
        evidence={"source_sha256":self.page["source_sha256"],"source_pages":[47,48,49],
                  "anchor_left_fraction":520/600,"anchor_top_fraction":745/800}
        proof,reason=identify_footer(self.page,self.native,changed,self.text,position_evidence=evidence)
        self.assertIsNone(reason)
        self.assertEqual(proof["position_evidence"]["source_page_count"],3)
        for bad in [dict(evidence,source_pages=[48,49]),dict(evidence,source_sha256="3"*64),
                    dict(evidence,anchor_left_fraction=.5),dict(evidence,source_pages=[46,47,48])]:
            self.assertIsNone(identify_footer(self.page,self.native,changed,self.text,position_evidence=bad)[0])


if __name__=="__main__":unittest.main()
