import unittest
from pathlib import Path
import build_inputs

class RelocatedPlanTests(unittest.TestCase):
    def test_current_plan_can_be_rebuilt_without_old_input_bundles(self):
        source = Path(__file__).resolve().parent.parent/'uploads_134_unit100_20261022/plan/plan.json'
        plan, previous = build_inputs.source_plan(source)
        self.assertEqual(plan['release_manifest_sha256'], build_inputs.digest(build_inputs.ENGINE/'RELEASE.json'))
        seeds = [j for j in plan['jobs'] if not j['layout_required']]
        self.assertTrue(seeds)
        for job in seeds:
            self.assertIn('dependency_data', job['run'])
            self.assertTrue((Path(job['run'])/'records.jsonl').exists())
        self.assertEqual(previous['plan_sha256'], build_inputs.digest(source))

if __name__ == '__main__': unittest.main()
