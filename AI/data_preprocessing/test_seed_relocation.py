import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent

class SeedRelocationTests(unittest.TestCase):
    def test_seed_assets_and_protected_splits_survive_relocation(self):
        current = json.loads((ROOT/'CURRENT.json').read_text(encoding='utf-8'))
        core = (ROOT/current['release_path']).resolve()
        sys.path.insert(0, str(core))
        from dependency_paths import V3, REGIONS, NATIVE, SEED_RUN
        from io_utils import load
        from review_app import allowed_roots
        for path, name in [(V3,'manifest.json'), (REGIONS,'regions.jsonl'), (NATIVE,'native_pages.jsonl')]:
            self.assertTrue(path.is_relative_to(ROOT))
            self.assertTrue((path/name).is_file())
        original = json.loads((SEED_RUN/'manifest.json').read_text(encoding='utf-8'))
        manifest = load(SEED_RUN/'manifest.json')
        self.assertEqual(original['document'], manifest['document'])
        self.assertEqual(Path(manifest['asset_root']).resolve(), SEED_RUN.resolve())
        self.assertEqual(set(allowed_roots(SEED_RUN, manifest)), {SEED_RUN.resolve()})
        self.assertTrue(load(V3/'benchmark_groups.json')['protected_holdout_pages'])
        first = json.loads((SEED_RUN/'records.jsonl').read_text(encoding='utf-8').splitlines()[0])
        self.assertTrue((SEED_RUN/first['render_path']).is_file())

if __name__ == '__main__': unittest.main()
