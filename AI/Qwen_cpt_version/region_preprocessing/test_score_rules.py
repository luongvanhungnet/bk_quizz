import copy
import unittest
from score_rules import score,decide,choose_representatives,region_features,POLICY


def terms(**values):return dict({'D':0,'C':0,'U':0,'R':0,'B':0,'E':0},**values)


class ScoringChecks(unittest.TestCase):
    def test_formula_matches_the_requested_weights(self):
        self.assertEqual(score({'D':1,'C':1,'U':1,'R':1,'B':1,'E':1}),3)
        self.assertEqual(score(terms(D=1,U=1,R=1)),7)

    def test_unknown_large_sparse_image_is_review_not_automatic_vlm(self):
        self.assertEqual(decide(terms(U=1,R=1)),'review')

    def test_dense_graph_score_six_is_not_claimed_solved(self):
        self.assertEqual(decide(terms(D=1,U=1)),'review')

    def test_verified_background_and_complete_extraction_bypass_vlm(self):
        self.assertEqual(decide(terms(D=1,U=1,R=1,B=1)),'exclude_verified_decoration')
        self.assertEqual(decide(terms(D=1,R=1,E=1)),'reuse_verified_extraction')

    def test_confirmed_chart_has_explicit_six_point_exception(self):
        self.assertEqual(decide(terms(C=1,U=1,R=1)),'vlm')
        self.assertEqual(decide(terms(C=1,U=1)),'review')

    def test_pending_duplicate_does_not_claim_success(self):
        self.assertEqual(decide(terms(D=1,U=1,R=1),True),'reuse_pending_canonical')

    def test_no_quota_promotion_when_every_image_is_unknown(self):
        decisions=[decide(terms(U=1,R=1)) for _ in range(1060)]
        self.assertEqual(decisions.count('vlm'),0)

    def test_no_quota_truncation_when_every_graph_is_high_risk(self):
        decisions=[decide(terms(D=1,U=1,R=1)) for _ in range(1060)]
        self.assertEqual(decisions.count('vlm'),1060)

    def test_high_risk_alias_promotes_a_representative_not_loses_the_graph(self):
        regions=[]
        for n,flags in [(1,terms(D=1,U=1)),(2,terms(D=1,U=1,R=1))]:
            regions.append({'id':str(n),'page':n,'engine':'vlm','state':'score_review' if n==1 else 'exact_duplicate',
                'raw_pixel_sha256':'same','layout_score':.8,'routing_features':{'terms':flags,'score':score(flags),'base_decision':decide(flags)}})
        choose_representatives(regions)
        self.assertEqual(regions[1]['state'],'scheduled')
        self.assertEqual(regions[0]['duplicate_of'],'2')

    def test_native_text_coverage_alone_never_sets_specialist_success(self):
        page={'render_width':1000,'page_size_pt':[1000,800],'blocks':[],'vector_regions':[]}
        region={'bbox_pixels':[0,0,1000,800],'state':'candidate','label':'image','layout_score':.8}
        context={'native_text_coverage':1.,'body_text':'', 'body_characters':0}
        probe={'white_fraction':.9,'circles':4,'rectangles':0,'line_segments':5,'horizontal_segments':2,'vertical_segments':2}
        features=region_features(region,page,context,probe)
        self.assertFalse(features['specialist_success'])
        self.assertEqual(features['terms']['U'],1)

    def test_title_slide_stripes_are_not_graph_proof_or_verified_background(self):
        page={'render_width':1000,'page_size_pt':[1000,800],'blocks':[],'vector_regions':[]}
        region={'bbox_pixels':[0,0,1000,800],'state':'candidate','label':'chart','layout_score':.8}
        context={'native_text_coverage':None,'body_text':'THUẬT TOÁN ỨNG DỤNG\nBộ môn KHMT\na@b.edu', 'body_characters':60}
        probe={'white_fraction':.8,'circles':16,'rectangles':6,'line_segments':232,'horizontal_segments':28,'vertical_segments':204}
        f=region_features(region,page,context,probe)
        self.assertFalse(f['has_diagram']);self.assertFalse(f['has_chart'])
        self.assertEqual(f['terms']['B'],0)
        self.assertEqual(f['decision'],'review')

    def test_text_glyph_circles_without_diagonal_links_do_not_trigger_raster_graph(self):
        page={'render_width':1000,'page_size_pt':[1000,800],'blocks':[],'vector_regions':[]}
        region={'bbox_pixels':[0,0,1000,800],'state':'candidate','label':'image','layout_score':.8}
        context={'native_text_coverage':None,'body_text':'DFS(6)', 'body_characters':41}
        probe={'white_fraction':.97,'circles':7,'rectangles':0,'line_segments':17,'horizontal_segments':12,'vertical_segments':5}
        self.assertFalse(region_features(region,page,context,probe)['has_diagram'])


if __name__=='__main__':unittest.main()
